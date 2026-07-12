# Series bindings

Author `inputs.bindings.yaml`, `outputs.bindings.yaml`, and `internals.bindings.yaml` here before running the pipeline.

Use schema version `1.8.0` and the prompt in [templates/binding-authoring-prompt.txt](../templates/binding-authoring-prompt.txt).

## Dimension `id` vs `concept`

| Field | Role |
|---|---|
| `concept` | SDMX-style meaning category (e.g. `TIME_PERIOD`) |
| `id` | Dimension identity used in records, cell keys, and refactor parameters |

Give every dimension an explicit `id`. When `id` is omitted, the effective id falls back to `concept`. If two dimensions share a concept, they must have distinct ids:

```yaml
dimensions:
  - id: PROJECTION_PERIOD
    concept: TIME_PERIOD
    role: key
    scope: cell
    bind:
      kind: column_header
      header_row: 5
      read: int
  - id: REFERENCE_PERIOD
    concept: TIME_PERIOD
    role: key
    scope: cell
    bind:
      kind: value_map
      values:
        0: C:G
      read: int
key: [PROJECTION_PERIOD, REFERENCE_PERIOD]
```

Effective ids drive parameter names (`projection_period`, `reference_period`). Concepts remain semantic metadata for documentation and concept-scheme dtype inheritance.
