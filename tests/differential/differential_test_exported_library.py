"""Exported-library differential test harness (workbook-specific).

Replace this stub with a scenario sweep that compares your exported package
against Microsoft Excel via xlwings. The harness should:

1. Load paths and import settings from ``workbook_config.py`` / ``--layout``.
2. Define input scenarios and map them to Excel cell writes and Records-shaped
   ``set_*`` calls on the exported public API.
3. Read output cells from Excel and from ``compute_*`` entrypoints.
4. Compare at ``atol = 1e-6`` and write ``parity_report.{csv,txt}``.

See ``tests/differential/README.md`` for the oracle pattern and acceptance bar.

Run from the extraction repo after export::

    uv run python tests/differential/differential_test_exported_library.py

From the exported ``dist/`` project (Windows + Excel)::

    uv run --project dist --group validation python tests/differential_test_exported_library.py --layout exported
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal


LayoutName = Literal["repo", "exported"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Differential test for the exported standalone library.",
    )
    parser.add_argument(
        "--layout",
        choices=("repo", "exported"),
        default="repo",
        help="Path preset: extraction repo (default) or exported dist/tests copy.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Directory for parity_report.{csv,txt} output.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print(
        "Differential harness not implemented for this workbook yet.\n"
        "Author scenarios and cell mappings in "
        "tests/differential/differential_test_exported_library.py.\n"
        f"Layout: {args.layout}"
    )
    if args.report_dir is not None:
        print(f"Report dir (unused): {args.report_dir}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
