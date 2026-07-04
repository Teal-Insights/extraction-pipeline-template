"""Workbook-specific configuration for this extraction project.

Edit every value below before running the pipeline. See README.md for the
configure → extract → export → test → document → refactor workflow.
"""

from pathlib import Path

from src.graph_dependency_audit import GraphAuditCase
from src.pipeline_config import DistProjectMetadata
from src.workbook_addresses import ProjectionColumnLayout

REPO_ROOT = Path(__file__).resolve().parent

WORKBOOK_PATH = REPO_ROOT / "data" / "workbook.xlsx"
GUIDE_PATH = REPO_ROOT / "data" / "guide.md"
BINDINGS_PATH = REPO_ROOT / "bindings"

# Named ranges or sheet-qualified addresses for target-driven graph extraction.
TARGETS: list[str] = []

# Cell address -> constraint for dynamic-ref resolution and leaf classification.
# Use Literal[...] for fixed lookup values and Annotated[..., Between/RealBetween]
# for user-editable inputs. Every graph leaf must appear here.
CONSTRAINTS: dict[str, object] = {}

DIST_METADATA = DistProjectMetadata(
    project_name="my-model",
    package_name="my_model",
    library_name="My Model",
    description="Python implementation of the configured Excel workbook.",
    documentation_url="https://example.com/my-model/",
    repository_url=None,
    # Optional markdown rendered in the generated README only, not in pyproject.toml.
    # attribution="Created by Example Corp.\n\n![Logo](README_files/logo.png)",
)

DOCSTRING_CALLBACK_NAME = "series_docs"

# Optional layout for parallel time-series columns during internals refactoring.
# Set to None when the workbook does not use a repeating Engine/Outputs projection.
PROJECTION_LAYOUT: ProjectionColumnLayout | None = None

# Reference example (Tiny DSA — uncomment and adapt for a similar workbook):
#
# PROJECTION_LAYOUT = ProjectionColumnLayout(
#     engine_sheet="Engine",
#     engine_columns=("C", "D", "E", "F", "G"),
#     outputs_sheet="Outputs",
#     outputs_column_to_engine={
#         "B": "C",
#         "C": "D",
#         "D": "E",
#         "E": "F",
#         "F": "G",
#     },
#     time_period_to_engine_column={
#         1: "C",
#         2: "D",
#         3: "E",
#         4: "F",
#         5: "G",
#     },
# )

DIFFERENTIAL_WORKBOOK_REL = Path("data/workbook.xlsx")
DIFFERENTIAL_REPORT_DIR_REL = Path("data/differential/exported_library")

# Optional per-parent formula cells for LLM direct-dependency graph audits.
GRAPH_AUDIT_CASES: tuple[GraphAuditCase, ...] = ()

# Optional hooks for ``uv run python -m src.workbook_audit`` (pre-extraction audit).
AUDIT_TITLE = "Workbook Audit"
AUDIT_PUBLIC_INPUTS: tuple[tuple[str, str, str], ...] = ()
AUDIT_GUIDE_USE_CASES: tuple[tuple[str, str, str], ...] = ()
