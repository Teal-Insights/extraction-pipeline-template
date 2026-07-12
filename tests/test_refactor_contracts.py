"""Tests for shape-based cluster refactor contract selection."""

from __future__ import annotations

from src.formula_clustering import FormulaCluster
from src.refactor_bindings import KeyConceptSpec
from src.refactor_contracts import (
    concepts_with_multiple_dimensions,
    select_cluster_refactor_contract,
)

TIME_PERIOD_SPEC = KeyConceptSpec(
    dimension_id="TIME_PERIOD",
    concept="TIME_PERIOD",
    dtype="int",
    suggested_param_name="time_period",
)
REF_AREA_SPEC = KeyConceptSpec(
    dimension_id="REF_AREA",
    concept="REF_AREA",
    dtype="str",
    suggested_param_name="ref_area",
)
COUNTERPART_REF_AREA_SPEC = KeyConceptSpec(
    dimension_id="COUNTERPART_REF_AREA",
    concept="REF_AREA",
    dtype="str",
    suggested_param_name="counterpart_ref_area",
)
PROJECTION_PERIOD_SPEC = KeyConceptSpec(
    dimension_id="PROJECTION_PERIOD",
    concept="TIME_PERIOD",
    dtype="int",
    suggested_param_name="projection_period",
)
REFERENCE_PERIOD_SPEC = KeyConceptSpec(
    dimension_id="REFERENCE_PERIOD",
    concept="TIME_PERIOD",
    dtype="int",
    suggested_param_name="reference_period",
)

TRADE_BALANCE_CLUSTER = FormulaCluster(
    cluster_id=0,
    members=("Engine!B5", "Engine!C5", "Engine!D5"),
    canonical_template="=Inputs!B10-Inputs!C10",
    row=5,
)

TRADE_BALANCE_FORMULAS = {
    "Engine!B5": "=Inputs!B10-Inputs!C10",
    "Engine!C5": "=Inputs!B11-Inputs!C11",
    "Engine!D5": "=Inputs!B12-Inputs!C12",
}

VARIABLE_COUNTRY_PAIR_BINDINGS = {
    "Inputs!B10": {"REF_AREA": "US", "TIME_PERIOD": 1},
    "Inputs!C10": {"REF_AREA": "CN", "TIME_PERIOD": 1},
    "Inputs!B11": {"REF_AREA": "DE", "TIME_PERIOD": 1},
    "Inputs!C11": {"REF_AREA": "FR", "TIME_PERIOD": 1},
    "Inputs!B12": {"REF_AREA": "JP", "TIME_PERIOD": 1},
    "Inputs!C12": {"REF_AREA": "KR", "TIME_PERIOD": 1},
}


def test_concepts_with_multiple_dimensions_groups_shared_concepts() -> None:
    collisions = concepts_with_multiple_dimensions(
        frozenset({"REF_AREA", "COUNTERPART_REF_AREA", "TIME_PERIOD"}),
        (TIME_PERIOD_SPEC, REF_AREA_SPEC, COUNTERPART_REF_AREA_SPEC),
    )
    assert collisions == {"REF_AREA": ("COUNTERPART_REF_AREA", "REF_AREA")}


def test_concepts_with_multiple_dimensions_ignores_unknown_dimension_ids() -> None:
    collisions = concepts_with_multiple_dimensions(
        frozenset({"REF_AREA", "UNKNOWN_DIMENSION"}),
        (REF_AREA_SPEC,),
    )
    assert collisions == {}


def test_selects_member_sweep_without_operand_variation() -> None:
    """A plain column sweep stays on Contract A."""
    cluster = FormulaCluster(
        cluster_id=1,
        members=("Engine!C6", "Engine!D6"),
        canonical_template="=Inputs!C1",
        row=6,
    )
    formula_nodes = {"Engine!C6": "=Inputs!C1", "Engine!D6": "=Inputs!D1"}
    bindings = {
        "Inputs!C1": {"TIME_PERIOD": 1},
        "Inputs!D1": {"TIME_PERIOD": 2},
    }
    contract = select_cluster_refactor_contract(
        cluster,
        formula_nodes,
        bindings,
        frozenset({"TIME_PERIOD"}),
        key_vocabulary=(TIME_PERIOD_SPEC,),
    )
    assert contract == "member_sweep"


def test_selects_member_sweep_when_shared_concepts_do_not_vary_per_operand() -> None:
    """Distinct dimension ids sharing a concept alone do not require Contract B."""
    cluster = FormulaCluster(
        cluster_id=2,
        members=("Engine!C10", "Engine!D10"),
        canonical_template="=Inputs!C4",
        row=10,
    )
    formula_nodes = {"Engine!C10": "=Inputs!C4", "Engine!D10": "=Inputs!D4"}
    bindings = {
        "Inputs!C4": {"TIME_PERIOD": 1},
        "Inputs!D4": {"TIME_PERIOD": 2},
    }
    contract = select_cluster_refactor_contract(
        cluster,
        formula_nodes,
        bindings,
        frozenset({"PROJECTION_PERIOD", "REFERENCE_PERIOD"}),
        key_vocabulary=(
            TIME_PERIOD_SPEC,
            PROJECTION_PERIOD_SPEC,
            REFERENCE_PERIOD_SPEC,
        ),
    )
    assert contract == "member_sweep"


def test_returns_none_for_operand_variation_without_distinct_dimension_ids() -> None:
    """Trade-balance operand variation stays unsupported without counterpart ids."""
    trade_balance_bindings = {
        "Inputs!B10": {"REF_AREA": "US", "TIME_PERIOD": 1},
        "Inputs!C10": {"REF_AREA": "CN", "TIME_PERIOD": 1},
        "Inputs!B11": {"REF_AREA": "US", "TIME_PERIOD": 2},
        "Inputs!C11": {"REF_AREA": "CN", "TIME_PERIOD": 2},
        "Inputs!B12": {"REF_AREA": "US", "TIME_PERIOD": 3},
        "Inputs!C12": {"REF_AREA": "CN", "TIME_PERIOD": 3},
    }
    contract = select_cluster_refactor_contract(
        TRADE_BALANCE_CLUSTER,
        TRADE_BALANCE_FORMULAS,
        trade_balance_bindings,
        frozenset({"REF_AREA", "TIME_PERIOD"}),
        key_vocabulary=(TIME_PERIOD_SPEC, REF_AREA_SPEC),
    )
    assert contract is None


def test_selects_dimension_aware_when_counterpart_dimension_ids_cover_variation() -> (
    None
):
    """Variable country pairs route to Contract B once counterpart ids exist."""
    contract = select_cluster_refactor_contract(
        TRADE_BALANCE_CLUSTER,
        TRADE_BALANCE_FORMULAS,
        VARIABLE_COUNTRY_PAIR_BINDINGS,
        frozenset({"REF_AREA", "COUNTERPART_REF_AREA"}),
        key_vocabulary=(
            TIME_PERIOD_SPEC,
            REF_AREA_SPEC,
            COUNTERPART_REF_AREA_SPEC,
        ),
    )
    assert contract == "dimension_aware"


def test_returns_none_when_flagged_dimension_lacks_counterpart_coverage() -> None:
    """A shared concept elsewhere must not unlock unrelated operand variation."""
    contract = select_cluster_refactor_contract(
        TRADE_BALANCE_CLUSTER,
        TRADE_BALANCE_FORMULAS,
        VARIABLE_COUNTRY_PAIR_BINDINGS,
        frozenset({"REF_AREA", "PROJECTION_PERIOD", "REFERENCE_PERIOD"}),
        key_vocabulary=(
            REF_AREA_SPEC,
            PROJECTION_PERIOD_SPEC,
            REFERENCE_PERIOD_SPEC,
        ),
    )
    assert contract is None
