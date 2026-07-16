You will be provided a fingerprint summary of a cluster of Excel formula cells: one structural skeleton, reference relations for each ref slot, a complete member key space, and a single exemplar mechanical Python translation. Your task is to refactor the cluster into a single domain-aware parameterized Python function.

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

Do not emit `parameters` or `member_keys`. The pipeline synthesizes both mechanically from `key_vocabulary` and the cluster's expected binding keys.

## Aborting

- If the cluster is unrefactorable or unrepresentable (for example contradictory membership), set `error` to `true` and provide a concise non-empty `error_reason`.
- When `error` is `true`, set every success field (`symbol_signature`, `symbol_docstring`, `symbol_body`) to `null`. Do not omit keys.
- On success, set `error` to `null` or `false`, set `error_reason` to `null`, and populate every success field.
- Declaring an error stops the pipeline run for human review.

## Fingerprint context

- Each `## Fingerprint F…` block covers every member that shares one structural skeleton. There is no sampling: the key space lists all observed values.
- The backtick formula uses `ref_N[DIM,…]` placeholders. Reference relations describe how each `ref_N` slot's binding keys relate to the member's own keys:
  - `DIM = member.DIM` — identity
  - `DIM = member.DIM - N` / `+ N` — constant offset / lag
  - `DIM = member.DIM - lag, lag by KEY {…}` — ragged lag keyed by another member dimension
  - `DIM = value` — constant across the cluster
  - `explicit member keys -> ref keys` — irregular fallback table
- `reads:` lines say how to resolve the referenced cells (`xl_cell` address templates, semantic helpers, or in-cluster self-recurrence).
- The exemplar translation is one concrete `cell_*` body. Generalize from the relations + exemplar; do not assume other members are shown as source.

## Signature

- `symbol_signature` must take `ctx: EvalContext` plus one typed parameter per varying binding dimension from `key_vocabulary`.
- Use `suggested_param_name` from `key_vocabulary` as each parameter's Python name.
- Choose the function name as a clear `snake_case` semantic identifier informed by naming hints.
- Do not include a return type hint on `symbol_signature`; the pipeline injects it mechanically from the mechanical member sources.
- Series-constant binding keys (`scope: series`) are not parameters; bake them into the helper.
- The cluster has already been qualified by formula structure and binding-key shape at each reference position. Do not reinterpret its membership or add parameters for individual reference positions.

## Docstring

- `symbol_docstring` must include a Google-style docstring with a semantic description and `Args` and `Returns` sections.
- Document each `snake_case` Python parameter in `Args` (not all-caps dimension id or concept).
- You may omit Python string delimiters.

## Body

- Emit `symbol_body` for one self-contained function; no nested helpers or imports.
- Call only runtime symbols from the exemplar translation and, if necessary, Python stdlib functions/operators.
- Preserve dependency function names and signatures.
- Where appropriate, directly pass through parameters in function calls; e.g. `prior_period_total(ctx, reporting_period=reporting_period)`.
- Rename local temporaries to domain-meaningful `snake_case` informed by naming hints.
- Leave `xl_cell(ctx, 'Sheet!Address')` calls unchanged; this helper reads input/constant values. (Assigning the return value to a semantic local temporary is okay!)
- Prefer concise lookup tables over verbose `if`/`elif` ladders.
- Derive lagged or offset periods inside the body from member parameters and the stated reference relations; do not invent extra parameters for operand positions.

## Example 1: Unpacking nested calls

Suppose the dump shows fingerprint `=IF(ref_0[REPORTING_PERIOD]>=ref_1,1,0)` over `Forecast!B12:F12` with `REPORTING_PERIOD: 1..5` and engine columns, identity on `ref_0`, and constant `Assumptions!C2` for `ref_1`, plus one exemplar `cell_forecast_b12`. Generalize the exemplar with a period→column table:

```json
{
  "symbol_signature": "def growth_threshold_met(ctx: EvalContext, reporting_period: int):",
  "symbol_docstring": "Return 1.0 when the observed value meets or exceeds the growth threshold for the reporting period.\n\nArgs:\n    ctx: Workbook evaluation context.\n    reporting_period: Reporting period index (1 through 5).\n\nReturns:\n    1.0 if the observed value is at or above the threshold, else 0.0.",
  "symbol_body": "column_by_period = {1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F'}\ncolumn = column_by_period[reporting_period]\nobserved_value = xl_cell(ctx, f'Forecast!{column}4')\nthreshold = xl_cell(ctx, 'Assumptions!C2')\nmeets_threshold = xl_compare('>=', observed_value, threshold)\nreturn 1.0 if meets_threshold else 0.0",
  "error": null,
  "error_reason": null
}
```

## Example 2: representing supported lagged reference periods

Some formulas read the same indicator at more than one period. Reference relations may show `TIME_PERIOD = member.TIME_PERIOD` on `ref_0` and `TIME_PERIOD = member.TIME_PERIOD - lag, lag by REF_AREA {USA: 1, FRA: 3}` on `ref_1`. Derive the lagged period inside the body; do not add a second period parameter.

```json
{
  "symbol_signature": "def indicator_change_from_reference_period(ctx: EvalContext, time_period: int, ref_area: str):",
  "symbol_docstring": "Return the change in the observed indicator relative to its area-specific reference period.\n\nArgs:\n    ctx: Workbook evaluation context.\n    time_period: Period index (4 through 7).\n    ref_area: Reference area code ('USA' or 'FRA').\n\nReturns:\n    Current-period value minus the lagged value (lag 1 for USA, lag 3 for FRA).",
  "symbol_body": "source_row_by_area = {'USA': 4, 'FRA': 8}\nlag_by_area = {'USA': 1, 'FRA': 3}\ncolumn_by_period = {1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H'}\nsource_row = source_row_by_area[ref_area]\ncurrent_value = xl_number(xl_cell(ctx, f'Data!{column_by_period[time_period]}{source_row}'))\nreference_period = time_period - lag_by_area[ref_area]\nreference_value = xl_number(xl_cell(ctx, f'Data!{column_by_period[reference_period]}{source_row}'))\nreturn current_value - reference_value",
  "error": null,
  "error_reason": null
}
```

Similar conditional selection or switching logic can be applied to solve other common cases, such as piecewise time series or first/last-period anchor cell special casing.

## Naming conventions

To support function naming, docstring generation, and parameterization, you will be provided a fingerprint summary (skeleton, reference relations, full key space, exemplar source), `key_vocabulary`, exemplar `expected_keys` / `binding_keys` / `binding_record` naming hints, and dependency stubs. Parameters and per-member keys are filled mechanically; focus on the semantic signature, docstring, and body.
