"""Tests for the series-graph viewer: generic input editors and a single force layout."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_ASSETS = REPO_ROOT / "templates/series-graph/assets/graph"
SERIES_PANEL_JS = GRAPH_ASSETS / "series-panel.js"


def _call(function: str, *args: Any) -> Any:
    """Call ``SeriesGraphPanel.<function>(*args)``; a thrown Error becomes ``{"error": msg}``."""
    node = shutil.which("node")
    assert node is not None, "node is required to test the graph viewer JS"
    script = (
        f"const P = require({json.dumps(str(SERIES_PANEL_JS))});"
        "const args = JSON.parse(process.argv[1]);"
        "let out;"
        f"try {{ out = {{ value: P.{function}(...args) }}; }}"
        "catch (err) { out = { error: err.message }; }"
        "process.stdout.write(JSON.stringify(out));"
    )
    result = subprocess.run(
        [node, "-e", script, json.dumps(list(args))],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def _value(function: str, *args: Any) -> Any:
    out = _call(function, *args)
    assert "error" not in out, out
    return out.get("value")


def _error(function: str, *args: Any) -> str:
    out = _call(function, *args)
    assert "error" in out, out
    return out["error"]


def _selected(html: str) -> list[str]:
    return re.findall(r'<option value="([^"]*)" selected', html)


_REGION = {
    "id": "region",
    "role": "input",
    "kind": "enum",
    "keys": [None],
    "options": ["North", "South"],
}
_MODE = {
    "id": "mode",
    "role": "input",
    "kind": "enum_int",
    "keys": [None],
    "options": [1, 2, 3],
    "optionLabels": {"1": "Low", "2": "Mid", "3": "High"},
}
_YEAR = {
    "id": "start_year",
    "role": "input",
    "kind": "int",
    "keys": [None],
    "domain": {"min": 1, "max": 5},
}
_RATE = {"id": "rate", "role": "input", "kind": "float", "keys": [None]}
_PATH = {"id": "path", "role": "input", "kind": "year_map", "keys": [2024, 2025]}


# --- editors key on series.id -------------------------------------------------


def test_enum_editor_selects_the_series_own_value() -> None:
    assert _selected(_value("editorHtml", _REGION, "South")) == ["South"]


def test_enum_int_editor_selects_the_series_own_value() -> None:
    html = _value("editorHtml", _MODE, 2)

    assert _selected(html) == ["2"]
    assert ">Mid</option>" in html


def test_enum_edit_rejects_unknown_option_generically() -> None:
    assert _error("parseEdit", _REGION, "East") == "Invalid option"
    assert _error("parseEdit", _MODE, "7") == "Invalid option"


def test_enum_edits_parse_to_the_option_type() -> None:
    assert _value("parseEdit", _REGION, "North") == "North"
    assert _value("parseEdit", _MODE, "3") == 3


def test_int_editor_shows_the_series_own_value() -> None:
    assert 'value="4"' in _value("editorHtml", _YEAR, 4)


def test_int_edit_enforces_domain() -> None:
    assert _value("parseEdit", _YEAR, "5") == 5
    assert _error("parseEdit", _YEAR, "6") == "Out of range"
    assert _error("parseEdit", _YEAR, "2.5") == "Out of range"


def test_int_without_domain_does_not_crash() -> None:
    series = {key: value for key, value in _YEAR.items() if key != "domain"}

    assert 'value="12"' in _value("editorHtml", series, 12)
    assert _value("parseEdit", series, "-40") == -40


def test_scalar_float_uses_a_number_input() -> None:
    html = _value("editorHtml", _RATE, 0.25)

    assert 'type="number"' in html
    assert 'step="any"' in html
    assert 'value="0.25"' in html
    assert "comma-separated" not in html


def test_scalar_float_edit_parses_a_number() -> None:
    assert _value("parseEdit", _RATE, "2.5") == 2.5
    assert _error("parseEdit", _RATE, "abc") == "Invalid number"


def test_scalar_float_edit_enforces_an_optional_domain() -> None:
    series = {**_RATE, "domain": {"min": 0, "max": 1}}

    assert _error("parseEdit", series, "1.5") == "Out of range"


def test_vector_edit_without_domain_does_not_crash() -> None:
    assert _value("parseEdit", _PATH, "1, 2.5") == {"2024": 1, "2025": 2.5}


def test_vector_edit_enforces_an_optional_domain() -> None:
    series = {**_PATH, "domain": {"min": 0, "max": 2}}

    assert _error("parseEdit", series, "1, 3") == "Out of range at 2025"


def test_vector_edit_needs_one_value_per_key() -> None:
    assert _error("parseEdit", _PATH, "1") == "Expected 2 values"


def test_vector_editor_prefills_every_value_even_for_long_series() -> None:
    keys = list(range(2020, 2030))
    series = {**_PATH, "keys": keys}
    current = {str(k): i for i, k in enumerate(keys)}

    html = _value("editorHtml", series, current)

    assert 'value="0, 1, 2, 3, 4, 5, 6, 7, 8, 9"' in html


# --- per-node hint and list summaries ------------------------------------------


def test_hint_is_rendered_escaped() -> None:
    html = _value("hintHtml", {**_RATE, "hint": "Share <of> GDP & more"})

    assert "Share &lt;of&gt; GDP &amp; more" in html


def test_no_hint_renders_nothing() -> None:
    assert _value("hintHtml", _RATE) == ""


def test_short_lists_are_joined() -> None:
    assert _value("summarize", ["A1", "B1", "C1"], "cells") == "A1, B1, C1"


def test_long_lists_show_first_and_last() -> None:
    items = [f"S!A{i}" for i in range(1, 13)]

    assert _value("summarize", items, "cells") == "S!A1 … S!A12 (12 cells)"


# --- the viewer has one layout path and no workbook-specific names ------------


def _asset_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(GRAPH_ASSETS.iterdir())
        if path.suffix in {".js", ".html", ".md", ".css"}
    )


@pytest.mark.parametrize("name", ["country_name", "shock_type", "shock_year"])
def test_no_tiny_dsa_input_names_remain(name: str) -> None:
    assert name not in _asset_text()


def test_viewer_has_no_layered_layout() -> None:
    assert not (GRAPH_ASSETS / "layered-layout.js").exists()
    app = (GRAPH_ASSETS / "app.js").read_text(encoding="utf-8")
    html = (GRAPH_ASSETS / "index.html").read_text(encoding="utf-8")
    for token in (
        "computeLayers",
        "orderWithinLayers",
        "applyNeuralLayout",
        "layoutMode",
        "btn-layout",
        "layered",
    ):
        assert token not in app, token
        assert token not in html, token


def test_viewer_reports_a_missing_layout_instead_of_relaying_out() -> None:
    app = (GRAPH_ASSETS / "app.js").read_text(encoding="utf-8")

    assert 'console.warn("layout.json' not in app
    assert "layout.json" in app
    assert "Series graph has a cycle" not in app


def test_index_loads_helpers_before_app_js() -> None:
    html = (GRAPH_ASSETS / "index.html").read_text(encoding="utf-8")

    for helper in ("config.js", "force-layout.js", "series-panel.js"):
        assert f'<script src="{helper}"></script>' in html
        assert html.index(helper) < html.index('src="app.js"')


def test_title_comes_from_config_js() -> None:
    config = (GRAPH_ASSETS / "config.js").read_text(encoding="utf-8")
    app = (GRAPH_ASSETS / "app.js").read_text(encoding="utf-8")

    assert "window.SERIES_GRAPH_TITLE" in config
    assert "SERIES_GRAPH_TITLE" in app


def test_app_uses_the_panel_helpers() -> None:
    app = (GRAPH_ASSETS / "app.js").read_text(encoding="utf-8")

    assert "const Panel = globalThis.SeriesGraphPanel;" in app
    for helper in ("editorHtml", "parseEdit", "hintHtml", "summarize"):
        assert f"Panel.{helper}(" in app, helper
