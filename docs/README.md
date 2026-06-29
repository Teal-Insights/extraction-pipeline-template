# Generated documentation outputs

This directory holds **generated** exploration artifacts. Do not commit graph JSON/HTML snapshots.

After extraction, write an interactive dependency graph site to `dependency-graph/` using `src.dependency_graph_viz.write_dependency_graph_site`, then serve it locally:

```bash
uv run python -m http.server 8000 --directory docs/dependency-graph
```

The archived literate notebook that informed the README workflow lives in [archive/extraction-pipeline.qmd](../archive/extraction-pipeline.qmd).
