"""Shape-based selection between the two cluster-refactor contracts.

Contract A (``member_sweep``) keeps today's rules: helper parameters are
exactly the varying binding keys of the member cells, and derivable operand
offsets stay in the helper body. Contract B (``dimension_aware``) applies when
a cluster's formula operands vary independently along one concept and the
bindings declare distinct dimension ids for it (e.g. ``REF_AREA`` vs
``COUNTERPART_REF_AREA``); parameters and member keys are then keyed by
effective dimension id so counterpart parameters do not collide.

``variation_mode`` controls whether dimension-aware clusters are even formed
(``dominant_key_only`` splits them away); the contract itself is always
selected from cluster shape.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal, TypeAlias

from src.formula_clustering import (
    BoundAddressKeys,
    FormulaCluster,
    cluster_has_independent_operand_variation,
)
from src.refactor_bindings import KeyConceptSpec
from src.workbook_addresses import ProjectionColumnLayout

ClusterRefactorContract: TypeAlias = Literal["member_sweep", "dimension_aware"]


def concepts_with_multiple_dimensions(
    dimension_ids: frozenset[str],
    key_vocabulary: Sequence[KeyConceptSpec],
) -> dict[str, tuple[str, ...]]:
    """Group the given dimension ids by concept, keeping concepts with >1 id."""
    concept_by_dimension = {item.dimension_id: item.concept for item in key_vocabulary}
    grouped: dict[str, list[str]] = {}
    for dimension_id in sorted(dimension_ids):
        concept = concept_by_dimension.get(dimension_id)
        if concept is None:
            continue
        grouped.setdefault(concept, []).append(dimension_id)
    return {
        concept: tuple(dimension_ids)
        for concept, dimension_ids in grouped.items()
        if len(dimension_ids) > 1
    }


def _dimensions_with_operand_variation(
    cluster: FormulaCluster,
    formula_nodes: Mapping[str, str],
    bound_address_keys: BoundAddressKeys,
    varying_dimension_ids: frozenset[str],
    *,
    workbook_path: Path | None,
    layout: ProjectionColumnLayout | None,
) -> frozenset[str]:
    return frozenset(
        dimension_id
        for dimension_id in varying_dimension_ids
        if cluster_has_independent_operand_variation(
            cluster,
            formula_nodes,
            bound_address_keys,
            frozenset({dimension_id}),
            workbook_path=workbook_path,
            layout=layout,
        )
    )


def select_cluster_refactor_contract(
    cluster: FormulaCluster,
    formula_nodes: Mapping[str, str],
    bound_address_keys: BoundAddressKeys,
    varying_dimension_ids: frozenset[str],
    *,
    key_vocabulary: Sequence[KeyConceptSpec],
    workbook_path: Path | None = None,
    layout: ProjectionColumnLayout | None = None,
) -> ClusterRefactorContract | None:
    """Select the refactor contract for one cluster from its shape.

    Returns ``"member_sweep"`` (Contract A) when the cluster only varies along
    member-cell sweep keys, ``"dimension_aware"`` (Contract B) when formula
    operands vary independently along a dimension whose concept is covered by
    distinct dimension ids in the member keys, and ``None`` when the operand
    variation cannot be routed by the declared bindings (the cluster must be
    skipped as ``operand_level_variation_unsupported``).
    """
    flagged = _dimensions_with_operand_variation(
        cluster,
        formula_nodes,
        bound_address_keys,
        varying_dimension_ids,
        workbook_path=workbook_path,
        layout=layout,
    )
    if not flagged:
        return "member_sweep"
    covered = {
        dimension_id
        for dimension_ids in concepts_with_multiple_dimensions(
            varying_dimension_ids, key_vocabulary
        ).values()
        for dimension_id in dimension_ids
    }
    if flagged <= covered:
        return "dimension_aware"
    return None
