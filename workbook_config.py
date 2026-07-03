"""Workbook-specific configuration for this extraction project.

Edit every value below before running the pipeline. See README.md for the
configure → extract → export → test → document → refactor workflow.
"""

from pathlib import Path

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

DIFFERENTIAL_WORKBOOK_REL = Path("data/workbook.xlsx")
DIFFERENTIAL_REPORT_DIR_REL = Path("data/differential/exported_library")
