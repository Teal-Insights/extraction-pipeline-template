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

## What to implement

The harness at [`differential_test_exported_library.py`](differential_test_exported_library.py)
loads paths from `workbook_config.py`, compares Excel against the exported package,
and writes parity reports. **Scenario definitions are workbook-specific** — implement
the hooks at the bottom of that module:

1. **`build_scenarios()`** — representative input combinations.
2. **`output_cell_labels()`** and **`output_ranges()`** — mirror output bindings.
3. **`inputs_for_excel()`** — map each scenario to Excel cell writes.
4. **`apply_inputs_to_mvp()`** — map each scenario to Records-shaped `set_*` calls.

Commit reference reports under `data/differential/exported_library/` after a passing Windows sweep. The export step copies harness, workbook fixture, and reports into `dist/tests/`.

## Run

Microsoft Excel must be installed locally — `xlwings` drives it through COM automation.

```bash
# Extraction repo (after implementing the harness and exporting dist/)
uv run python tests/differential/differential_test_exported_library.py

# Exported dist project (Windows + Excel)
uv run --project dist --group validation python tests/differential_test_exported_library.py --layout exported
```

Exit codes: **`0`** all comparisons pass, **`1`** any failure, **`2`** prerequisite missing or scenarios not configured.

## Optional: graph-oracle harness

You may also add a sibling script that compares Excel against an in-memory
`FormulaEvaluator` over the extracted graph (same `constraints` as
`workbook_config.py`). That validates extraction fidelity before codegen.
The exported-library harness validates the artifact callers consume.

## Output locations

| Run context | Reports |
|---|---|
| Extraction repo | `data/differential/exported_library/parity_report.{csv,txt}` |
| Exported dist (local rerun) | `dist/tests/results/local/` |
| Exported dist (shipped reference) | `dist/tests/results/reference/` |

Refresh committed reference reports whenever the workbook, bindings, constraints, or scenario sweep changes.
