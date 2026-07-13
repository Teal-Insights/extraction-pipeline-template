from __future__ import annotations

from typing import cast

import pytest
from excel_grapher.exporter import BaseProjectionManifest, ProjectionResult
from excel_grapher.grapher.graph import DependencyGraph
from excel_grapher.grapher.node import Node

from src.formula_clustering import FormulaCluster, cluster_graph_formulas
from src.refactor_order import (
    assert_valid_cluster_refactor_order,
    compute_cluster_refactor_order,
)
from src.subgraph_projection import build_refactor_projection
from src.workbook_addresses import parse_workbook_address


def test_refactor_projection_uses_optimal_compression(synthetic_graph) -> None:
    projection = build_refactor_projection(synthetic_graph)
    manifest = projection.manifest
    assert isinstance(manifest, BaseProjectionManifest)
    assert manifest.kind == "optimal_compression"
    assert len(projection) <= len(synthetic_graph)


def test_cluster_graph_formulas_finds_parallel_engine_row(
    synthetic_projection,
    synthetic_bound_address_keys,
    synthetic_pipeline_config_fixture,
) -> None:
    clusters = cluster_graph_formulas(
        synthetic_projection,
        bound_address_keys=synthetic_bound_address_keys,
        workbook_path=synthetic_pipeline_config_fixture.workbook_path,
        layout=synthetic_pipeline_config_fixture.projection_layout,
    )
    parallel = next(
        cluster for cluster in clusters if cluster.members == ("Engine!B2", "Engine!C2")
    )
    assert parallel.row == 2


def test_compute_cluster_refactor_order_respects_dependencies(
    synthetic_projection,
    synthetic_bound_address_keys,
    synthetic_pipeline_config_fixture,
) -> None:
    clusters = cluster_graph_formulas(
        synthetic_projection,
        bound_address_keys=synthetic_bound_address_keys,
        workbook_path=synthetic_pipeline_config_fixture.workbook_path,
        layout=synthetic_pipeline_config_fixture.projection_layout,
    )
    ordered = compute_cluster_refactor_order(synthetic_projection, clusters)

    assert len(ordered) == 2
    assert ordered[0].members == ("Engine!B2", "Engine!C2")
    assert ordered[1].members == ("Outputs!B1", "Outputs!C1")
    assert_valid_cluster_refactor_order(synthetic_projection, ordered)
    assert len({cluster.cluster_id for cluster in ordered}) == len(ordered)


class _StubProjection:
    def get_dependencies(self, address: str) -> tuple[str, ...]:
        if address == "Engine!B3":
            return ("Engine!B2",)
        if address in {"Outputs!B1", "Outputs!C1"}:
            return ("Engine!B2",) if address == "Outputs!B1" else ("Engine!C2",)
        return ()


def test_compute_cluster_refactor_order_interleaves_singleton_and_multi_member() -> (
    None
):
    multi_member = FormulaCluster(
        cluster_id=0,
        members=("Engine!B2", "Engine!C2"),
        canonical_template="=Inputs!A1+Inputs!B1+1",
        row=2,
    )
    singleton = FormulaCluster(
        cluster_id=1,
        members=("Engine!B3",),
        canonical_template="=Engine!B2*2",
        row=3,
    )
    clusters = (multi_member, singleton)
    projection = cast(ProjectionResult, _StubProjection())

    ordered = compute_cluster_refactor_order(projection, clusters)

    assert ordered == (multi_member, singleton)
    assert_valid_cluster_refactor_order(projection, ordered)


def test_compute_cluster_refactor_order_includes_all_eligible_clusters(
    synthetic_projection,
    synthetic_bound_address_keys,
    synthetic_pipeline_config_fixture,
) -> None:
    clusters = cluster_graph_formulas(
        synthetic_projection,
        bound_address_keys=synthetic_bound_address_keys,
        workbook_path=synthetic_pipeline_config_fixture.workbook_path,
        layout=synthetic_pipeline_config_fixture.projection_layout,
    )
    eligible = [cluster for cluster in clusters if cluster.members]
    ordered = compute_cluster_refactor_order(synthetic_projection, clusters)
    assert len(ordered) == len(eligible)
    assert_valid_cluster_refactor_order(synthetic_projection, ordered)


def _formula_node(sheet: str, column: str, row: int, formula: str) -> Node:
    return Node(
        sheet=sheet,
        column=column,
        row=row,
        formula=formula,
        normalized_formula=formula,
        value=None,
        is_leaf=False,
        metadata={},
    )


def _leaf_node(sheet: str, column: str, row: int, value: object = 0) -> Node:
    return Node(
        sheet=sheet,
        column=column,
        row=row,
        formula=None,
        normalized_formula=None,
        value=value,
        is_leaf=True,
        metadata={},
    )


def _inter_cluster_cycle_graph() -> tuple[DependencyGraph, dict[str, dict[str, int]]]:
    """Acyclic cell graph whose formula clusters form a dependency cycle.

    Two formula families (``+`` vs ``*``) share binding-key concepts so each
    family clusters across periods. Cross-period lag edges then make the
    clusters depend on each other even though ``evaluation_order`` succeeds.
    """
    graph = DependencyGraph()
    for address, value in (
        ("Inputs!A2", 1),
        ("Inputs!A3", 1),
        ("Inputs!B1", 0),
    ):
        sheet, column, row = parse_workbook_address(address)
        graph.add_node(_leaf_node(sheet, column, row, value))

    formulas = {
        "Engine!B2": "=Inputs!A2+Inputs!B1",
        "Engine!C2": "=Inputs!A2*Engine!B2",
        "Engine!B3": "=Inputs!A3+Engine!C2",
        "Engine!C3": "=Inputs!A3*Engine!B3",
    }
    for address, formula in formulas.items():
        sheet, column, row = parse_workbook_address(address)
        graph.add_node(_formula_node(sheet, column, row, formula))

    for dependent, dependency in (
        ("Engine!B2", "Inputs!A2"),
        ("Engine!B2", "Inputs!B1"),
        ("Engine!C2", "Inputs!A2"),
        ("Engine!C2", "Engine!B2"),
        ("Engine!B3", "Inputs!A3"),
        ("Engine!B3", "Engine!C2"),
        ("Engine!C3", "Inputs!A3"),
        ("Engine!C3", "Engine!B3"),
    ):
        graph.add_edge(dependent, dependency)

    bindings = {
        "Inputs!A2": {"TIME_PERIOD": 1},
        "Inputs!A3": {"TIME_PERIOD": 2},
        "Inputs!B1": {"TIME_PERIOD": 0},
        "Engine!B2": {"TIME_PERIOD": 1},
        "Engine!C2": {"TIME_PERIOD": 1},
        "Engine!B3": {"TIME_PERIOD": 2},
        "Engine!C3": {"TIME_PERIOD": 2},
    }
    return graph, bindings


def test_cluster_detection_can_create_inter_cluster_cycle_on_acyclic_cell_graph() -> (
    None
):
    """Clustering ignores topology; refactor ordering then hard-fails on cycles.

    Cell DAG (evaluation order succeeds)::

        Inputs!B1 ──► Engine!B2 ──► Engine!C2 ──► Engine!B3 ──► Engine!C3
        Inputs!A2 ─┘           ─┘
        Inputs!A3 ─────────────────────────────┘           ─┘

    Distinct AST shapes (``+`` vs ``*``) yield two multi-member clusters::

        cluster + : {Engine!B2, Engine!B3}
        cluster * : {Engine!C2, Engine!C3}

    External deps then form a cluster cycle: B3→C2 and C2→B2 / C3→B3.
    """
    graph, bindings = _inter_cluster_cycle_graph()

    assert graph.evaluation_order() == [
        "Inputs!A2",
        "Inputs!B1",
        "Engine!B2",
        "Engine!C2",
        "Inputs!A3",
        "Engine!B3",
        "Engine!C3",
    ]

    clusters = cluster_graph_formulas(graph, bound_address_keys=bindings)
    members = {cluster.members for cluster in clusters}
    assert members == {
        ("Engine!B2", "Engine!B3"),
        ("Engine!C2", "Engine!C3"),
    }

    with pytest.raises(
        ValueError,
        match="Cycle detected in cluster refactor dependencies",
    ):
        compute_cluster_refactor_order(graph, clusters)
