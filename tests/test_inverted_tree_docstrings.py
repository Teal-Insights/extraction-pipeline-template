"""LLM docstring overlay for inverted-tree helpers (pipeline annotate stage)."""

from __future__ import annotations

import inspect
from pathlib import Path

from src.inverted_tree_docstrings import (
    ArgDoc,
    FunctionDocResponse,
    apply_inverted_tree_docstrings,
    render_google_docstring,
    replace_function_docstring,
)


def _mechanical_internals() -> str:
    return (
        "from __future__ import annotations\n"
        "\n"
        "def helper_series(year_labels: list[int], shock_year: int) -> tuple[int, ...]:\n"
        '    """First-level helper for bound series `helper_series`."""\n'
        "    return tuple(1 for _ in year_labels)\n"
    )


def test_replace_function_docstring_splices_google_block() -> None:
    source = _mechanical_internals()
    rendered = render_google_docstring(
        FunctionDocResponse(
            summary="Shock-year activation flags.",
            purpose="Return 1 when the year is at or after the shock year.",
            args=(
                ArgDoc(name="year_labels", description="Projection year labels."),
                ArgDoc(name="shock_year", description="First year the shock applies."),
            ),
            returns="One flag per projection year.",
        )
    )
    updated = replace_function_docstring(source, "helper_series", rendered)
    assert "First-level helper" not in updated
    assert "Shock-year activation flags." in updated
    assert "year_labels:" in updated
    assert "return tuple(1 for _ in year_labels)" in updated


def test_apply_inverted_tree_docstrings_uses_injected_generator(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "api.py").write_text(
        "from __future__ import annotations\n"
        "\n"
        "def compute_output_baseline(\n"
        "    *,\n"
        "    country_name: str,\n"
        "    growth_baseline: list[float],\n"
        ") -> tuple[float, ...]:\n"
        '    """Compute `output_baseline` from its subgraph leaf closure."""\n'
        "    return (1.0,)\n",
        encoding="utf-8",
    )
    (package / "internals.py").write_text(_mechanical_internals(), encoding="utf-8")

    calls: list[str] = []

    def generate(request) -> FunctionDocResponse:
        calls.append(request.function_name)
        names = request.parameter_names
        return FunctionDocResponse(
            summary=f"{request.function_name} summary.",
            purpose=f"{request.function_name} purpose.",
            args=tuple(ArgDoc(name=name, description=f"{name} arg.") for name in names),
            returns="Result values.",
        )

    apply_inverted_tree_docstrings(
        package_root=package,
        series_notes={},
        guide_text="Guide text.",
        generate_doc=generate,
    )

    assert "helper_series" in calls
    assert "compute_output_baseline" in calls
    internals = (package / "internals.py").read_text(encoding="utf-8")
    api = (package / "api.py").read_text(encoding="utf-8")
    assert "helper_series summary." in internals
    assert "compute_output_baseline summary." in api
    namespace: dict[str, object] = {}
    exec(compile(internals, str(package / "internals.py"), "exec"), namespace)  # noqa: S102
    helper = namespace["helper_series"]
    assert callable(helper)
    doc = inspect.getdoc(helper)
    assert doc is not None
    assert "year_labels arg." in doc


def test_apply_inverted_tree_docstrings_rejects_arg_mismatch(
    tmp_path: Path,
) -> None:
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "api.py").write_text(
        "def compute_output_baseline(*, country_name: str) -> tuple[float, ...]:\n"
        '    """Compute `output_baseline` from its subgraph leaf closure."""\n'
        "    return (1.0,)\n",
        encoding="utf-8",
    )
    (package / "internals.py").write_text("# empty\n", encoding="utf-8")

    def generate(request) -> FunctionDocResponse:
        return FunctionDocResponse(
            summary="Wrong.",
            purpose="Wrong args.",
            args=(ArgDoc(name="not_a_param", description="nope"),),
            returns="nope",
        )

    try:
        apply_inverted_tree_docstrings(
            package_root=package,
            series_notes={},
            guide_text="guide",
            generate_doc=generate,
        )
    except ValueError as error:
        assert "compute_output_baseline" in str(error)
        assert "not_a_param" in str(error)
    else:
        raise AssertionError("expected ValueError for arg mismatch")
