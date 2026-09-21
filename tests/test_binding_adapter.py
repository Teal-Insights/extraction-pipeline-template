"""Bindings-driven Excel/library adapter for the inverted-tree differential."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from excel_grapher.core.address_keys import normalize_key

from tests.differential.binding_adapter import (
    compute_outputs_for_writes,
    excel_writes_for_inputs,
    expressible_input_cells,
    input_kwargs_for_compute,
    overlay_series_values,
)
from tests.differential.output_specs import OutputCellSpec


def _scalar(series_id: str, address: str) -> dict[str, Any]:
    return {
        "id": series_id,
        "key_fields": [],
        "cells": [{"address": address, "key": {}}],
    }


def _shocks() -> dict[str, Any]:
    return {
        "id": "revenue_shocks",
        "key_fields": ["SCENARIO", "TIME_PERIOD"],
        "cells": [
            {
                "address": "Risks!C2",
                "key": {"SCENARIO": "base", "TIME_PERIOD": 2030},
            },
            {
                "address": "Risks!H2",
                "key": {"SCENARIO": "base", "TIME_PERIOD": 2035},
            },
            {
                "address": "Risks!BT12",
                "key": {"SCENARIO": "stress", "TIME_PERIOD": 2099},
            },
        ],
    }


def test_excel_writes_map_scalars_to_bound_addresses() -> None:
    writes = excel_writes_for_inputs(
        (_scalar("country_name", "Inputs!A1"),),
        {"country_name": "France"},
    )
    assert writes == {normalize_key("Inputs!A1"): "France"}


def test_excel_writes_overlay_matrix_records_by_key() -> None:
    writes = excel_writes_for_inputs(
        (_scalar("country_name", "Inputs!A1"), _shocks()),
        {
            "country_name": "France",
            "revenue_shocks": (
                {"SCENARIO": "base", "TIME_PERIOD": 2035, "OBS_VALUE": 1.0},
            ),
        },
    )
    assert writes[normalize_key("Inputs!A1")] == "France"
    assert writes[normalize_key("Risks!H2")] == 1.0
    assert normalize_key("Risks!C2") not in writes


def test_excel_writes_fail_closed_on_unknown_shock_key() -> None:
    with pytest.raises(LookupError, match="revenue_shocks"):
        excel_writes_for_inputs(
            (_shocks(),),
            {
                "revenue_shocks": (
                    {"SCENARIO": "base", "TIME_PERIOD": 2040, "OBS_VALUE": 1.0},
                )
            },
        )


def test_expressible_cells_are_normalized_input_addresses() -> None:
    cells = expressible_input_cells((_scalar("country_name", "Inputs!A1"), _shocks()))
    assert normalize_key("Inputs!A1") in cells
    assert normalize_key("Risks!H2") in cells
    assert len(cells) == 4


def test_overlay_series_values_patches_catalog_index() -> None:
    patched = overlay_series_values(
        _shocks(),
        (0.0, 0.0, 0.0),
        ({"SCENARIO": "base", "TIME_PERIOD": 2035, "OBS_VALUE": 1.5},),
    )
    assert patched == (0.0, 1.5, 0.0)


def test_overlay_series_values_fail_closed_on_length_mismatch() -> None:
    with pytest.raises(ValueError, match="revenue_shocks"):
        overlay_series_values(_shocks(), (0.0, 0.0), ())


def test_input_kwargs_fail_closed_on_non_record_matrix_overlay() -> None:
    def compute(*, revenue_shocks: tuple[float, ...]) -> tuple[float, ...]:
        return (1.0,)

    data = SimpleNamespace(REVENUE_SHOCKS_DEFAULT=(0.0, 0.0, 0.0))
    data.__name__ = "pkg.data"
    with pytest.raises(TypeError, match="sequence of records"):
        input_kwargs_for_compute(
            compute,
            data,
            inputs={"revenue_shocks": "not-records"},
            input_series=(_shocks(),),
        )


def test_input_kwargs_overlay_matrix_series_onto_data_defaults() -> None:
    def compute(
        *, country_name: str, revenue_shocks: tuple[float, ...]
    ) -> tuple[float, ...]:
        return (1.0,)

    data = SimpleNamespace(REVENUE_SHOCKS_DEFAULT=(0.0, 0.0, 0.0))
    data.__name__ = "pkg.data"
    kwargs = input_kwargs_for_compute(
        compute,
        data,
        inputs={
            "country_name": "France",
            "revenue_shocks": (
                {"SCENARIO": "base", "TIME_PERIOD": 2035, "OBS_VALUE": 2.0},
            ),
        },
        input_series=(_scalar("country_name", "Inputs!A1"), _shocks()),
    )
    assert kwargs == {
        "country_name": "France",
        "revenue_shocks": (0.0, 2.0, 0.0),
    }


def test_input_kwargs_without_series_keep_data_defaults_for_arrays() -> None:
    def compute(
        *, country_name: str, revenue_shocks: tuple[float, ...]
    ) -> tuple[float, ...]:
        return (1.0,)

    data = SimpleNamespace(REVENUE_SHOCKS_DEFAULT=(0.0, 0.0, 0.0))
    data.__name__ = "pkg.data"
    kwargs = input_kwargs_for_compute(
        compute,
        data,
        inputs={"country_name": "France", "revenue_shocks": ()},
        scalar_input_keys=frozenset({"country_name"}),
    )
    assert kwargs == {
        "country_name": "France",
        "revenue_shocks": (0.0, 0.0, 0.0),
    }


def _spec(label: str, address: str, compute: str) -> OutputCellSpec:
    return OutputCellSpec(label=label, address=address, compute=compute, keys=())


def test_compute_outputs_wraps_scalar_string_as_one_catalog_value() -> None:
    def compute_external_dsa_risk_rating_signal() -> str:
        return "High"

    values = compute_outputs_for_writes(
        SimpleNamespace(
            compute_external_dsa_risk_rating_signal=compute_external_dsa_risk_rating_signal
        ),
        SimpleNamespace(),
        excel_writes={},
        input_series=(),
        output_specs=(
            _spec(
                "external_dsa_risk_rating_signal",
                "Chart Data!D10",
                "compute_external_dsa_risk_rating_signal",
            ),
        ),
    )
    assert values == {"external_dsa_risk_rating_signal": "High"}


def test_compute_outputs_wraps_scalar_float_as_one_catalog_value() -> None:
    def compute_gdp() -> float:
        return 1.5

    values = compute_outputs_for_writes(
        SimpleNamespace(compute_gdp=compute_gdp),
        SimpleNamespace(),
        excel_writes={},
        input_series=(),
        output_specs=(_spec("gdp", "Out!A1", "compute_gdp"),),
    )
    assert values == {"gdp": 1.5}


def test_compute_outputs_fail_closed_when_scalar_covers_two_specs() -> None:
    def compute_rating() -> str:
        return "High"

    with pytest.raises(ValueError, match="compute_rating"):
        compute_outputs_for_writes(
            SimpleNamespace(compute_rating=compute_rating),
            SimpleNamespace(),
            excel_writes={},
            input_series=(),
            output_specs=(
                _spec("rating_a", "Out!A1", "compute_rating"),
                _spec("rating_b", "Out!B1", "compute_rating"),
            ),
        )


def test_compute_outputs_maps_one_tuple_onto_one_spec() -> None:
    def compute_rating() -> tuple[str, ...]:
        return ("High",)

    values = compute_outputs_for_writes(
        SimpleNamespace(compute_rating=compute_rating),
        SimpleNamespace(),
        excel_writes={},
        input_series=(),
        output_specs=(_spec("rating", "Out!A1", "compute_rating"),),
    )
    assert values == {"rating": "High"}


def test_compute_outputs_zips_multi_cell_sequence() -> None:
    def compute_gdp() -> tuple[float, ...]:
        return (1.0, 2.0)

    values = compute_outputs_for_writes(
        SimpleNamespace(compute_gdp=compute_gdp),
        SimpleNamespace(),
        excel_writes={},
        input_series=(),
        output_specs=(
            _spec("gdp[2030]", "Out!B1", "compute_gdp"),
            _spec("gdp[2031]", "Out!C1", "compute_gdp"),
        ),
    )
    assert values == {"gdp[2030]": 1.0, "gdp[2031]": 2.0}
