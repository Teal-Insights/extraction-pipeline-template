"""Materialize ``dist/`` as a disposable projection of cached artifacts."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.codegen_cache import (
    load_codegen_payload,
    save_codegen_payload,
    write_generated_modules,
)
from src.export_validation_assets import (
    export_reference_reports,
    seed_validation_harness,
)
from src.pipeline_config import PipelineConfig
from src.qmd_python_validation import (
    DOCUMENTATION_BASELINE_DEV_DEPS,
    VALIDATION_BASELINE_DEV_DEPS,
    render_dist_pyproject_toml,
    write_dist_readme,
)
from src.soft_error_compute_codegen import (
    ensure_xl_error_exception_import,
    rewrite_compute_measure_assignment,
)

PACKAGE_CACHE_KEYS_FILENAME = ".pipeline-cache-keys.json"
DIST_GITIGNORE_CONTENT = """
*.egg-info/
*.pyc
__pycache__/
.venv/
_validate_user_guide_cells.py
tests/results/local/
"""
_GENERATED_ROOT_MODULE_NAMES = frozenset(
    {"__init__.py", "api.py", "data.py", "runtime.py", "internals.py"}
)
_PACKAGE_MODULE_NAMES = (
    "__init__.py",
    "api.py",
    "data.py",
    "runtime.py",
    "internals.py",
)


@dataclass(frozen=True)
class PackageCacheKeys:
    """Cache keys recorded beside a materialized ``dist/`` tree."""

    codegen_key: str
    internals_key: str | None = None


def package_cache_keys_path(dist_root: Path) -> Path:
    return dist_root / PACKAGE_CACHE_KEYS_FILENAME


def write_package_cache_keys(dist_root: Path, keys: PackageCacheKeys) -> None:
    dist_root.mkdir(parents=True, exist_ok=True)
    payload = {
        "codegen_key": keys.codegen_key,
        "internals_key": keys.internals_key,
    }
    package_cache_keys_path(dist_root).write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_package_cache_keys(dist_root: Path) -> PackageCacheKeys | None:
    path = package_cache_keys_path(dist_root)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid package cache keys payload: {path}")
    codegen_key = payload.get("codegen_key")
    if not isinstance(codegen_key, str) or not codegen_key:
        raise ValueError(f"package cache keys missing codegen_key: {path}")
    internals_key = payload.get("internals_key")
    if internals_key is not None and not isinstance(internals_key, str):
        raise ValueError(f"package cache keys have non-string internals_key: {path}")
    return PackageCacheKeys(codegen_key=codegen_key, internals_key=internals_key)


def apply_export_api_rewrite(modules: dict[str, str]) -> dict[str, str]:
    """Apply the export-stage ``api.py`` soft-error rewrite to module texts."""
    rewritten_modules = dict(modules)
    api_source = rewritten_modules.get("api.py")
    if api_source is None:
        return rewritten_modules
    rewritten = "\n".join(rewrite_compute_measure_assignment(api_source.splitlines()))
    if api_source.endswith("\n"):
        rewritten += "\n"
    rewritten_modules["api.py"] = ensure_xl_error_exception_import(rewritten)
    return rewritten_modules


def load_pristine_internals_from_codegen(codegen_key: str) -> str:
    """Return pristine ``internals.py`` text from the codegen cache.

    Fails loudly when the payload or module is missing — never falls back to
    whatever is currently on disk under ``dist/``, which may already be
    refactored.
    """
    modules = load_codegen_payload(codegen_key)
    if modules is None:
        raise FileNotFoundError(
            "codegen cache payload missing for "
            f"key={codegen_key[:12]}; cannot resolve pristine internals "
            "for the parity oracle"
        )
    source = modules.get("internals.py")
    if source is None:
        raise KeyError(
            f"codegen payload key={codegen_key[:12]} has no internals.py module"
        )
    return source


def internals_cache_path(internals_key: str, *, cache_dir: Path | None = None) -> Path:
    if cache_dir is None:
        # Look up at call time so pytest cache redirects stay in sync.
        from src.internals_refactor import DEFAULT_INTERNALS_CACHE_DIR

        resolved = DEFAULT_INTERNALS_CACHE_DIR
    else:
        resolved = cache_dir
    return resolved / f"{internals_key}.py"


def load_refactored_internals(
    internals_key: str, *, cache_dir: Path | None = None
) -> str:
    path = internals_cache_path(internals_key, cache_dir=cache_dir)
    if not path.is_file():
        raise FileNotFoundError(
            f"internals cache miss for key={internals_key[:12]}: {path}"
        )
    return path.read_text(encoding="utf-8")


def _read_package_modules(package_root: Path) -> dict[str, str] | None:
    modules: dict[str, str] = {}
    for name in _PACKAGE_MODULE_NAMES:
        path = package_root / name
        if not path.is_file():
            return None
        modules[name] = path.read_text(encoding="utf-8")
    return modules


def _write_dist_tree(config: PipelineConfig, modules: dict[str, str]) -> None:
    """Write package modules and dist metadata/harness files."""
    write_generated_modules(config.package_root, modules)

    for stale_module in _GENERATED_ROOT_MODULE_NAMES:
        stale_path = config.dist_root / stale_module
        if stale_path.is_file():
            stale_path.unlink()

    (config.dist_root / ".gitignore").write_text(
        DIST_GITIGNORE_CONTENT, encoding="utf-8"
    )
    (config.dist_root / "pyproject.toml").write_text(
        render_dist_pyproject_toml(
            dev_dependencies=list(DOCUMENTATION_BASELINE_DEV_DEPS),
            validation_dependencies=list(VALIDATION_BASELINE_DEV_DEPS),
            metadata=config.dist_metadata,
        ),
        encoding="utf-8",
    )
    write_dist_readme(config.dist_root, metadata=config.dist_metadata)
    seed_validation_harness(config=config)


def materialize_package(
    config: PipelineConfig,
    *,
    codegen_key: str,
    internals_key: str | None = None,
    include_reference_reports: bool = False,
) -> None:
    """Write the complete ``dist/`` tree from cache plus config.

    This is the single writer for the generated package projection. Export and
    mid-pipeline stage entry both call it so ``dist/`` stays disposable.
    """
    modules = load_codegen_payload(codegen_key)
    if modules is None:
        raise FileNotFoundError(
            f"codegen cache payload missing for key={codegen_key[:12]}; "
            "cannot materialize dist/"
        )
    modules = apply_export_api_rewrite(dict(modules))
    if internals_key is not None:
        modules["internals.py"] = load_refactored_internals(internals_key)

    _write_dist_tree(config, modules)
    if include_reference_reports:
        export_reference_reports(config=config)

    write_package_cache_keys(
        config.dist_root,
        PackageCacheKeys(codegen_key=codegen_key, internals_key=internals_key),
    )


def adopt_codegen_cache_from_dist(
    config: PipelineConfig,
    *,
    expected_codegen_key: str,
    projection_cache_key: str,
) -> bool:
    """Adopt pristine package modules into ``.cache/codegen/`` when keys match.

    Only safe when ``dist/`` still holds pristine ``internals.py`` (no
    ``internals_key`` in the sidecar). A refactored package must not be written
    into the codegen cache — that would poison the parity oracle.
    """
    keys = read_package_cache_keys(config.dist_root)
    if keys is None or keys.codegen_key != expected_codegen_key:
        return False
    if keys.internals_key is not None:
        return False
    modules = _read_package_modules(config.package_root)
    if modules is None:
        return False
    # Dist holds post-rewrite api.py; re-materialize re-applies the rewrite,
    # which is idempotent for already-rewritten sources.
    save_codegen_payload(
        modules,
        cache_key=expected_codegen_key,
        projection_cache_key=projection_cache_key,
    )
    return True


def adopt_internals_cache_from_dist(
    config: PipelineConfig,
    *,
    expected_codegen_key: str,
    internals_key: str,
) -> bool:
    """Copy committed ``dist`` internals into ``.cache/internals/`` when keys match."""
    keys = read_package_cache_keys(config.dist_root)
    if (
        keys is None
        or keys.codegen_key != expected_codegen_key
        or keys.internals_key != internals_key
    ):
        return False
    source_path = config.package_root / "internals.py"
    if not source_path.is_file():
        return False
    destination = internals_cache_path(internals_key)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_path, destination)
    return True


def try_materialize_refactored_package_from_cache(
    config: PipelineConfig,
    *,
    codegen_key: str,
    expected_internals_key: str | None = None,
) -> bool:
    """Materialize dist from caches when a recorded ``internals_key`` is available.

    On a cold ``.cache/internals/`` but matching committed ``dist/`` keys, adopt
    the package module into the internals cache first. When the codegen cache is
    also cold, reconstruct non-oracle module texts from the committed package
    without writing them into ``.cache/codegen/`` (which must stay pristine).

    When ``expected_internals_key`` is provided, the sidecar ``internals_key`` must
    match it exactly — otherwise adoption is refused so a stale content key cannot
    skip Pass 1 / parity / Pass 2.

    Returns True when materialization succeeded and the refactor stage can skip.
    """
    keys = read_package_cache_keys(config.dist_root)
    if keys is None or keys.codegen_key != codegen_key or keys.internals_key is None:
        return False
    internals_key = keys.internals_key
    if expected_internals_key is not None and internals_key != expected_internals_key:
        return False
    cache_path = internals_cache_path(internals_key)
    if not cache_path.is_file():
        if not adopt_internals_cache_from_dist(
            config,
            expected_codegen_key=codegen_key,
            internals_key=internals_key,
        ):
            return False

    modules = load_codegen_payload(codegen_key)
    if modules is None:
        modules = _read_package_modules(config.package_root)
        if modules is None:
            return False
        modules = apply_export_api_rewrite(modules)
        modules["internals.py"] = load_refactored_internals(internals_key)
        _write_dist_tree(config, modules)
        write_package_cache_keys(
            config.dist_root,
            PackageCacheKeys(codegen_key=codegen_key, internals_key=internals_key),
        )
        return True

    materialize_package(
        config,
        codegen_key=codegen_key,
        internals_key=internals_key,
    )
    return True
