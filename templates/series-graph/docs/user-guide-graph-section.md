# Interactive dependency graph (landing-page fragment)

Add a short **Interactive dependency graph** section on `user_guide/index.qmd`
(or the site landing page). Do **not** write a long topology blurb under the
heading — the viz is the explanation.

## Quarto front matter

Declare resources so the UI ships with the site:

```yaml
resources:
  - ../assets/graph/**
```

Style the embed with a small `include-in-header` block using a
`series-graph-*` class prefix.

## HTML embed

Link + iframe pointing at `assets/graph/index.html` (fullscreen) and
`assets/graph/index.html?preview=1` (docs paint). Resolve relative bases for
both `/user-guide/` and site-root publishes.

## Local FormulaEvaluator API

From the exported `dist/` project:

```bash
uv sync --group graph
uv run python scripts/serve_graph_api.py
# http://127.0.0.1:8765/
```

Author `{package}/graph_schema.py` (`NODES` / `EDGES`) before the viz is useful.
Reference: `examples/reference_graph_schema.py` and
`templates/series-graph/README.md` in this pipeline repo.
