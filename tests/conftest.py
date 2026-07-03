import pytest

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
