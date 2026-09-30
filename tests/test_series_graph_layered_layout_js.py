"""Tests for the viewer's ``layered-layout.js``, which spaces layered columns by box width."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GRAPH_ASSETS = REPO_ROOT / "templates/series-graph/assets/graph"
LAYERED_LAYOUT_JS = GRAPH_ASSETS / "layered-layout.js"

_ORIGIN = 140.0
_GAP = 80.0


def _column_xs(columns: list[list[str]], widths: dict[str, float]) -> list[float]:
    node = shutil.which("node")
    assert node is not None, "node is required to test the graph viewer JS"
    script = (
        f"const L = require({json.dumps(str(LAYERED_LAYOUT_JS))});"
        "const o = JSON.parse(process.argv[1]);"
        "process.stdout.write(JSON.stringify(L.columnXs(o)));"
    )
    options: dict[str, Any] = {
        "columns": columns,
        "widths": widths,
        "originX": _ORIGIN,
        "gap": _GAP,
    }
    result = subprocess.run(
        [node, "-e", script, json.dumps(options)],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_adjacent_wide_columns_keep_the_gap() -> None:
    # tiny-dsa: two 360 px five-value paths in adjacent layers overlapped at 280 px.
    columns = [["in"], ["path_internal"], ["path_output"]]
    widths = {"in": 168.0, "path_internal": 360.0, "path_output": 360.0}

    xs = _column_xs(columns, widths)

    assert xs[0] == pytest.approx(_ORIGIN)
    assert xs[1] - xs[0] == pytest.approx(168.0 / 2 + _GAP + 360.0 / 2)
    assert xs[2] - xs[1] == pytest.approx(360.0 / 2 + _GAP + 360.0 / 2)


def test_column_width_is_its_widest_box() -> None:
    columns = [["narrow", "wide"], ["next"]]
    widths = {"narrow": 168.0, "wide": 300.0, "next": 200.0}

    xs = _column_xs(columns, widths)

    assert xs[1] - xs[0] == pytest.approx(300.0 / 2 + _GAP + 200.0 / 2)


def test_empty_column_takes_only_the_gap() -> None:
    # The cycle fallback lays out role columns, and a role may have no series.
    columns = [["a"], [], ["b"]]
    widths = {"a": 200.0, "b": 200.0}

    xs = _column_xs(columns, widths)

    assert xs[1] - xs[0] == pytest.approx(100.0 + _GAP)
    assert xs[2] - xs[1] == pytest.approx(_GAP + 100.0)


def test_app_loads_layered_layout_before_app_js() -> None:
    html = (GRAPH_ASSETS / "index.html").read_text(encoding="utf-8")

    assert '<script src="layered-layout.js"></script>' in html
    assert html.index("layered-layout.js") < html.index('src="app.js"')


def test_app_no_longer_spaces_columns_by_a_constant() -> None:
    app = (GRAPH_ASSETS / "app.js").read_text(encoding="utf-8")

    assert "LAYER_GAP_X" not in app
    assert "SeriesGraphLayeredLayout.columnXs" in app
