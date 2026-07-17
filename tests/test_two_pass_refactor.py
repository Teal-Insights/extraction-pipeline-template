"""Acceptance tests for the two-pass mechanical / semantic refactor split (#166)."""

from __future__ import annotations

import re
from pathlib import Path
from textwrap import dedent

import pytest

from src.internals_refactor import write_refactor_failure_diagnostic
from src.mechanical_body import MechanicalBodyDraft
from src.mechanical_naming import (
    ClusterNamingLLMResponse,
    LocalRename,
    apply_cluster_naming_response,
    apply_naming_responses_to_module,
)


def _draft_a() -> MechanicalBodyDraft:
    return MechanicalBodyDraft(
        body="_t1 = xl_number(ctx)\nreturn _t1",
        renameable_locals=("_t1",),
        lookup_table_names=(),
        group_count=1,
    )


def _draft_b() -> MechanicalBodyDraft:
    return MechanicalBodyDraft(
        body="_t1 = xl_bool(ctx)\nreturn _t1",
        renameable_locals=("_t1",),
        lookup_table_names=(),
        group_count=1,
    )


def _naming(
    original: str, replacement: str, *, summary: str
) -> ClusterNamingLLMResponse:
    return ClusterNamingLLMResponse(
        symbol_docstring=(
            f"{summary}\n\nArgs:\n    ctx: Context.\n\nReturns:\n    Value."
        ),
        renames=(LocalRename(original=original, replacement=replacement),),
        error=None,
        error_reason=None,
    )


def _mechanical_module() -> str:
    return dedent(
        '''
        from __future__ import annotations

        def helper_a(ctx):
            """Mechanically synthesized helper.

            Args:
                ctx: Workbook evaluation context.

            Returns:
                Cell value.
            """
            _t1 = xl_number(ctx)
            return _t1

        def helper_b(ctx):
            """Mechanically synthesized helper.

            Args:
                ctx: Workbook evaluation context.

            Returns:
                Cell value.
            """
            _t1 = xl_bool(ctx)
            return _t1
        '''
    ).strip()


def test_applying_two_naming_responses_is_order_independent() -> None:
    """Pass-2 applier: both application orders yield identical source (#166)."""
    module = _mechanical_module()
    response_a = _naming("_t1", "numeric_value", summary="Numeric helper.")
    response_b = _naming("_t1", "flag_value", summary="Boolean helper.")
    units = (
        ("helper_a", _draft_a(), response_a, frozenset()),
        ("helper_b", _draft_b(), response_b, frozenset()),
    )
    forward = apply_naming_responses_to_module(
        module,
        units,
        forbidden_names=frozenset({"xl_number", "xl_bool"}),
    )
    reverse = apply_naming_responses_to_module(
        module,
        tuple(reversed(units)),
        forbidden_names=frozenset({"xl_number", "xl_bool"}),
    )
    assert forward == reverse
    assert "numeric_value = xl_number(ctx)" in forward
    assert "flag_value = xl_bool(ctx)" in forward
    assert "_t1" not in forward


def test_semantic_naming_cache_payload_omits_internals_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.internals_refactor import semantic_naming_cache_payload

    monkeypatch.setattr("src.internals_refactor.refactor_model", lambda: "test-model")
    payload = semantic_naming_cache_payload(
        kind="cluster",
        unit_id="cluster:1",
        canonical_template="=A1",
        mechanical_body="_t1 = 1\nreturn _t1",
        response_schema={"type": "object"},
        member_fingerprints=(("Engine!C1", "aaa", "bbb"),),
        contract="member_sweep",
    )
    assert "internals_sha256" not in payload
    assert payload["mechanical_body_sha256"]
    assert payload["kind"] == "cluster"


def test_semantic_naming_cache_key_changes_with_mechanical_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.internals_refactor import semantic_naming_cache_key

    monkeypatch.setattr("src.internals_refactor.refactor_model", lambda: "test-model")
    key_a = semantic_naming_cache_key(
        kind="cluster",
        unit_id="cluster:1",
        canonical_template="=A1",
        mechanical_body="_t1 = 1\nreturn _t1",
        response_schema={"type": "object"},
        member_fingerprints=(("Engine!C1", "aaa", "bbb"),),
        contract="member_sweep",
    )
    key_b = semantic_naming_cache_key(
        kind="cluster",
        unit_id="cluster:1",
        canonical_template="=A1",
        mechanical_body="_t1 = 2\nreturn _t1",
        response_schema={"type": "object"},
        member_fingerprints=(("Engine!C1", "aaa", "bbb"),),
        contract="member_sweep",
    )
    assert key_a != key_b


def test_write_refactor_failure_diagnostic_uses_unit_identity_dirname(
    tmp_path: Path,
) -> None:
    dump_dir = write_refactor_failure_diagnostic(
        kind="cluster",
        target="cluster_42",
        error=ValueError("boom"),
        dump_dir=tmp_path,
        source="llm",
        model="test-model",
    )
    assert dump_dir.parent == tmp_path
    assert dump_dir.name == "cluster_42"
    assert not re.match(r"^\d{8}T\d{6}Z_", dump_dir.name)


def test_prompt_dump_observer_names_by_unit_identity(tmp_path: Path) -> None:
    from scripts.run_refactor_stage import _prompt_dump_observer

    observe = _prompt_dump_observer(tmp_path)
    observe("cluster", "helper_alpha", "prompt a")
    observe("singleton", "helper_beta", "prompt b")
    observe("cluster", "helper_alpha", "prompt a again")
    names = sorted(path.name for path in tmp_path.glob("*.md"))
    assert names == ["cluster_helper_alpha.md", "singleton_helper_beta.md"]
    assert (tmp_path / "cluster_helper_alpha.md").read_text(encoding="utf-8") == (
        "prompt a again"
    )


def test_apply_cluster_naming_response_leaves_other_helpers_untouched() -> None:
    body = apply_cluster_naming_response(
        _naming("_t1", "numeric_value", summary="Numeric helper."),
        _draft_a(),
        parameter_names=frozenset(),
        forbidden_names=frozenset({"xl_number"}),
    )
    assert body == "numeric_value = xl_number(ctx)\nreturn numeric_value"
