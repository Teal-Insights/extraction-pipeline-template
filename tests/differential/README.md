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
`AxisPoint`, and `ATOL`) and input-isolation helpers from
[`differential_scenario_inputs.py`](differential_scenario_inputs.py). Golden-master cell reads go through
[`differential_excel.py`](differential_excel.py), which sets xlwings
`err_to_str=True` so Excel error cells (`#VALUE!`, `#N/A`, …) are returned as
strings rather than `None`. Workbook-specific hooks live at the bottom of each
harness module.

### Address keys

`excel-grapher` stores graph keys in **canonical** form. Sheets whose names
contain spaces, hyphens, or apostrophes are quoted (e.g. `'Discrete Risks'!H2`).
Human-authored config (`CONSTRAINTS`, scenario matrices, bindings) often uses
unquoted spellings (`Discrete Risks!H2`). Both refer to the same cell, but naive
string equality against graph keys fails.

At harness boundaries, import from `excel_grapher.core.address_keys`:

| Helper | Use when |
|--------|----------|
| `normalize_key(address)` | Comparing to `leaf_keys()` / `formula_keys()`, calling `graph.set_node_value()`, `graph.get_node()`, `FormulaEvaluator.evaluate()` |
| `parse_address(normalize_key(address))` | Driving Excel via xlwings/COM (sheet name + A1 coordinate) |

Do **not** re-implement quoting rules or use `split("!", 1)` on sheet-qualified
addresses inside harness code. Config authors may keep unquoted addresses;
normalization belongs at the boundary.

### Graph harness hooks

1. **`build_scenarios()`** or **`build_axes()`** — representative input combinations.
2. **`output_cell_labels()`** — mirror output bindings as `(label, address)` pairs.
3. **`inputs_for_excel()`** — map each scenario to Excel cell writes.

Before each scenario the graph harness restores every input cell in the union of
all scenario writes to its workbook baseline, then applies that scenario's
declared overrides. Undeclared cells therefore do not inherit values from prior
scenarios.

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

# With matched-error audit (passing error cells listed for scenario review)
uv run python -m tests.differential.differential_test_graph --warn-on-error-values

# Exported library (extraction repo, after export)
uv run python -m tests.differential.differential_test_exported_library

# Exported dist project (Windows + Excel)
uv run --project dist --group validation python -m tests.differential.differential_test_exported_library --layout exported
```

Pass `--warn-on-error-values` on either harness to list comparisons where both
oracles returned the same Excel error code. These still count as passes, but may
indicate unintended scenario setup unless the scenario sets
`expects_error_values=True`.

Exit codes: **`0`** all comparisons pass, **`1`** any failure, **`2`** prerequisite missing or scenarios not configured.

## Golden-master conformance

The comparison ladder, report schema, and acceptance bar are defined in
[`technical_standard.md`](../../technical_standard.md) (§1–§3 and the conformance
checklist at the end). Unit tests in
[`tests/test_differential_harness.py`](../test_differential_harness.py) lock the
exported-library harness helpers (`compare_cell`, `crash_comparisons`,
`write_csv_report`, `write_txt_summary`) to that standard on every PR — no Excel
required.

CSV columns use `excel_value` / `mvp_value` as aliases for the standard's
`golden_value` / `sut_value` terminology.

## Output locations

| Harness | Reports |
|---|---|
| Graph (extraction repo) | `data/differential/graph/differential_report.{csv,txt}` |
| Exported library (extraction repo) | `data/differential/exported_library/parity_report.{csv,txt}` |
| Exported dist (local rerun) | `dist/tests/results/local/` |
| Exported dist (shipped reference) | `dist/tests/results/reference/` |

Refresh committed reference reports whenever the workbook, bindings, constraints, or scenario sweep changes.
