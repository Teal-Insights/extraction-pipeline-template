# Differential testing

**Differential testing** feeds identical inputs to two oracles and compares outputs.
Here the golden-master oracle is Microsoft Excel (via `xlwings`), and the system
under test is either the in-memory dependency graph or the exported standalone
library.

| Term | Meaning |
|---|---|
| **Golden master** | Trusted Excel workbook recalculated through COM automation |
| **MVP oracle** | Python reimplementation (graph evaluator or exported package) |
| **Absolute tolerance (`atol`)** | Maximum allowed numeric difference; use `1e-6` unless the model needs looser bounds |

## Two harnesses

Run the **graph** differential before export to validate extraction fidelity.
Run the **exported-library** differential after export to validate the artifact
callers consume.

| Harness | SUT | When |
|---|---|---|
| [`differential_test_graph.py`](differential_test_graph.py) | In-memory `FormulaEvaluator` over the extracted graph | Before / alongside extraction review |
| [`differential_test_exported_library.py`](differential_test_exported_library.py) | Generated standalone package public API | After `uv run python -m src.extraction_pipeline` |

Both harnesses import shared scenario types from
[`differential_types.py`](differential_types.py) (`Scenario`, optional `Axis` /
`AxisPoint`, and `ATOL`). Workbook-specific hooks live at the bottom of each harness
module.

### Graph harness hooks

1. **`build_scenarios()`** or **`build_axes()`** — representative input combinations.
2. **`output_cell_labels()`** — mirror output bindings as `(label, address)` pairs.
3. **`inputs_for_excel()`** — map each scenario to Excel cell writes.

The graph harness also reports input cells absent from the extracted graph —
itself a differential signal about extraction coverage.

### Exported-library harness hooks

1. **`build_scenarios()`** — representative input combinations.
2. **`output_cell_labels()`** and **`output_ranges()`** — mirror output bindings.
3. **`inputs_for_excel()`** — map each scenario to Excel cell writes.
4. **`apply_inputs_to_mvp()`** — map each scenario to Records-shaped `set_*` calls.

Commit reference reports under `data/differential/graph/` and
`data/differential/exported_library/` after passing Windows sweeps. The export
step copies the exported-library harness, workbook fixture, and reports into
`dist/tests/`.

## Run

Microsoft Excel must be installed locally — `xlwings` drives it through COM automation.

```bash
# Graph oracle (extraction repo — run before export)
uv run python -m tests.differential.differential_test_graph

# Exported library (extraction repo, after export)
uv run python -m tests.differential.differential_test_exported_library

# Exported dist project (Windows + Excel)
uv run --project dist --group validation python -m tests.differential.differential_test_exported_library --layout exported
```

Exit codes: **`0`** all comparisons pass, **`1`** any failure, **`2`** prerequisite missing or scenarios not configured.

## Output locations

| Harness | Reports |
|---|---|
| Graph (extraction repo) | `data/differential/graph/differential_report.{csv,txt}` |
| Exported library (extraction repo) | `data/differential/exported_library/parity_report.{csv,txt}` |
| Exported dist (local rerun) | `dist/tests/results/local/` |
| Exported dist (shipped reference) | `dist/tests/results/reference/` |

Refresh committed reference reports whenever the workbook, bindings, constraints, or scenario sweep changes.
