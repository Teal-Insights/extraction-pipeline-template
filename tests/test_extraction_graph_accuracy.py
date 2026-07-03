import os

from dotenv import load_dotenv
import pytest

from excel_grapher.grapher import to_mermaid

from src.extraction_pipeline import build_pipeline_graph
from src.pipeline_config import load_pipeline_config, validate_pipeline_config

load_dotenv()


@pytest.mark.skipped(reason="Opt-in test; pass --run-skipped to run")
def test_llm_judges_that_graph_is_correct() -> None:
    """Use an LLM spot-check to review the configured dependency graph."""
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not set")

    config = load_pipeline_config()
    try:
        validate_pipeline_config(config)
    except FileNotFoundError as exc:
        pytest.skip(f"Pipeline configuration is incomplete: {exc}")

    openai = pytest.importorskip(
        "openai",
        reason="requires openai for LLM-based graph accuracy testing",
    )

    graph, _series_bindings, _input_series, _output_series = build_pipeline_graph(
        config
    )
    prompt = """
Given these targets in an Excel workbook, we want to extract a graph
of all possible dependencies of the targets:

{targets}

We set the following constraints on user inputs affecting dependency
resolution:

{constraints}

Given these constraints, is the following graph correct? Does it contain
all nodes and edges it should, and none that it shouldn't? Just say
CORRECT or INCORRECT.

Graph:
```mermaid
{mermaid_graph}
```
""".format(
        targets=list(config.targets),
        constraints=config.constraints,
        mermaid_graph=to_mermaid(graph),
    )

    client = openai.OpenAI(
        api_key=os.environ["OPENAI_API_KEY"],
        base_url="https://api.openai.com/v1/",
    )
    response = client.chat.completions.create(
        model="gpt-5.5",
        messages=[
            {"role": "user", "content": prompt},
        ],
        stream=False,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )

    assert response.choices[0].message.content.strip().upper() == "CORRECT"
