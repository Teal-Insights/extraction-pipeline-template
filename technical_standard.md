# Technical Standard: Good Extraction

This standard defines when an Excel-to-Python extraction is *good enough to ship*. It covers configure → extract → export → refactor.

---

## Summary

A good extraction produces a distributable Python library whose **public API is semantic and economist-facing**, whose **dependency graph is complete and constraint-resolved**, and whose **generated code is mechanically traceable** back to workbook cells. Internals must be **organized into functions that map to macrofinance computations**, not individual Excel workbook cells. The library must be **runnable without Excel** but must produce the **same outputs as the original workbook for the same inputs**. The library must be documented with **detailed docstrings, a polished website, and a GitHub README**.

---

## Stage gates

### 1. Configure

| Criterion | Pass condition |
|---|---|
| **Targets declared** | Every published output is a named target (range name or sheet-qualified address) driving target-driven graph extraction. |
| **Series bindings authored** | `bindings/inputs.bindings.yaml` and `bindings/outputs.bindings.yaml` exist, use `schema_version: 1.2.0`, and declare one logical scalar/series/table per public I/O function. |
| **Bindings validated against graph** | `validate_series_bindings(...)` reports `ok`; input bindings overlap graph leaves, output bindings overlap target nodes. |
| **Dynamic refs resolved** | All `OFFSET` / `INDEX` / `MATCH` / `CHOOSE` dependencies are resolved via `DynamicRefConfig.from_constraints(...)` without `DynamicRefError`. |
| **Every mutable leaf is bound** | Each leaf classified as `input` appears in `inputs.bindings.yaml`; unbound mutable leaves fail the pipeline. |
| **Constants distinguished from inputs** | Single-value `Literal[...]` constraints mark lookup/structural data; range constraints mark user-editable inputs. |
| **Constraints cover all leaves** | Every graph leaf has a typed constraint (`Literal`, `Between`, `RealBetween`, etc.) for codegen, testing, and documentation. |

### 2. Extract

| Criterion | Pass condition |
|---|---|
| **Graph builds cleanly** | `create_dependency_graph(..., load_values=True, dynamic_refs=..., capture_dependency_provenance=True)` succeeds. |
| **Graph is inspectable** | DAG from outputs to inputs; manual review confirms expected sheets, no spurious nodes, no missing shock/engine paths. |
| **Provenance captured** | `capture_dependency_provenance=True` so later compression/refactor projections are safe and auditable. |
| **Series derive cleanly** | `derive_input_series` / `derive_output_series` resolve every binding to concrete cell addresses. |
| **Dependency chains pass AI-powered spot-checking** | `graph.dependency_chains` passes a series of LLM-powered spot-checks that confirm graph edges correctly capture formula dependencies. |

### 3. Export

| Criterion | Pass condition |
|---|---|
| **Leaf classification attached** | Before codegen, every graph leaf is classified `input` or `constant` and attached to the graph. |
| **Records-shaped public API** | Codegen emits `make_context()`, `set_*` input setters, and `compute_*` output functions from series bindings—not raw cell writers. |
| **Inputs validated at runtime** | Setters validate record shape and key matching; domain/units prose belongs in docstrings, not implied runtime validation beyond what codegen emits. |
| **Domain-language identifiers** | Public functions **and** internal functions use macrofinance vocabulary (`growth_baseline`, `output_delta`), not workbook coordinates (`U24`, `OFFSET_RANGE_3`). |
| **Concise/readable code** | Internal formula cell groups are collapsed to functions, rewritten with macrofinance semantics, parameterized by economic concepts, and reused to reduce code duplication. |
| **Pandas/Polars compatible** | Public functions can accept (and ideally return) pandas or polars `DataFrame`s as inputs as well as scalars, sequences, and `Records` lists. |
| **Docstrings on public API** | Every `set_*` and `compute_*` has a docstring: deterministic fields from the binding contract, LLM-authored prose from a registered docstring callback grounded in the human guide. |
| **Distributable package** | Export writes `dist/<package>/` with `api.py`, runtime modules, `pyproject.toml`, and README; package imports without the extraction repo on `PYTHONPATH`. |
| **Validation bundle shipped** | Differential harness, workbook fixture, and reference parity reports (with 100% passing scores) are exported under `dist/tests/`. |
| **Documentation website published** | `dist/website/` contains a polished website with detailed macrofinance explanations and usage instructions and examples. |

---

## Acceptance bar

An extraction meets this standard when:

1. All stage-gate checks above pass programmatically or by documented human review where judgment is required (graph completeness).
2. The exported library runs a representative scenario end-to-end using only the semantic API.
3. A macrofinance domain expert can configure inputs and read outputs without opening the workbook.
4. The extraction repo documents *decisions* (targets, binding choices, constraint domains, constant vs input classification) clearly enough that an agent or teammate can replicate the process on a new workbook.

Golden-master parity (100% pass rate, precision policy, first-divergence reporting) is required for release.

---

## Known gaps/footguns

- **Binding authoring needs a scaling strategy:** Larger workbooks need a structured discovery workflow (logical tables → series catalog → graph cross-check); the prompt pattern in the pipeline doc is the reference.
- **User override of formula cells is not currently allowed**: Currently we're enforcing that all input cells must be leaf nodes. However, there's at least one user-editable cell in the LIC DSF that is not a leaf node, so we will need to relax this constraint for the LIC DSF extraction.
- **Synchronous LLM API calls slow down the pipeline**: Currently we're calling LLMs synchronously at each stage of the pipeline. For large workbooks, we will need to parallelize LLM calls to speed up the pipeline. (In some cases, sequencing is important, so we'll have to do this intelligently.)
- **LLM-authored configs and docstrings are not currently validated**: We may want to run some evals over the AI-generated series bindings and docstrings to make sure this is really the API shape we want.
- **Context-passing is a bit unergonomic**: We're currently requiring the user to pass the context object to every function. This sits uncomfortably between functional and object-oriented programming paradigms, so we should commit to one or the other (e.g., attach public functions to the context object as methods).
- **Error handling is insufficiently Pythonic**: Our Python runtime replicates Excel error-handling semantics. In Excel, errors in "internals" are made visible via error codes like `#N/A` and `#VALUE!` appearing in user-visible cells. In Python, internals are hidden from the user, so we should raise Python exceptions instead.
- **Excel runtime still uses ugly helpers for simple mathematical operations**: Where possible, we should use Python's built-in mathematical operators. This should be doable for adding, subtracting, and multiplying, but may not be possible for division (because Excel division coerces datatypes differently). (Perhaps we could implement division by wrapping operands in coercion functions like `float` or `int`.)
- **Public API takes pandas/polars inputs but does not return pandas/polars outputs**: We should provide a way to return outputs as pandas/polars DataFrames if that's what the user specifies.
- **Dynamic ref resolution is not fully implemented for hard cases yet:** We don't yet fully support nested dynamic refs in `excel-grapher`, and constraint resolution can take a long time for wide domains due to combinatorial blowup.
- **Similarity-aware graph packing should be explored as a better compression strategy:** Export uses `OptimalCompression` as the compression strategy; this seemed to work well on Tiny DSA, but similarity-aware compression might be better for larger workbooks (to maximize deduplication potential).

---

## Checklist (copy for new workbook)

[ ] Outputs declared as extraction targets
[ ] bindings/inputs.bindings.yaml + outputs.bindings.yaml validated
[ ] Dynamic-ref constraint candidates constrained
[ ] All leaves classified; mutable leaves bound
[ ] Graph extracts with provenance; manual completeness review done
[ ] dist package builds; semantic API scenario runs
[ ] Validation bundle exported
[ ] Public API uses domain language; docstrings present
[ ] Ready for golden-master sweep (D19)
