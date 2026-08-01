from __future__ import annotations

import argparse
import json
import logging
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence, cast, get_args, get_origin

from excel_grapher.core.cell_types import normalize_cell_type_env_key
from excel_grapher.grapher import (
    DependencyGraph,
    DynamicRefConfig,
)
from excel_grapher.exporter import CodeGenerator
from excel_grapher.exporter.codegen import GraphLike
from excel_grapher.series_bindings import load_series_bindings
from excel_grapher.series_bindings.types import WorkbookSeriesBindings

from src.dependency_graph_viz import (
    constant_keys_from_leaf_classification,
    series_cell_keys,
    write_dependency_graph_site,
)
from src.internal_bindings import (
    InternalBindingIndex,
    binding_node_labels,
)
from src.internal_binding_coverage import InternalBindingCoverageReport
from src.refactor_bindings import BindingKeyValue
from src.codegen_cache import (
    get_or_build_codegen_modules,
    guide_fingerprint,
)
from src.docstring_callback import configure_docstring_callback
from src.differential_validation import run_post_refactor_differential
from src.export_validation_assets import export_reference_reports
from src.package_materialize import (
    materialize_package,
    try_materialize_refactored_package_from_cache,
)
from src.projection_cache import projection_cache_key
from src.logging_config import configure_logging
from src.pipeline_config import (
    PipelineConfig,
    add_clustering_mode_argument,
    add_variation_mode_argument,
    apply_clustering_mode_cli_override,
    apply_variation_mode_cli_override,
    load_pipeline_config,
    validate_pipeline_config,
)
from src.pipeline_context import activate_pipeline_config
from src.pipeline_monitor import (
    StageTimer,
    monitor_pipeline_stage,
    profile_if_enabled,
    resolve_stall_log_path,
)
from src.bindings_validation_cache import get_or_build_bindings_validation
from src.graph_cache import get_or_build_dependency_graph
from src.series_derived_cache import get_or_build_series_derived
from src.series_resolution_cache import get_or_build_series_resolution
from src.stage_timings import (
    PipelineTimings,
    record_cache_result,
    stage_span,
    stage_timings_path,
)
from src.subgraph_projection import build_refactor_projection

SeriesResolutionList = Sequence[Mapping[str, Any]]

EXTRACTION_SUMMARY_SCHEMA_VERSION = "1.0.0"

logger = logging.getLogger(__name__)

PipelineStageName = Literal[
    "extract",
    "export",
    "refactor",
    "validate",
    "document",
]
PIPELINE_STAGES: tuple[PipelineStageName, ...] = (
    "extract",
    "export",
    "refactor",
    "validate",
    "document",
)


class DocumentStageError(RuntimeError):
    """Raised when the document stage fails after earlier artifacts are written."""


@dataclass(frozen=True)
class PipelineGraphResult:
    graph: DependencyGraph
    series_bindings: WorkbookSeriesBindings
    input_series: SeriesResolutionList
    output_series: SeriesResolutionList
    internal_series: SeriesResolutionList
    constant_series: SeriesResolutionList
    graph_cache_key: str
    leaf_classification: dict[str, str]
    internal_binding_index: InternalBindingIndex
    bound_address_keys: dict[str, dict[str, BindingKeyValue]]
    address_to_series_id: dict[str, str]
    coverage_report: InternalBindingCoverageReport | None


@dataclass(frozen=True)
class DependencyGraphExtraction:
    """Graph build result plus timing diagnostics for the extract-only stage."""

    graph: DependencyGraph
    series_bindings: WorkbookSeriesBindings
    input_series: SeriesResolutionList
    output_series: SeriesResolutionList
    internal_series: SeriesResolutionList
    constant_series: SeriesResolutionList
    leaf_classification: dict[str, str]
    internal_binding_index: InternalBindingIndex
    timer: StageTimer
    elapsed_seconds: float


@dataclass(frozen=True)
class ExportStageState:
    """Shared state produced by the export stage for later pipeline stages."""

    config: PipelineConfig
    graph_result: PipelineGraphResult
    refactor_projection: Any
    internal_binding_index: InternalBindingIndex
    bound_address_keys: dict[str, dict[str, BindingKeyValue]]
    address_to_series_id: dict[str, str]
    package_root: Path
    codegen_cache_key: str


@dataclass(frozen=True)
class RefactorStageState:
    """Shared state produced by the refactor stage for validation."""

    config: PipelineConfig


def count_provenance_edges(graph: DependencyGraph) -> int:
    """Count dependency edges that carry extraction provenance metadata."""
    count = 0
    for key in graph:
        for dependency in graph.get_dependencies(key):
            if graph.get_edge_attrs(key, dependency).provenance is not None:
                count += 1
    return count


def _graph_edge_count(graph: DependencyGraph) -> int:
    return sum(len(graph.get_dependencies(key)) for key in graph)


def extract_dependency_graph_result(
    config: PipelineConfig,
    *,
    no_cache: bool = False,
    force_rebuild: bool = False,
    timings: PipelineTimings | None = None,
    timer: StageTimer | None = None,
    profile: bool = True,
) -> DependencyGraphExtraction:
    """Build the pipeline dependency graph and collect stage timings.

    When ``timer`` is supplied (e.g. from ``stage_span``), spans accumulate on
    that timer. ``profile=False`` skips the local ``profile_if_enabled`` wrap so
    a caller that already profiles the surrounding stage is not double-wrapped.
    """
    stage_timer = timer if timer is not None else StageTimer()
    stall_log_path = resolve_stall_log_path(config.graph_output_dir)
    started = time.perf_counter()

    def _build() -> PipelineGraphResult:
        return build_pipeline_graph(
            config,
            timer=stage_timer,
            stall_log_path=stall_log_path,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            timings=timings,
        )

    if profile:
        with profile_if_enabled(config.graph_output_dir, basename="extract"):
            graph_result = _build()
    else:
        graph_result = _build()
    elapsed_seconds = time.perf_counter() - started
    return DependencyGraphExtraction(
        graph=graph_result.graph,
        series_bindings=graph_result.series_bindings,
        input_series=graph_result.input_series,
        output_series=graph_result.output_series,
        internal_series=graph_result.internal_series,
        constant_series=graph_result.constant_series,
        leaf_classification=graph_result.leaf_classification,
        internal_binding_index=graph_result.internal_binding_index,
        timer=stage_timer,
        elapsed_seconds=elapsed_seconds,
    )


def _artifact_output_path(config: PipelineConfig, path: Path) -> str:
    resolved = path if path.is_absolute() else config.repo_root / path
    try:
        return resolved.relative_to(config.repo_root).as_posix()
    except ValueError:
        return resolved.as_posix()


def write_dependency_graph_artifacts(
    extraction: DependencyGraphExtraction,
    config: PipelineConfig,
) -> dict[str, Any]:
    """Write the interactive graph site and extraction summary JSON."""
    graph = extraction.graph
    leaf_classification = extraction.leaf_classification
    output_dir = config.graph_output_dir
    artifact_started = time.perf_counter()
    internal_binding_index = extraction.internal_binding_index
    write_dependency_graph_site(
        graph,
        output_dir,
        node_labels=binding_node_labels(graph, internal_binding_index),
        target_keys=set(config.targets),
        input_keys=series_cell_keys(extraction.input_series),
        output_keys=series_cell_keys(extraction.output_series),
        internal_binding_index=internal_binding_index,
        constant_keys=constant_keys_from_leaf_classification(leaf_classification),
        timer=extraction.timer,
    )
    elapsed_seconds = extraction.elapsed_seconds + (
        time.perf_counter() - artifact_started
    )

    output_paths = {
        "output_dir": _artifact_output_path(config, output_dir),
        "index_html": _artifact_output_path(config, output_dir / "index.html"),
        "dependency_graph_json": _artifact_output_path(
            config, output_dir / "dependency-graph.json"
        ),
        "dependencies_dot": _artifact_output_path(
            config, output_dir / "dependencies.dot"
        ),
        "graph_topology_json": _artifact_output_path(
            config, output_dir / "graph-topology.json"
        ),
        "extraction_summary_json": _artifact_output_path(
            config, output_dir / "extraction-summary.json"
        ),
    }
    summary: dict[str, Any] = {
        "schema_version": EXTRACTION_SUMMARY_SCHEMA_VERSION,
        "node_count": len(graph),
        "edge_count": _graph_edge_count(graph),
        "leaf_count": len(graph.leaf_keys()),
        "provenance_edge_count": count_provenance_edges(graph),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "stage_timings": extraction.timer.as_dict(),
        "output_paths": output_paths,
    }
    summary_path = output_dir / "extraction-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


def extract_dependency_graph(
    config: PipelineConfig,
    *,
    no_cache: bool = False,
    force_rebuild: bool = False,
    timings: PipelineTimings | None = None,
) -> dict[str, Any]:
    """Build the dependency graph, write review artifacts, and return the summary."""
    with (
        profile_if_enabled(config.graph_output_dir, basename="extract"),
        stage_span(timings, "extract") as timer,
    ):
        extraction = extract_dependency_graph_result(
            config,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            timings=timings,
            timer=timer,
            profile=False,
        )
        summary = write_dependency_graph_artifacts(extraction, config)
        timer.print_summary(header="Extract stage timings")
        stall_log_path = resolve_stall_log_path(config.graph_output_dir)
        if stall_log_path.is_file():
            print(f"Stall diagnostics: {stall_log_path}")
        print(
            f"Wrote dependency graph artifacts to {config.graph_output_dir.resolve()}/"
        )
        return summary


def is_constant_constraint(constraint: object) -> bool:
    """True when the constraint fixes a single value (lookup/structural data)."""
    return get_origin(constraint) is Literal and len(get_args(constraint)) == 1


def classify_leaves_from_constraints(
    constraint_map: Mapping[str, object],
    leaf_keys: Iterable[str],
) -> dict[str, str]:
    """Classify graph leaves as inputs or constants from their constraints."""
    normalized_constraints = {
        normalize_cell_type_env_key(key): value for key, value in constraint_map.items()
    }
    keys = list(leaf_keys)
    missing = [
        key
        for key in keys
        if normalize_cell_type_env_key(key) not in normalized_constraints
    ]
    if missing:
        raise KeyError(f"missing constraints for leaf cells: {missing}")
    return {
        key: (
            "constant"
            if is_constant_constraint(
                normalized_constraints[normalize_cell_type_env_key(key)]
            )
            else "input"
        )
        for key in keys
    }


def build_pipeline_graph(
    config: PipelineConfig,
    *,
    timer: StageTimer | None = None,
    stall_log_path: Path | None = None,
    no_cache: bool = False,
    force_rebuild: bool = False,
    timings: PipelineTimings | None = None,
) -> PipelineGraphResult:
    def stage(name: str):
        if timer is None:
            return nullcontext()
        return monitor_pipeline_stage(
            timer,
            name,
            stall_log_path=stall_log_path,
        )

    with stage("load_series_bindings"):
        series_bindings: WorkbookSeriesBindings = load_series_bindings(
            config.bindings_path
        )
        dynamic_ref_config = DynamicRefConfig.from_constraints(config.constraints, {})

    with stage("create_dependency_graph"):
        graph_result = get_or_build_dependency_graph(
            workbook_path=config.workbook_path,
            targets=config.targets,
            constraints=config.constraints,
            bindings_path=config.bindings_path,
            dynamic_refs=dynamic_ref_config,
            load_values=True,
            capture_dependency_provenance=True,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
        )
        graph = graph_result.graph
        graph_cache_key = graph_result.cache_key
        record_cache_result(timings, "dependency-graph", graph_result)

    with stage("validate_series_bindings"):
        validation_result = get_or_build_bindings_validation(
            graph,
            series_bindings,
            workbook_path=config.workbook_path,
            graph_cache_key=graph_cache_key,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
        )
        record_cache_result(timings, "bindings-validation", validation_result)
        binding_validation_report = validation_result.report
        if not binding_validation_report["ok"]:
            raise ValueError(
                f"Invalid series bindings: {binding_validation_report['issues']!r}"
            )

    with stage("derive_series"):
        series_result = get_or_build_series_resolution(
            graph,
            series_bindings,
            workbook_path=config.workbook_path,
            graph_cache_key=graph_cache_key,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
        )
        record_cache_result(timings, "series-resolution", series_result)
        input_series = series_result.input_series
        output_series = series_result.output_series
        internal_series = series_result.internal_series
        constant_series = series_result.constant_series

    with stage("series_derived"):
        derived_result = get_or_build_series_derived(
            graph,
            constraints=config.constraints,
            input_series=input_series,
            output_series=output_series,
            internal_series=internal_series,
            constant_series=constant_series,
            input_cells=series_cell_keys(input_series),
            output_cells=series_cell_keys(output_series),
            exempt_cells=config.internal_binding_exempt_cells,
            validation_mode=config.internal_binding_validation_mode,
            context="pipeline",
            graph_cache_key=graph_cache_key,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
        )
        record_cache_result(timings, "series-derived", derived_result)

    return PipelineGraphResult(
        graph=graph,
        series_bindings=series_bindings,
        input_series=input_series,
        output_series=output_series,
        internal_series=internal_series,
        constant_series=constant_series,
        graph_cache_key=graph_cache_key,
        leaf_classification=derived_result.leaf_classification,
        internal_binding_index=derived_result.internal_binding_index,
        bound_address_keys=derived_result.bound_address_keys,
        address_to_series_id=derived_result.address_to_series_id,
        coverage_report=derived_result.coverage_report,
    )


def run_export_stage(
    config: PipelineConfig,
    *,
    no_cache: bool = False,
    force_rebuild: bool = False,
    timings: PipelineTimings | None = None,
) -> ExportStageState:
    """Build the graph, generate the package under dist/, and seed the harness."""
    configure_logging()
    stall_log_path = resolve_stall_log_path(config.graph_output_dir)
    with (
        profile_if_enabled(config.graph_output_dir, basename="export"),
        stage_span(timings, "export") as timer,
    ):
        graph_result = build_pipeline_graph(
            config,
            timer=timer,
            stall_log_path=stall_log_path,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            timings=timings,
        )
        graph = graph_result.graph
        series_bindings = graph_result.series_bindings
        graph_cache_key = graph_result.graph_cache_key
        if stall_log_path.is_file():
            print(f"Stall diagnostics: {stall_log_path}")
        projection_started = time.perf_counter()
        refactor_projection = build_refactor_projection(
            graph,
            graph_cache_key=graph_cache_key,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            timings=timings,
        )
        timer.record(
            "build_refactor_projection", time.perf_counter() - projection_started
        )
        state = _generate_export_package(
            config,
            graph_result=graph_result,
            series_bindings=series_bindings,
            graph_cache_key=graph_cache_key,
            refactor_projection=refactor_projection,
            internal_binding_index=graph_result.internal_binding_index,
            bound_address_keys=graph_result.bound_address_keys,
            address_to_series_id=graph_result.address_to_series_id,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            timings=timings,
            timer=timer,
        )
        timer.print_summary(header="Export stage timings")
        return state


def _generate_export_package(
    config: PipelineConfig,
    *,
    graph_result: PipelineGraphResult,
    series_bindings: WorkbookSeriesBindings,
    graph_cache_key: str,
    refactor_projection: Any,
    internal_binding_index: InternalBindingIndex,
    bound_address_keys: dict[str, dict[str, BindingKeyValue]],
    address_to_series_id: dict[str, str],
    no_cache: bool,
    force_rebuild: bool,
    timings: PipelineTimings | None,
    timer: StageTimer,
) -> ExportStageState:
    """Generate the package modules under dist/ and seed the validation harness."""
    proj_cache_key = projection_cache_key(graph_cache_key=graph_cache_key)
    targets = list(config.targets)
    unpack_return = True
    docstring_renderer = "google"
    callback_name = config.docstring_callback_name

    def _build_modules() -> dict[str, str]:
        configure_docstring_callback(config)
        with CodeGenerator(
            cast(GraphLike, refactor_projection), unpack_return=unpack_return
        ) as generator:
            return generator.generate_modules(
                targets,
                series_bindings=series_bindings,
                bindings_workbook=config.workbook_path,
                series_docstring_callback=callback_name,
                docstring_renderer=docstring_renderer,
            )

    codegen_started = time.perf_counter()
    codegen_result = get_or_build_codegen_modules(
        projection_cache_key=proj_cache_key,
        targets=targets,
        unpack_return=unpack_return,
        docstring_renderer=docstring_renderer,
        series_docstring_callback=callback_name,
        guide_sha256=guide_fingerprint(config.guide_path),
        build_modules=_build_modules,
        no_cache=no_cache,
        force_rebuild=force_rebuild,
    )
    timer.record("codegen", time.perf_counter() - codegen_started)
    record_cache_result(timings, "codegen", codegen_result)

    package_started = time.perf_counter()
    package_root = config.package_root
    materialize_package(config, codegen_key=codegen_result.cache_key)
    timer.record("write_export_package", time.perf_counter() - package_started)
    print(
        f"codegen: {len(codegen_result.modules)} modules "
        f"({codegen_result.elapsed_seconds:.1f}s)",
        flush=True,
    )

    return ExportStageState(
        config=config,
        graph_result=graph_result,
        refactor_projection=refactor_projection,
        internal_binding_index=internal_binding_index,
        bound_address_keys=bound_address_keys,
        address_to_series_id=address_to_series_id,
        package_root=package_root,
        codegen_cache_key=codegen_result.cache_key,
    )


def run_refactor_stage(
    state: ExportStageState,
    *,
    no_cache: bool = False,
    force_rebuild: bool = False,
    timings: PipelineTimings | None = None,
) -> RefactorStageState:
    """Cluster formulas and rewrite internals behind the parity gate."""
    from src.cluster_cache import get_or_build_clusters_and_schedule
    from src.internals_cache import (
        consumed_refactors_digest,
        internals_cache_key,
        load_refactored_internals_payload,
        save_refactored_internals_payload,
    )
    from src.internals_refactor import refactor_internals_all_clusters

    config = state.config
    graph_result = state.graph_result
    with (
        profile_if_enabled(config.graph_output_dir, basename="refactor"),
        stage_span(timings, "refactor") as timer,
    ):
        # Fresh-clone / committed-dist path: trust sidecar keys (#238).
        if (
            not no_cache
            and not force_rebuild
            and try_materialize_refactored_package_from_cache(
                config, codegen_key=state.codegen_cache_key
            )
        ):
            print(
                "internals_refactor: skipped "
                f"(adopted dist/ cache keys for codegen={state.codegen_cache_key[:12]})",
                flush=True,
            )
            return RefactorStageState(config=config)

        bindings_started = time.perf_counter()
        bound_address_keys = state.bound_address_keys
        address_to_series_id = state.address_to_series_id
        timer.record("build_refactor_bindings", time.perf_counter() - bindings_started)
        print("clustering: partitioning formulas…", flush=True)
        clustering_started = time.perf_counter()
        cluster_result = get_or_build_clusters_and_schedule(
            state.refactor_projection,
            bound_address_keys=bound_address_keys,
            address_to_series_id=address_to_series_id,
            workbook_path=config.workbook_path,
            layout=config.projection_layout,
            bindings_path=config.bindings_path,
            projection_cache_key=projection_cache_key(
                graph_cache_key=graph_result.graph_cache_key
            ),
            variation_mode=config.variation_mode,
            clustering_mode=config.clustering_mode,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
        )
        formula_clusters = cluster_result.clusters
        clustering_seconds = time.perf_counter() - clustering_started
        timer.record("cluster_graph_formulas", clustering_seconds)
        record_cache_result(timings, "clusters", cluster_result)
        formula_count = sum(len(cluster.members) for cluster in formula_clusters)
        print(
            f"clustering: {formula_count} formulas → {len(formula_clusters)} clusters "
            f"({clustering_seconds:.1f}s)",
            flush=True,
        )

        # Content-keyed warm hit (#239): materialize and skip Pass 1 / gate / Pass 2.
        refactor_digest = consumed_refactors_digest()
        internals_key = internals_cache_key(
            codegen_cache_key=state.codegen_cache_key,
            clusters_cache_key=cluster_result.cache_key,
            consumed_refactors_digest=refactor_digest,
        )
        if not no_cache and not force_rebuild:
            cached_source = load_refactored_internals_payload(internals_key)
            if cached_source is not None:
                materialize_package(
                    config,
                    codegen_key=state.codegen_cache_key,
                    internals_key=internals_key,
                )
                print(
                    "internals: cache hit "
                    f"(key={internals_key[:12]}); skipped Pass 1 / parity / Pass 2",
                    flush=True,
                )
                return RefactorStageState(config=config)

        print(
            f"internals_refactor: rewriting {len(formula_clusters)} clusters…",
            flush=True,
        )
        refactor_started = time.perf_counter()
        run_result = refactor_internals_all_clusters(
            state.refactor_projection,
            formula_clusters,
            internals_path=state.package_root / "internals.py",
            source_graph=graph_result.graph,
            internal_binding_index=state.internal_binding_index,
            bound_address_keys=bound_address_keys,
            bindings_path=config.bindings_path,
            workbook_path=config.workbook_path,
            address_to_series_id=address_to_series_id,
            refactor_schedule=cluster_result.schedule,
            timer=timer,
            codegen_cache_key=state.codegen_cache_key,
        )
        refactor_seconds = time.perf_counter() - refactor_started
        # Do not record an ``internals_refactor`` rollup span: Pass 1 leaf spans
        # and parity/pass2/phase_c already partition that work on the same timer.
        print(
            f"internals_refactor: done ({refactor_seconds:.1f}s)",
            flush=True,
        )

        # Recompute the key after the run so newly written LLM cache entries
        # participate in the digest (first-run → second-run warm hit).
        cacheable = getattr(run_result, "cacheable", False)
        final_source = getattr(run_result, "final_source", None)
        if not no_cache and cacheable and isinstance(final_source, str):
            post_digest = consumed_refactors_digest()
            post_key = internals_cache_key(
                codegen_cache_key=state.codegen_cache_key,
                clusters_cache_key=cluster_result.cache_key,
                consumed_refactors_digest=post_digest,
            )
            save_refactored_internals_payload(
                final_source,
                cache_key=post_key,
                codegen_cache_key=state.codegen_cache_key,
                clusters_cache_key=cluster_result.cache_key,
                consumed_refactors_digest=post_digest,
            )
            materialize_package(
                config,
                codegen_key=state.codegen_cache_key,
                internals_key=post_key,
            )
            print(
                f"internals: cache store (key={post_key[:12]})",
                flush=True,
            )
    return RefactorStageState(config=config)


def run_validate_stage(
    state: RefactorStageState,
    *,
    no_cache: bool = False,
    timings: PipelineTimings | None = None,
) -> int | None:
    """Run post-refactor differential and ship reference reports into dist/.

    Returns the differential harness exit code when it ran, ``0`` on a cache
    hit, or ``None`` when differential was skipped (for example under CI).
    """
    config = state.config
    with (
        profile_if_enabled(config.graph_output_dir, basename="validate"),
        stage_span(timings, "validate") as timer,
    ):
        differential_started = time.perf_counter()
        exit_code = run_post_refactor_differential(
            config=config,
            no_cache=no_cache,
        )
        timer.record(
            "post_refactor_differential",
            time.perf_counter() - differential_started,
        )
        reports_started = time.perf_counter()
        export_reference_reports(config=config)
        timer.record("export_reference_reports", time.perf_counter() - reports_started)
    return exit_code


def run_document_stage(
    config: PipelineConfig,
    *,
    timings: PipelineTimings | None = None,
) -> None:
    """Rewrite the user guide against the exported package.

    Raises :class:`DocumentStageError` on failure; the export and differential
    artifacts written by earlier stages are left in place for diagnosis.
    """
    from src.documentation_pipeline import run_documentation_pipeline

    with (
        profile_if_enabled(config.graph_output_dir, basename="document"),
        stage_span(timings, "document"),
    ):
        try:
            run_documentation_pipeline(config)
        except Exception as error:
            logger.exception(
                "Document stage failed after export/differential artifacts were written"
            )
            print(
                "Document stage failed; export package and differential reports under "
                f"{config.dist_root} and {config.differential_report_dir_rel} are "
                "preserved for diagnosis.",
                flush=True,
            )
            raise DocumentStageError(f"document stage failed: {error}") from error


def run_pipeline(
    config: PipelineConfig,
    *,
    stop_after_stage: PipelineStageName | str = "document",
    no_cache: bool = False,
    force_rebuild: bool = False,
    force_document: bool = False,
) -> None:
    """Run pipeline stages in order, stopping after ``stop_after_stage`` inclusive."""
    if stop_after_stage not in PIPELINE_STAGES:
        raise ValueError(
            f"unknown pipeline stage {stop_after_stage!r}; "
            f"expected one of {list(PIPELINE_STAGES)}"
        )

    timings = PipelineTimings(output_path=stage_timings_path(config.repo_root))
    try:
        _run_pipeline_stages(
            config,
            timings=timings,
            stop_after_stage=stop_after_stage,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            force_document=force_document,
        )
    finally:
        timings.flush()
        print(f"Stage timings: {timings.output_path}", flush=True)


def _run_pipeline_stages(
    config: PipelineConfig,
    *,
    timings: PipelineTimings,
    stop_after_stage: PipelineStageName | str,
    no_cache: bool,
    force_rebuild: bool,
    force_document: bool,
) -> None:
    if stop_after_stage == "extract":
        extract_dependency_graph(
            config,
            no_cache=no_cache,
            force_rebuild=force_rebuild,
            timings=timings,
        )
        return

    export_state = run_export_stage(
        config,
        no_cache=no_cache,
        force_rebuild=force_rebuild,
        timings=timings,
    )
    if stop_after_stage == "export":
        return

    refactor_state = run_refactor_stage(
        export_state,
        no_cache=no_cache,
        force_rebuild=force_rebuild,
        timings=timings,
    )
    if stop_after_stage == "refactor":
        return

    differential_exit_code = run_validate_stage(
        refactor_state,
        no_cache=no_cache,
        timings=timings,
    )
    if stop_after_stage == "validate":
        return

    if (
        isinstance(differential_exit_code, int)
        and differential_exit_code != 0
        and not force_document
    ):
        print(
            "Skipping document stage because exported-library differential "
            f"exited with code {differential_exit_code}. Export and differential "
            "artifacts are ready for diagnosis; pass --force-document to rewrite "
            "guides anyway.",
            flush=True,
        )
        return

    run_document_stage(config, timings=timings)


def export_generated_package(
    config: PipelineConfig,
    *,
    no_cache: bool = False,
    force_rebuild: bool = False,
) -> None:
    """Write the generated package under dist/ through the validate stage."""
    run_pipeline(
        config,
        stop_after_stage="validate",
        no_cache=no_cache,
        force_rebuild=force_rebuild,
    )


def main(argv: Sequence[str] | None = None) -> None:
    configure_logging()
    parser = argparse.ArgumentParser(description="Run the extraction pipeline.")
    stop_group = parser.add_mutually_exclusive_group()
    stop_group.add_argument(
        "--stop-after-stage",
        choices=PIPELINE_STAGES,
        default=None,
        help=(
            "Run pipeline stages through the named stage and exit. "
            f"Stages in order: {', '.join(PIPELINE_STAGES)}."
        ),
    )
    stop_group.add_argument(
        "--extract-graph",
        action="store_true",
        help="Alias for --stop-after-stage extract.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help=(
            "Bypass on-disk graph, projection, series-resolution, series-derived, "
            "bindings-validation, codegen, cluster, refactored-internals, and "
            "exported-library differential caches for this run."
        ),
    )
    parser.add_argument(
        "--force-document",
        action="store_true",
        help=(
            "Run the document stage even when exported-library differential "
            "finished with a non-zero exit code."
        ),
    )
    add_variation_mode_argument(parser)
    add_clustering_mode_argument(parser)
    args = parser.parse_args(list(argv) if argv is not None else None)

    config = apply_clustering_mode_cli_override(
        apply_variation_mode_cli_override(load_pipeline_config(), args.variation_mode),
        args.clustering_mode,
    )
    validate_pipeline_config(config)
    activate_pipeline_config(config)

    stop_after_stage: PipelineStageName = "document"
    if args.extract_graph:
        stop_after_stage = "extract"
    elif args.stop_after_stage is not None:
        stop_after_stage = cast(PipelineStageName, args.stop_after_stage)

    run_pipeline(
        config,
        stop_after_stage=stop_after_stage,
        no_cache=args.no_cache,
        force_document=args.force_document,
    )


if __name__ == "__main__":
    main()
