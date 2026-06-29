from pathlib import Path

from src.pipeline_config import load_pipeline_config
from src.documentation_pipeline import (
    build_section_prompt,
    load_canonical_api_example,
    parse_parity_report,
    render_validation_page,
    validate_rewritten_markdown_fences,
)


def test_load_canonical_api_example_reads_template() -> None:
    config = load_pipeline_config()
    example = load_canonical_api_example(config)
    assert "make_context()" in example
    assert "compute_" in example
    assert "import polars as pl" in example


def test_section_prompt_uses_configured_api_import_path() -> None:
    config = load_pipeline_config()
    prompt = build_section_prompt(
        library_name=config.dist_metadata.library_name,
        api_import_path=config.api_import_path,
        section_name="Functional Overview",
        source_section_markdown="Source",
        python_focus_instructions="Mirror the canonical example.",
        pipeline_context_blocks={"canonical_api_usage": "ctx = make_context()"},
        api_signatures="def make_context(): ...",
        response_schema={"type": "object"},
    )

    assert config.api_import_path in prompt
    assert "ctx = make_context()" in prompt


def test_fence_validation_accepts_well_formed_quarto_cell() -> None:
    markdown = (
        "Intro paragraph.\n\n"
        "```{python}\n"
        "from my_model.api import make_context\n"
        "ctx = make_context()\n"
        "```\n\n"
        "Closing paragraph."
    )
    validate_rewritten_markdown_fences(markdown)


def test_render_validation_page_uses_package_metadata() -> None:
    from src.documentation_pipeline import ParityReportSummary

    summary = ParityReportSummary(
        generated="2026-01-01",
        tolerance="1e-6",
        total_comparisons=10,
        passed=10,
        failed=0,
        pass_rate="100%",
        acceptance_bar="100%",
        result="PASS",
    )
    page = render_validation_page(
        summary,
        library_name="Forecast Kit",
        package_name="forecast_kit",
    )
    assert "Forecast Kit" in page
    assert "forecast_kit" in page


def test_parse_parity_report() -> None:
    report = """Generated: 2026-01-01
Tolerance: 1e-6
Total comparisons: 10
Passed: 10
Failed: 0
Pass rate: 100%
Acceptance bar: 100%
Result: PASS
"""
    summary = parse_parity_report(report)
    assert summary.result == "PASS"
    assert summary.total_comparisons == 10
