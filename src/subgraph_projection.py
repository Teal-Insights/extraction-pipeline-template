from __future__ import annotations

from pathlib import Path

from excel_grapher.exporter import OptimalCompression, ProjectionResult
from excel_grapher.grapher.graph import DependencyGraph
from excel_grapher.series_bindings.types import WorkbookSeriesBindings

from src.projection_cache import get_or_build_refactor_projection
from src.stage_timings import PipelineTimings, record_cache_result


def build_refactor_projection(
    graph: DependencyGraph,
    *,
    series_bindings: WorkbookSeriesBindings | None = None,
    bindings_workbook: Path | str | None = None,
    graph_cache_key: str | None = None,
    no_cache: bool = False,
    force_rebuild: bool = False,
    cache_dir: Path | None = None,
    timings: PipelineTimings | None = None,
) -> ProjectionResult:
    """Build the provenance-aware projection used for refactor-oriented exports.

    Pass ``series_bindings`` / ``bindings_workbook`` so OptimalCompression
    preserves series-bound addresses (including internals) instead of inlining
    singleton formula transit cells.
    """
    if series_bindings is not None and bindings_workbook is None:
        raise ValueError("bindings_workbook is required when series_bindings is set")
    if graph_cache_key is None:
        return OptimalCompression(
            series_bindings=series_bindings,
            bindings_workbook=bindings_workbook,
        ).project(graph)
    result = get_or_build_refactor_projection(
        graph,
        graph_cache_key=graph_cache_key,
        series_bindings=series_bindings,
        bindings_workbook=bindings_workbook,
        no_cache=no_cache,
        force_rebuild=force_rebuild,
        cache_dir=cache_dir,
    )
    record_cache_result(timings, "projection", result)
    return result.projection
