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

Copy the preview CSS from the Tiny DSA export
(`exports/py-tiny-dsa/user_guide/index.qmd` `include-in-header`) or the
styled block under `## Interactive dependency graph` there, renaming the
`tiny-dsa-graph-*` class prefix to `series-graph-*` if you prefer.

## HTML embed

Link + iframe pointing at `assets/graph/index.html` (fullscreen) and
`assets/graph/index.html?preview=1` (docs paint). Resolve relative bases for
both `/user-guide/` and site-root publishes (see Tiny DSA `index.qmd` script).

## Local FormulaEvaluator API

From the exported `dist/` project:

```bash
uv sync --group graph
uv run python scripts/serve_graph_api.py
# http://127.0.0.1:8765/
```

Author `{package}/graph_schema.py` (`NODES` / `EDGES`) before the viz is useful.
Reference: `examples/tiny_dsa_graph_schema.py` and
`templates/series-graph/README.md` in this pipeline repo.
