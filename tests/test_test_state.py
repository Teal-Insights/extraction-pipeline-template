"""Tests for shared pytest pipeline state helpers."""

from __future__ import annotations

import importlib
import os
import sys
import types
from pathlib import Path

import pytest

from tests.fixtures.test_state import (
    assert_repo_pipeline_artifacts_unchanged,
    reset_pipeline_test_state,
    snapshot_repo_pipeline_artifacts,
)

_DIFFERENTIAL_HARNESS_MODULE = "tests.differential.differential_test_exported_library"


def test_reset_pipeline_test_state_clears_probe_modules() -> None:
    sys.modules[_DIFFERENTIAL_HARNESS_MODULE] = types.ModuleType(
        _DIFFERENTIAL_HARNESS_MODULE
    )

    reset_pipeline_test_state()

    assert _DIFFERENTIAL_HARNESS_MODULE not in sys.modules


def test_pipeline_context_module_is_removed() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("src.pipeline_context")


def test_repo_pipeline_artifact_guard_passes_when_untouched(tmp_path: Path) -> None:
    stages = tmp_path / "artifacts" / "stages"
    stages.mkdir(parents=True)
    (stages / "extract.json").write_text("{}", encoding="utf-8")

    before = snapshot_repo_pipeline_artifacts(tmp_path)

    assert_repo_pipeline_artifacts_unchanged(before, tmp_path)


@pytest.mark.parametrize(
    "relative_path",
    ["artifacts/stages/extract.json", "artifacts/stage-timings.json"],
)
def test_repo_pipeline_artifact_guard_fails_when_a_test_writes(
    tmp_path: Path, relative_path: str
) -> None:
    stages = tmp_path / "artifacts" / "stages"
    stages.mkdir(parents=True)
    (stages / "extract.json").write_text("{}", encoding="utf-8")
    before = snapshot_repo_pipeline_artifacts(tmp_path)

    (tmp_path / relative_path).write_text('{"changed": true}', encoding="utf-8")

    with pytest.raises(AssertionError, match=relative_path):
        assert_repo_pipeline_artifacts_unchanged(before, tmp_path)


def test_repo_pipeline_artifact_guard_fails_when_a_test_deletes(
    tmp_path: Path,
) -> None:
    stages = tmp_path / "artifacts" / "stages"
    stages.mkdir(parents=True)
    (stages / "export.json").write_text("{}", encoding="utf-8")
    before = snapshot_repo_pipeline_artifacts(tmp_path)

    (stages / "export.json").unlink()

    with pytest.raises(AssertionError, match="artifacts/stages/export.json"):
        assert_repo_pipeline_artifacts_unchanged(before, tmp_path)


def test_repo_pipeline_artifact_guard_fails_on_identical_rewrite(
    tmp_path: Path,
) -> None:
    stages = tmp_path / "artifacts" / "stages"
    stages.mkdir(parents=True)
    manifest = stages / "extract.json"
    manifest.write_text("{}", encoding="utf-8")
    before = snapshot_repo_pipeline_artifacts(tmp_path)

    manifest.write_text("{}", encoding="utf-8")
    stat = manifest.stat()
    os.utime(manifest, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    with pytest.raises(AssertionError, match="artifacts/stages/extract.json"):
        assert_repo_pipeline_artifacts_unchanged(before, tmp_path)
