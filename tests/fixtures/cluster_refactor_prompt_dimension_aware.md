You will be provided a fingerprint summary of a cluster of Excel formula cells: one structural skeleton, reference relations for each ref slot, a complete member key space, and a single exemplar mechanical Python translation. Your task is to refactor the cluster into a single domain-aware parameterized Python function.

This cluster's formula operands vary independently along a shared semantic concept, and the series bindings declare a distinct dimension id for each role (e.g. `REF_AREA` vs `COUNTERPART_REF_AREA`, or `PROJECTION_PERIOD` vs `REFERENCE_PERIOD`, each referencing one shared concept). Parameterize the formula operand structure: declare one parameter per varying binding dimension id in the signature (the pipeline synthesizes the formal `parameters` / `member_keys` payloads mechanically).

## Output format

Return only JSON matching the response schema:

```json
{
  "additionalProperties": false,
  "properties": {
    "symbol_signature": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "description": "Python function signature, including `def` keyword, `snake_case` semantic name, `ctx: EvalContext`, typed economic parameters from `key_vocabulary`, and parameter type hints. Do not include a return type hint. Null when error is true.",
      "title": "Helper Signature"
    },
    "symbol_docstring": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "description": "Google-style docstring. Include Args and Returns sections. Null when error is true.",
      "title": "Helper Docstring"
    },
    "symbol_body": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "description": "Python function body. Null when error is true.",
      "title": "Helper Body"
    },
    "error": {
      "anyOf": [{"type": "boolean"}, {"type": "null"}],
      "description": "Set to true to abort this refactor and stop the pipeline when the cluster cannot be safely refactored. Null or false on success.",
      "title": "Error"
    },
    "error_reason": {
      "anyOf": [{"type": "string"}, {"type": "null"}],
      "description": "Human-readable explanation of why refactoring must abort. Non-empty when error is true; null otherwise.",
      "title": "Error Reason"
    }
  },
  "required": [
    "symbol_signature",
    "symbol_docstring",
    "symbol_body",
    "error",
    "error_reason"
  ],
  "title": "ClusterRefactorLLMResponse",
  "type": "object"
}
```

Do not emit `parameters` or `member_keys`. The pipeline synthesizes both mechanically from `key_vocabulary` and the cluster's expected binding keys (including counterpart dimension ids).

## Aborting

- If the cluster cannot be safely refactored (for example, member keys that cannot triangulate the operand structure, or contradictory membership), set `error` to `true` and provide a concise non-empty `error_reason`.
- When `error` is `true`, set every success field (`symbol_signature`, `symbol_docstring`, `symbol_body`) to `null`. Do not omit keys.
- Do not invent a best-effort refactor when the correct outcome is to stop. Declaring an error ends the pipeline for human review.
- On success, set `error` to `null` or `false`, set `error_reason` to `null`, and populate every success field.

## Fingerprint context

- Each `## Fingerprint F…` block covers every member that shares one structural skeleton. There is no sampling: the key space lists all observed values.
- The backtick formula uses `ref_N[DIM,…]` placeholders. Reference relations describe how each `ref_N` slot's binding keys relate to the member's own keys, including counterpart dimensions (e.g. `COUNTERPART_REF_AREA = member.COUNTERPART_REF_AREA`).
- `reads:` lines say how to resolve the referenced cells (`xl_cell` address templates, semantic helpers, or in-cluster self-recurrence).
- The exemplar translation is one concrete `cell_*` body. Generalize from the relations + exemplar; do not assume other members are shown as source.

## Signature

- `symbol_signature` must take `ctx: EvalContext` plus one typed parameter per varying binding dimension id from `key_vocabulary` — including counterpart dimension ids that share a concept with another parameter.
- Use `suggested_param_name` from `key_vocabulary` as each parameter's Python name; counterpart dimension ids yield distinct names (e.g. `ref_area` and `counterpart_ref_area`), so parameter names never collide.
- Choose the function name as a clear `snake_case` semantic identifier informed by naming hints.
- Do not include a return type hint on `symbol_signature`; the pipeline injects it mechanically from the mechanical member sources.
- Series-constant binding keys (`scope: series`) are not parameters; bake them into the helper.
- The cluster has already been qualified by formula structure and binding-key shape at each reference position. Do not reinterpret its membership.

## Docstring

- `symbol_docstring` must include a Google-style docstring with a semantic description and `Args` and `Returns` sections.
- Document each `snake_case` Python parameter in `Args` (not all-caps dimension id or concept).
- You may omit Python string delimiters.

## Body

- Emit `symbol_body` for one self-contained function; no nested helpers or imports.
- Parameterize the formula operand structure: use each dimension-id parameter to select the operand it governs (e.g. a lookup table from `ref_area` for one operand's row and from `counterpart_ref_area` for the other operand's row).
- Call only runtime symbols from the exemplar translation and, if necessary, Python stdlib functions/operators.
- Preserve dependency function names and signatures.
- Where appropriate, directly pass through parameters in function calls; e.g. `prior_period_total(ctx, reporting_period=reporting_period)`.
- Rename local temporaries to domain-meaningful `snake_case` informed by naming hints.
- Leave `xl_cell(ctx, 'Sheet!Address')` calls unchanged; this helper reads input/constant values. (Assigning the return value to a semantic local temporary is okay!)
- Prefer concise lookup tables over verbose `if`/`elif` ladders.
- Derive a reference value inside the helper when it follows mechanically from a member parameter (e.g. a fixed lag or period anchor switch). Never collapse two dimension ids onto one concept parameter.

## Example: bilateral flows with counterpart dimension ids

Suppose the dump shows fingerprint `=ref_0[REF_AREA,TIME_PERIOD]-ref_1[COUNTERPART_REF_AREA,TIME_PERIOD]` with identity relations on each role dim, and exemplar metadata carrying `REF_AREA`, `COUNTERPART_REF_AREA`, and `TIME_PERIOD`. Both operand rows are selected by their own dimension-id parameter.

```json
{
  "symbol_signature": "def bilateral_trade_balance(ctx: EvalContext, time_period: int, ref_area: str, counterpart_ref_area: str):",
  "symbol_docstring": "Return exports minus imports for a reporter-counterpart area pair in a period.\n\nArgs:\n    ctx: Workbook evaluation context.\n    time_period: Period index (1 through 2).\n    ref_area: Reporting area code ('USA' or 'DEU').\n    counterpart_ref_area: Counterpart area code ('CHN' or 'FRA').\n\nReturns:\n    Exports of the reporting area minus imports from the counterpart area.",
  "symbol_body": "exports_row_by_area = {'USA': 4, 'DEU': 5}\nimports_row_by_counterpart = {'CHN': 6, 'FRA': 7}\ncolumn_by_period = {1: 'C', 2: 'D'}\ncolumn = column_by_period[time_period]\nexports_value = xl_number(xl_cell(ctx, f'Data!{column}{exports_row_by_area[ref_area]}'))\nimports_value = xl_number(xl_cell(ctx, f'Data!{column}{imports_row_by_counterpart[counterpart_ref_area]}'))\nreturn exports_value - imports_value",
  "error": null,
  "error_reason": null
}
```

## Naming conventions

To support function naming, docstring generation, and parameterization, you will be provided a fingerprint summary (skeleton, reference relations, full key space, exemplar source), `key_vocabulary`, exemplar `expected_keys` / `binding_keys` / `binding_record` naming hints, and dependency stubs. Parameters and per-member keys (including counterpart dimension ids) are filled mechanically; focus on the semantic signature, docstring, and body.
