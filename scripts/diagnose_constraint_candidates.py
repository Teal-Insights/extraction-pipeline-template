"""CLI entry point for dynamic-ref constraint candidate diagnostics.

Run: uv run python -u -m scripts.diagnose_constraint_candidates
"""

from __future__ import annotations

from src.diagnose_constraint_candidates import main

if __name__ == "__main__":
    raise SystemExit(main())
