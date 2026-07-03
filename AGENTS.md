## Python best practices

Always run Python code with `uv run`.

Use `fastpyxl` as a drop-in replacement for `openpyxl`.

Use static type annotations and direct attribute access. True defensive programming means enforcing that incorrect code fails fast and loudly.

## Test-driven development

Practice test-driven development (TDD). First write RED-phase tests and watch them fail for the right reason, then write code to turn the tests GREEN.

## Git branching

If you are asked to commit your work, make sure you commit it to an issue branch created with `gh issue develop`. Check that you are not already on such a branch before creating a new one.

## Opening issues to `Teal-Insights/excel-grapher`

We control the `Teal-Insights/excel-grapher` repository, so we can and should open issues there directly when we encounter bugs or need new features.

If a bug blocks our work, open an issue, mark it urgent, and stop working until the bug is fixed. If we can work around it, you should still open an issue so that we can track it and fix it in the future.

Remember to include at least a working minimal complete verifiable example (MCVE) of the bug in the issue body. The MCVE must be *self-contained* (must not depend on any local file artifacts or environment variables).

## Cursor Cloud specific instructions

Dev commands are documented in `README.md` (Development section); use `uv run <cmd>`. The dependency-refresh step (`uv sync --all-groups`) runs automatically on startup, so you normally do not need to run it manually.

- `graphviz` is a required system dependency (see `.github`/`workflows/test.yml`) and is preinstalled in the VM.
- This is a **template** repo: the pipeline entry point `uv run python -m src.extraction_pipeline` needs a configured `data/workbook.xlsx`, `data/guide.md`, `bindings/*.bindings.yaml`, and populated `TARGETS`/`CONSTRAINTS` in `workbook_config.py`. Without those it fails fast with a `FileNotFoundError` listing the missing inputs — that is expected, not a broken environment. The primary dev surface here is `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, and `uv run ty check`.
- The differential/parity harness (`tests/differential/`) drives Microsoft Excel via `xlwings` COM automation and only runs on Windows with Excel installed; it cannot run in this Linux VM.
- LLM-backed steps read cached results under `.cache/`; uncached runs need `OPENAI_API_KEY` (place in `.env`).