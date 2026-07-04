# Artifacts catalog

Generated pipeline artifacts live under `artifacts/`. Do not commit graph JSON/HTML snapshots.

## `dependency-graph/`

Written by the extract-only stage (`uv run python -m src.extraction_pipeline --extract-graph`).

| File | Description |
|---|---|
| `index.html` | Interactive Cytoscape explorer (Graphviz preset layout) |
| `dependency-graph.json` | Cytoscape preset payload for the explorer |
| `extraction-summary.json` | Machine-readable extraction metrics and output paths |

### `extraction-summary.json` schema (version `1.0.0`)

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Summary schema version (`1.0.0`) |
| `node_count` | integer | Cells in the dependency graph |
| `edge_count` | integer | Directed dependency edges |
| `leaf_count` | integer | Graph leaves (inputs/constants) |
| `provenance_edge_count` | integer | Edges with dependency provenance metadata |
| `elapsed_seconds` | number | Wall-clock seconds for the extract stage |
| `stage_timings` | object | Per-stage seconds keyed by stage name |
| `output_paths` | object | Repo-relative paths for `output_dir`, `index_html`, `dependency_graph_json`, and `extraction_summary_json` |

Serve locally:

```bash
uv run python -m http.server 8000 --directory artifacts/dependency-graph
```

Open `http://localhost:8000/`.
