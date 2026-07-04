from __future__ import annotations

from typing import Any, Iterable, Literal, Mapping, Sequence, cast, get_args, get_origin

from excel_grapher.core.cell_types import normalize_cell_type_env_key
from excel_grapher.grapher import (
    DependencyGraph,
    DynamicRefConfig,
    create_dependency_graph,
)
from excel_grapher.exporter import CodeGenerator
from excel_grapher.series_bindings import (
    derive_input_series,
    derive_output_series,
    load_series_bindings,
    validate_series_bindings,
)
from excel_grapher.series_bindings.types import WorkbookSeriesBindings

from src.docstring_callback import configure_docstring_callback
from src.dependency_graph_viz import series_cell_keys
from src.export_validation_assets import export_validation_assets
from src.pipeline_config import (
    PipelineConfig,
    load_pipeline_config,
    validate_pipeline_config,
)
from src.pipeline_context import activate_pipeline_config
from src.qmd_python_validation import (
    DOCUMENTATION_BASELINE_DEV_DEPS,
    VALIDATION_BASELINE_DEV_DEPS,
    render_dist_pyproject_toml,
    write_dist_readme,
)
from src.semantic_labeling import label_internal_graph_cells
from src.subgraph_projection import build_refactor_projection

SeriesResolutionList = Sequence[Mapping[str, Any]]


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
) -> tuple[
    DependencyGraph,
    WorkbookSeriesBindings,
    SeriesResolutionList,
    SeriesResolutionList,
]:
    series_bindings: WorkbookSeriesBindings = load_series_bindings(config.bindings_path)
    dynamic_ref_config = DynamicRefConfig.from_constraints(config.constraints, {})
    graph = create_dependency_graph(
        config.workbook_path,
        list(config.targets),
        load_values=True,
        dynamic_refs=dynamic_ref_config,
        capture_dependency_provenance=True,
    )

    binding_validation_report = validate_series_bindings(
        graph,
        series_bindings,
        workbook=config.workbook_path,
    )
    if not binding_validation_report["ok"]:
        raise ValueError(
            f"Invalid series bindings: {binding_validation_report['issues']!r}"
        )

    input_series = cast(
        SeriesResolutionList,
        derive_input_series(graph, series_bindings, workbook=config.workbook_path),
    )
    output_series = cast(
        SeriesResolutionList,
        derive_output_series(graph, series_bindings, workbook=config.workbook_path),
    )

    label_internal_graph_cells(
        graph=graph,
        workbook_path=config.workbook_path,
        input_cells=series_cell_keys(input_series),
        target_cells=series_cell_keys(output_series),
        concept_scheme=series_bindings["concept_scheme"],
    )

    leaf_classification = classify_leaves_from_constraints(
        config.constraints, graph.leaf_keys()
    )
    graph.leaf_classification = leaf_classification

    return graph, series_bindings, input_series, output_series


def export_generated_package(config: PipelineConfig) -> None:
    """Write the generated package under dist/."""
    graph, series_bindings, _input_series, _output_series = build_pipeline_graph(config)
    refactor_projection = build_refactor_projection(graph)
    callback_name = configure_docstring_callback(config)

    with CodeGenerator(refactor_projection) as generator:
        modules = generator.generate_modules(
            list(config.targets),
            series_bindings=series_bindings,
            bindings_workbook=config.workbook_path,
            series_docstring_callback=callback_name,
            docstring_renderer="google",
        )

    package_root = config.package_root
    package_root.mkdir(parents=True, exist_ok=True)

    generated_module_names = frozenset(
        {"__init__.py", "api.py", "data.py", "runtime.py", "internals.py"}
    )

    for filepath, code in modules.items():
        output_path = package_root / filepath
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(code, encoding="utf-8", newline="\n")

    for stale_module in generated_module_names:
        stale_path = config.dist_root / stale_module
        if stale_path.is_file():
            stale_path.unlink()

    gitignore_content = """
*.egg-info/
*.pyc
__pycache__/
.venv/
_validate_user_guide_cells.py
tests/results/local/
"""

    (config.dist_root / ".gitignore").write_text(gitignore_content, encoding="utf-8")
    (config.dist_root / "pyproject.toml").write_text(
        render_dist_pyproject_toml(
            dev_dependencies=list(DOCUMENTATION_BASELINE_DEV_DEPS),
            validation_dependencies=list(VALIDATION_BASELINE_DEV_DEPS),
            metadata=config.dist_metadata,
        ),
        encoding="utf-8",
    )
    write_dist_readme(config.dist_root, metadata=config.dist_metadata)

    export_validation_assets(config=config)

    from src.formula_clustering import cluster_graph_formulas
    from src.internals_refactor import refactor_internals_all_clusters

    formula_clusters = cluster_graph_formulas(refactor_projection)
    refactor_internals_all_clusters(
        refactor_projection,
        formula_clusters,
        internals_path=package_root / "internals.py",
        source_graph=graph,
        bindings_path=config.bindings_path,
        workbook_path=config.workbook_path,
    )


def main() -> None:
    config = load_pipeline_config()
    validate_pipeline_config(config)
    activate_pipeline_config(config)
    export_generated_package(config)
    from src.documentation_pipeline import run_documentation_pipeline

    run_documentation_pipeline(config)


if __name__ == "__main__":
    from src.logging_config import configure_logging

    configure_logging()
    main()
