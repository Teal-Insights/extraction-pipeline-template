# Interactive dependency graph

Fullscreen Cytoscape explorer for the exported package. Values recompute via
**excel-grapher FormulaEvaluator** (and optionally the exported `Model`).

| File | Role |
|------|------|
| `index.html` | Shell UI; `?preview=1` hides chrome |
| `config.js` | Per-workbook config: `SERIES_GRAPH_API` (empty = same-origin), `SERIES_GRAPH_TITLE` |
| `app.js` | Cytoscape wiring; `GET /api/graph`, `POST /api/evaluate` |
| `bootstrap.json` | Optional static snapshot when the API is offline |
| `force-layout.js` | Fits `layout.json` to node boxes (scale, then separate vertically) |
| `series-panel.js` | Side-panel input editors (keyed on `series.id`), hints, list summaries |
| `layout.json` | Pipeline-written excel-grapher force layout; the only layout (missing → error) |
| `style.css` | Layout and role colors |
| `API.md` | Full HTTP contract the UI expects |

## Run locally

From the exported package root (`dist/`):

```bash
uv sync --group graph
uv run python scripts/serve_graph_api.py
# http://127.0.0.1:8765/
```

Author `{package}/graph_schema.py` (`NODES` / `EDGES`) before the viz is useful.
A downstream `dist-overlay/` needs only `assets/graph/config.js`,
`{package}/graph_schema.py` and `assets/graph/bootstrap.json`; do not fork
`app.js` or `index.html`. Nodes may carry an optional `hint` for the side panel.
See `examples/reference_graph_schema.py` and `../README.md`.

```bash
uv run python scripts/write_graph_bootstrap.py
uv run python scripts/check_graph_eval.py
```
