from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence
from unittest.mock import patch

import pytest
from excel_grapher.grapher import DependencyGraph
from excel_grapher.series_bindings.types import WorkbookSeriesBindings

from src.extraction_pipeline import (
    DependencyGraphExtraction,
    build_pipeline_graph,
    extract_dependency_graph_result,
    write_dependency_graph_artifacts,
)
from src.pipeline_config import PipelineConfig
from src.semantic_labeling import SemanticLabelingSummary
from tests.fixtures.synthetic_pipeline import (
    build_synthetic_graph,
    build_synthetic_projection,
    load_synthetic_series_bindings,
    synthetic_pipeline_config,
    write_synthetic_workbook,
)
from tests.fixtures.test_state import reset_pipeline_test_state


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-skipped",
        action="store_true",
        default=False,
        help="Run tests marked with @pytest.mark.skipped.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "skipped: marks opt-in tests skipped unless --run-skipped is set",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--run-skipped"):
        return

    skip_reason = "opt-in test; pass --run-skipped to run"
    for item in items:
        if item.get_closest_marker("skipped"):
            item.add_marker(pytest.mark.skip(reason=skip_reason))


@pytest.fixture(autouse=True)
def _reset_shared_pipeline_state_after_test() -> None:
    yield
    reset_pipeline_test_state()


@pytest.fixture(scope="session")
def synthetic_workbook_path(tmp_path_factory: pytest.TempPathFactory):
    path = tmp_path_factory.mktemp("synthetic_workbook") / "workbook.xlsx"
    write_synthetic_workbook(path)
    return path


@pytest.fixture(scope="session")
def synthetic_graph(synthetic_workbook_path):
    return build_synthetic_graph(synthetic_workbook_path)


@pytest.fixture(scope="session")
def synthetic_projection(synthetic_graph):
    return build_synthetic_projection(synthetic_graph)


@pytest.fixture(scope="session")
def synthetic_series_bindings():
    return load_synthetic_series_bindings()


@pytest.fixture(scope="session")
def synthetic_pipeline_config_fixture(synthetic_workbook_path):
    return synthetic_pipeline_config(workbook_path=synthetic_workbook_path)


@dataclass(frozen=True)
class SyntheticConfiguredPipeline:
    config: PipelineConfig
    graph: DependencyGraph
    series_bindings: WorkbookSeriesBindings
    input_series: Sequence[Mapping[str, Any]]
    output_series: Sequence[Mapping[str, Any]]


@pytest.fixture(scope="session")
def synthetic_configured_pipeline(
    synthetic_pipeline_config_fixture: PipelineConfig,
) -> SyntheticConfiguredPipeline:
    stub_summary = SemanticLabelingSummary(
        labeled_cell_count=0,
        sheet_count=0,
        candidate_cells_by_sheet={},
    )
    with patch(
        "src.extraction_pipeline.label_internal_graph_cells",
        return_value=stub_summary,
    ):
        graph, series_bindings, input_series, output_series = build_pipeline_graph(
            synthetic_pipeline_config_fixture
        )
    return SyntheticConfiguredPipeline(
        config=synthetic_pipeline_config_fixture,
        graph=graph,
        series_bindings=series_bindings,
        input_series=input_series,
        output_series=output_series,
    )


@dataclass(frozen=True)
class SyntheticGraphExtractionArtifacts:
    config: PipelineConfig
    extraction: DependencyGraphExtraction
    summary: dict[str, Any]


@pytest.fixture(scope="session")
def synthetic_graph_extraction_artifacts(
    tmp_path_factory: pytest.TempPathFactory,
    synthetic_pipeline_config_fixture: PipelineConfig,
) -> SyntheticGraphExtractionArtifacts:
    output_dir = tmp_path_factory.mktemp("synthetic_graph_extraction")
    config = replace(
        synthetic_pipeline_config_fixture,
        graph_output_dir=output_dir,
    )
    stub_summary = SemanticLabelingSummary(
        labeled_cell_count=0,
        sheet_count=0,
        candidate_cells_by_sheet={},
    )
    with patch(
        "src.extraction_pipeline.label_internal_graph_cells",
        return_value=stub_summary,
    ):
        extraction = extract_dependency_graph_result(config)
        summary = write_dependency_graph_artifacts(extraction, config)
    return SyntheticGraphExtractionArtifacts(
        config=config,
        extraction=extraction,
        summary=summary,
    )
