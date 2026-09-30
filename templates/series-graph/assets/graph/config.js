/**
 * Per-workbook viewer config. Override this file through dist-overlay/.
 *
 * SERIES_GRAPH_API: optional remote FormulaEvaluator API base (empty = same-origin /api).
 * Local: uv run python scripts/serve_graph_api.py
 * SERIES_GRAPH_TITLE: page and toolbar title (empty = "Dependency graph").
 */
window.SERIES_GRAPH_API = "";
window.SERIES_GRAPH_TITLE = "";
