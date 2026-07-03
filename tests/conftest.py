import pytest

from tests.fixtures.synthetic_pipeline import (
    build_synthetic_graph,
    build_synthetic_projection,
    load_synthetic_series_bindings,
    synthetic_pipeline_config,
)


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


@pytest.fixture(scope="session")
def synthetic_graph():
    return build_synthetic_graph()


@pytest.fixture(scope="session")
def synthetic_projection(synthetic_graph):
    return build_synthetic_projection(synthetic_graph)


@pytest.fixture(scope="session")
def synthetic_series_bindings():
    return load_synthetic_series_bindings()


@pytest.fixture(scope="session")
def synthetic_pipeline_config_fixture():
    return synthetic_pipeline_config()

