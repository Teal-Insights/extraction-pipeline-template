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

This template ships a **stub harness** at
[`differential_test_exported_library.py`](differential_test_exported_library.py).
Replace it with workbook-specific logic:

1. **Scenario sweep** — representative input combinations (single-axis sweeps plus a few multi-axis combos).
2. **Cell mappings** — mirror your `bindings/*.bindings.yaml` addresses for Excel writes and output reads.
3. **Input adaptation** — one `Inputs` dataclass converted to Excel cell dict and Records-shaped `set_*` calls.
4. **Parity report** — CSV (one row per cell comparison) and TXT summary with pass rate, first divergence, and failure list.

Commit reference reports under `data/differential/exported_library/` after a passing Windows sweep. The export step copies harness, workbook fixture, and reports into `dist/tests/`.

## Run

Microsoft Excel must be installed locally — `xlwings` drives it through COM automation.

```bash
# Extraction repo (after implementing the harness and exporting dist/)
uv run python tests/differential/differential_test_exported_library.py

# Exported dist project (Windows + Excel)
uv run --project dist --group validation python tests/differential_test_exported_library.py --layout exported
```

Exit codes: **`0`** all comparisons pass, **`1`** any failure, **`2`** prerequisite missing or harness not implemented.

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
