"""Exported-library differential test harness.

Compare the generated standalone package against Microsoft Excel via xlwings.
Workbook-specific scenario definitions live in the ``Workbook-specific hooks``
section at the bottom of this module.

Run from the extraction repo after export::

    uv run python -m tests.differential.differential_test_exported_library

From the exported ``dist/`` project (Windows + Excel)::

    uv run --project dist --group validation python -m tests.differential.differential_test_exported_library --layout exported
"""

from __future__ import annotations

import argparse
import csv
import importlib
import logging
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, Mapping, cast

from excel_grapher import XlError

from .differential_excel import (
    coerce_excel_error,
    matched_error_values,
    read_cell_value,
)
from .differential_types import ATOL, Scenario

logger = logging.getLogger(__name__)

LayoutName = Literal["repo", "exported"]


@dataclass(frozen=True)
class DifferentialConfig:
    """Runtime paths and import settings for one differential run."""

    workbook_path: Path
    package_dir: Path
    package_name: str
    import_root: Path
    report_dir: Path
    library_name: str
    atol: float = ATOL
    warn_on_error_values: bool = False


@dataclass(frozen=True)
class Comparison:
    scenario_id: str
    cell_address: str
    cell_label: str
    excel_value: Any
    mvp_value: Any
    abs_diff: float | None
    rel_diff: float | None
    passed: bool
    matched_error: bool = False
    flagged_matched_error: bool = False


CSV_COLUMNS: tuple[str, ...] = (
    "scenario_id",
    "cell_address",
    "cell_label",
    "excel_value",
    "mvp_value",
    "abs_diff",
    "rel_diff",
    "passed",
    "matched_error",
    "flagged_matched_error",
)


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
        "--workbook-path",
        type=Path,
        default=None,
        help="Override workbook path (defaults depend on --layout).",
    )
    parser.add_argument(
        "--package-name",
        default=None,
        help="Override import module for the MVP oracle (defaults depend on --layout).",
    )
    parser.add_argument(
        "--import-root",
        type=Path,
        default=None,
        help="Directory added to sys.path before importing the MVP oracle.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Directory for parity_report.{csv,txt} output.",
    )
    parser.add_argument(
        "--warn-on-error-values",
        action="store_true",
        help=(
            "List passing comparisons where both sides are the same Excel error "
            "code, for scenario-setup review."
        ),
    )
    return parser.parse_args(argv)


def _project_root_from_module(module_path: Path) -> Path:
    """Return repo or dist root from ``tests/differential/<module>.py``."""
    return module_path.resolve().parents[2]


def _tests_root_from_module(module_path: Path) -> Path:
    return module_path.resolve().parents[1]


def resolve_config(
    *,
    module_path: Path,
    layout: LayoutName,
    workbook_path: Path | None = None,
    package_name: str | None = None,
    import_root: Path | None = None,
    report_dir: Path | None = None,
    warn_on_error_values: bool = False,
) -> DifferentialConfig:
    """Resolve paths from ``workbook_config.py`` and the selected layout."""
    module_path = module_path.resolve()
    project_root = _project_root_from_module(module_path)

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from src.pipeline_config import load_pipeline_config

    pipeline = load_pipeline_config(repo_root=project_root)
    package_dir = pipeline.package_root
    package_slug = pipeline.dist_metadata.package_name
    library_name = pipeline.dist_metadata.library_name

    if layout == "exported":
        tests_root = _tests_root_from_module(module_path)
        dist_root = project_root
        defaults = DifferentialConfig(
            workbook_path=tests_root / "fixtures" / pipeline.workbook_path.name,
            package_dir=dist_root / package_slug,
            package_name=f"{package_slug}.api",
            import_root=dist_root,
            report_dir=tests_root / "results" / "local",
            library_name=library_name,
        )
    else:
        defaults = DifferentialConfig(
            workbook_path=pipeline.workbook_path,
            package_dir=package_dir,
            package_name=f"dist.{package_slug}.api",
            import_root=project_root,
            report_dir=project_root / pipeline.differential_report_dir_rel,
            library_name=library_name,
        )

    return DifferentialConfig(
        workbook_path=(workbook_path or defaults.workbook_path).resolve(),
        package_dir=defaults.package_dir.resolve(),
        package_name=package_name or defaults.package_name,
        import_root=(import_root or defaults.import_root).resolve(),
        report_dir=(report_dir or defaults.report_dir).resolve(),
        library_name=library_name,
        atol=ATOL,
        warn_on_error_values=warn_on_error_values,
    )


def config_from_args(module_path: Path, args: argparse.Namespace) -> DifferentialConfig:
    return resolve_config(
        module_path=module_path,
        layout=args.layout,
        workbook_path=args.workbook_path,
        package_name=args.package_name,
        import_root=args.import_root,
        report_dir=args.report_dir,
        warn_on_error_values=args.warn_on_error_values,
    )


def compare_cell(
    scenario_id: str,
    cell_address: str,
    cell_label: str,
    excel: Any,
    mvp: Any,
    *,
    atol: float,
    expects_error_values: bool = False,
) -> Comparison:
    raw_excel = excel
    raw_mvp = mvp
    excel = coerce_excel_error(excel)
    mvp = coerce_excel_error(mvp)

    if isinstance(excel, XlError) or isinstance(mvp, XlError):
        passed = isinstance(excel, XlError) and isinstance(mvp, XlError) and excel == mvp
        matched_error = passed
        return Comparison(
            scenario_id,
            cell_address,
            cell_label,
            excel,
            mvp,
            None,
            None,
            passed,
            matched_error=matched_error,
            flagged_matched_error=matched_error and not expects_error_values,
        )

    if excel is None and mvp is None:
        return Comparison(
            scenario_id, cell_address, cell_label, None, None, 0.0, 0.0, True
        )
    if excel is None or mvp is None:
        return Comparison(
            scenario_id, cell_address, cell_label, excel, mvp, None, None, False
        )
    try:
        excel_f = float(excel)  # type: ignore[arg-type]
        mvp_f = float(mvp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        passed = excel == mvp
        matched_error = matched_error_values(raw_excel, raw_mvp) and passed
        return Comparison(
            scenario_id,
            cell_address,
            cell_label,
            excel,
            mvp,
            None,
            None,
            passed,
            matched_error=matched_error,
            flagged_matched_error=matched_error and not expects_error_values,
        )
    if not (math.isfinite(excel_f) and math.isfinite(mvp_f)):
        passed = excel_f == mvp_f or (math.isnan(excel_f) and math.isnan(mvp_f))
        return Comparison(
            scenario_id, cell_address, cell_label, excel_f, mvp_f, None, None, passed
        )
    abs_diff = abs(excel_f - mvp_f)
    rel_diff = abs_diff / abs(excel_f) if excel_f != 0 else math.inf
    passed = abs_diff <= atol
    return Comparison(
        scenario_id,
        cell_address,
        cell_label,
        excel_f,
        mvp_f,
        abs_diff,
        rel_diff,
        passed,
    )


def compare_scenario(
    scenario: Scenario,
    excel_outputs: dict[str, Any],
    mvp_outputs: dict[str, Any],
    cell_labels: tuple[tuple[str, str], ...],
    *,
    atol: float,
) -> list[Comparison]:
    return [
        compare_cell(
            scenario.id,
            cell_address,
            cell_label,
            excel_outputs.get(cell_address),
            mvp_outputs.get(cell_address),
            atol=atol,
            expects_error_values=scenario.expects_error_values,
        )
        for cell_label, cell_address in cell_labels
    ]


def crash_comparisons(
    scenario: Scenario,
    cell_labels: tuple[tuple[str, str], ...],
    exc: BaseException,
) -> list[Comparison]:
    err_repr = f"<exception: {type(exc).__name__}: {exc}>"
    return [
        Comparison(
            scenario_id=scenario.id,
            cell_address=cell_address,
            cell_label=cell_label,
            excel_value=err_repr,
            mvp_value=err_repr,
            abs_diff=None,
            rel_diff=None,
            passed=False,
        )
        for cell_label, cell_address in cell_labels
    ]


def write_csv_report(comparisons: list[Comparison], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for comparison in comparisons:
            writer.writerow(
                [
                    comparison.scenario_id,
                    comparison.cell_address,
                    comparison.cell_label,
                    comparison.excel_value,
                    comparison.mvp_value,
                    comparison.abs_diff,
                    comparison.rel_diff,
                    comparison.passed,
                    comparison.matched_error,
                    comparison.flagged_matched_error,
                ]
            )


def write_txt_summary(
    comparisons: list[Comparison],
    path: Path,
    *,
    config: DifferentialConfig,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(comparisons)
    failures = [comparison for comparison in comparisons if not comparison.passed]
    passed = total - len(failures)
    pass_rate = (100.0 * passed / total) if total else 0.0
    result = "PASS" if not failures else "FAIL"
    first = failures[0] if failures else None

    with path.open("w", encoding="utf-8") as handle:
        handle.write(
            f"Parity report: exported {config.library_name} standalone library vs Excel\n"
        )
        handle.write(
            f"Generated: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        )
        handle.write(f"Workbook:  {config.workbook_path}\n")
        handle.write(
            f"Package:   {config.package_dir} (imported as {config.package_name})\n"
        )
        handle.write(f"Tolerance: atol = {config.atol}\n\n")
        handle.write(f"Total comparisons: {total}\n")
        handle.write(f"Passed:            {passed}\n")
        handle.write(f"Failed:            {len(failures)}\n")
        handle.write(f"Pass rate:         {pass_rate:.2f}%\n")
        handle.write("Acceptance bar:    100.00%\n")
        handle.write(f"Result:            {result}\n")
        if first is not None:
            handle.write("\nFirst divergence:\n")
            handle.write(f"  scenario:  {first.scenario_id}\n")
            handle.write(f"  cell:      {first.cell_address}  ({first.cell_label})\n")
            handle.write(f"  excel:     {first.excel_value!r}\n")
            handle.write(f"  mvp:       {first.mvp_value!r}\n")
            handle.write(f"  abs_diff:  {first.abs_diff!r}\n")
            handle.write(f"  rel_diff:  {first.rel_diff!r}\n")
        if config.warn_on_error_values:
            flagged = [
                comparison
                for comparison in comparisons
                if comparison.flagged_matched_error
            ]
            if flagged:
                handle.write(
                    "\nMatched error values (passed, but review scenario setup; "
                    "set Scenario.expects_error_values=True when intentional):\n"
                )
                for comparison in flagged:
                    handle.write(f"  {comparison.scenario_id} :: ")
                    handle.write(
                        f"{comparison.cell_address} ({comparison.cell_label})\n"
                    )
                    handle.write(f"    excel: {comparison.excel_value!r}\n")
                    handle.write(f"    mvp:   {comparison.mvp_value!r}\n")


def load_exported_library(import_root: Path, package_name: str) -> ModuleType:
    root_str = str(import_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return importlib.import_module(package_name)


def run_excel_oracle(
    workbook_path: Path,
    scenario: Scenario,
    output_addresses: tuple[str, ...],
) -> dict[str, Any]:
    import xlwings as xw

    logger.info("Excel oracle: %s", scenario.id)
    app = xw.App(visible=False, add_book=False)
    try:
        workbook = app.books.open(str(workbook_path))
        try:
            app.calculation = "manual"
            for address, value in inputs_for_excel(scenario).items():
                sheet, cell = address.split("!", 1)
                workbook.sheets[sheet].range(cell).value = value
            workbook.app.calculate()

            def read(address: str) -> Any:
                return read_cell_value(workbook.sheets, address)

            return {address: read(address) for address in output_addresses}
        finally:
            workbook.close()
    finally:
        app.quit()


def _records_to_cells(
    records: list[dict[str, Any]],
    cells: tuple[str, ...],
) -> dict[str, Any]:
    if len(records) != len(cells):
        raise ValueError(f"expected {len(cells)} records, got {len(records)}")
    raw_periods = [record.get("TIME_PERIOD") for record in records]
    if all(period is not None for period in raw_periods):
        periods = cast(list[Any], raw_periods)
        if any(a >= b for a, b in zip(periods, periods[1:], strict=False)):
            raise ValueError(
                f"records' TIME_PERIOD values are not strictly increasing: {periods!r}"
            )
    by_cell: dict[str, Any] = {}
    for index, (record, cell) in enumerate(zip(records, cells, strict=True)):
        if "OBS_VALUE" not in record:
            raise ValueError(f"record {index}: missing OBS_VALUE: {record!r}")
        by_cell[cell] = record["OBS_VALUE"]
    return by_cell


def run_mvp_oracle(api: ModuleType, scenario: Scenario) -> dict[str, Any]:
    logger.info("MVP oracle:   %s", scenario.id)
    ctx = api.make_context()
    apply_inputs_to_mvp(api, ctx, scenario)
    outputs: dict[str, Any] = {}
    for entrypoint, cells in output_ranges():
        compute_fn = getattr(api, f"compute_{entrypoint}")
        records = compute_fn(ctx=ctx)
        outputs.update(_records_to_cells(records, cells))
    return outputs


def _verify_paths(config: DifferentialConfig) -> None:
    if not config.workbook_path.is_file():
        raise FileNotFoundError(
            f"Workbook not found: {config.workbook_path}. "
            "Populate data/ and workbook_config.py before running parity tests."
        )
    if (
        not (config.package_dir / "__init__.py").is_file()
        or not (config.package_dir / "api.py").is_file()
    ):
        raise FileNotFoundError(
            f"Exported package incomplete at {config.package_dir} "
            "(expected __init__.py and api.py). "
            "Run 'uv run python -m src.extraction_pipeline' to regenerate."
        )


def _check_staleness(config: DifferentialConfig) -> None:
    data_path = config.package_dir / "data.py"
    if not data_path.is_file():
        return
    workbook_mtime = config.workbook_path.stat().st_mtime
    data_mtime = data_path.stat().st_mtime
    if workbook_mtime > data_mtime:
        logger.warning(
            "Workbook is newer than exported data.py; regenerate dist/ if constants changed."
        )


def _validate_workbook_hooks() -> None:
    scenarios = build_scenarios()
    if not scenarios:
        raise RuntimeError(
            "No differential scenarios configured. Author build_scenarios(), "
            "output_cell_labels(), output_ranges(), inputs_for_excel(), and "
            "apply_inputs_to_mvp() in "
            "tests/differential/differential_test_exported_library.py."
        )
    if not output_cell_labels():
        raise RuntimeError(
            "output_cell_labels() returned no cells. Mirror your output bindings "
            "as (label, address) pairs."
        )
    if not output_ranges():
        raise RuntimeError(
            "output_ranges() returned no compute groups. Map each compute_* "
            "entrypoint to its output cell addresses."
        )


def run_differential_test(config: DifferentialConfig) -> int:
    _validate_workbook_hooks()
    _verify_paths(config)
    _check_staleness(config)

    api = load_exported_library(config.import_root, config.package_name)
    scenarios = build_scenarios()
    cell_labels = output_cell_labels()
    output_addresses = tuple(address for _, address in cell_labels)

    comparisons: list[Comparison] = []
    for scenario in scenarios:
        try:
            excel_outputs = run_excel_oracle(
                config.workbook_path,
                scenario,
                output_addresses,
            )
            mvp_outputs = run_mvp_oracle(api, scenario)
        except Exception as exc:
            logger.exception("Scenario %s crashed; recording as failure.", scenario.id)
            comparisons.extend(crash_comparisons(scenario, cell_labels, exc))
            continue
        comparisons.extend(
            compare_scenario(
                scenario,
                excel_outputs,
                mvp_outputs,
                cell_labels,
                atol=config.atol,
            )
        )

    config.report_dir.mkdir(parents=True, exist_ok=True)
    write_csv_report(comparisons, config.report_dir / "parity_report.csv")
    write_txt_summary(
        comparisons,
        config.report_dir / "parity_report.txt",
        config=config,
    )

    failed = sum(1 for comparison in comparisons if not comparison.passed)
    flagged = sum(1 for comparison in comparisons if comparison.flagged_matched_error)
    logger.info("Done. Failures: %d / %d", failed, len(comparisons))
    if config.warn_on_error_values and flagged:
        logger.warning(
            "Matched error values in %d comparison(s); see report section in %s",
            flagged,
            config.report_dir / "parity_report.txt",
        )
    return 0 if failed == 0 else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        args = parse_args(argv)
        config = config_from_args(Path(__file__).resolve(), args)
        return run_differential_test(config)
    except RuntimeError as exc:
        logger.error("%s", exc)
        return 2
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return 2
    except Exception:
        logger.exception("Differential test failed with an unhandled exception.")
        return 2


# --------------------------------------------------------------------------
# Workbook-specific hooks — replace these when configuring a new extraction.
# --------------------------------------------------------------------------


def build_scenarios() -> tuple[Scenario, ...]:
    """Return the scenario sweep for this workbook."""
    return ()


def output_cell_labels() -> tuple[tuple[str, str], ...]:
    """Return ``((cell_label, cell_address), ...)`` for every compared output cell."""
    return ()


def output_ranges() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Return ``((compute_entrypoint, (cell, ...)), ...)`` for MVP oracle reads."""
    return ()


def inputs_for_excel(scenario: Scenario) -> dict[str, Any]:
    """Map one scenario to Excel cell writes for the golden-master oracle."""
    raise NotImplementedError(
        "Author inputs_for_excel() with cell mappings from bindings/*.bindings.yaml."
    )


def apply_inputs_to_mvp(api: ModuleType, ctx: Any, scenario: Scenario) -> None:
    """Apply one scenario via the exported package's public set_* functions."""
    raise NotImplementedError(
        "Author apply_inputs_to_mvp() to drive the Records-shaped public API."
    )


if __name__ == "__main__":
    sys.exit(main())
