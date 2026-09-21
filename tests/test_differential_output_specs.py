"""Unit tests for derived-series output specs and collision→None matching."""

from __future__ import annotations

from typing import Any

import pytest

from tests.differential.output_specs import (
    OutputCellSpec,
    outputs_from_records,
    outputs_from_tuple,
    specs_from_output_series,
)


def _series(
    *,
    series_id: str,
    compute_name: str,
    key_fields: tuple[str, ...],
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "id": series_id,
        "compute_name": compute_name,
        "key_fields": list(key_fields),
        "cells": cells,
    }


def test_specs_from_output_series_builds_one_spec_per_cell() -> None:
    series = [
        _series(
            series_id="gdp",
            compute_name="compute_gdp",
            key_fields=("TIME_PERIOD",),
            cells=[
                {"address": "Out!B1", "key": {"TIME_PERIOD": 2030}},
                {"address": "Out!C1", "key": {"TIME_PERIOD": 2031}},
            ],
        )
    ]

    specs = specs_from_output_series(series)

    assert specs == (
        OutputCellSpec(
            label="gdp[2030]",
            address="Out!B1",
            compute="compute_gdp",
            keys=(("TIME_PERIOD", 2030),),
        ),
        OutputCellSpec(
            label="gdp[2031]",
            address="Out!C1",
            compute="compute_gdp",
            keys=(("TIME_PERIOD", 2031),),
        ),
    )


def test_specs_from_output_series_keyless_label_is_series_id() -> None:
    series = [
        _series(
            series_id="scalar_out",
            compute_name="compute_scalar_out",
            key_fields=(),
            cells=[{"address": "Out!A1", "key": {}}],
        )
    ]

    specs = specs_from_output_series(series)

    assert specs[0].label == "scalar_out"
    assert specs[0].keys == ()


def test_outputs_from_records_key_matches_and_none_for_missing() -> None:
    specs = (
        OutputCellSpec(
            label="gdp[2030]",
            address="Out!B1",
            compute="compute_gdp",
            keys=(("TIME_PERIOD", 2030),),
        ),
        OutputCellSpec(
            label="gdp[2031]",
            address="Out!C1",
            compute="compute_gdp",
            keys=(("TIME_PERIOD", 2031),),
        ),
    )
    records = {
        "compute_gdp": [
            {"TIME_PERIOD": 2030, "OBS_VALUE": 1.5},
        ]
    }

    values = outputs_from_records(specs, records)

    assert values == {"gdp[2030]": 1.5, "gdp[2031]": None}


def test_outputs_from_records_nulls_ambiguous_compute_key_collisions() -> None:
    shared_keys = (("TIME_PERIOD", 2030),)
    specs = (
        OutputCellSpec(
            label="paris[2030]",
            address="Paris!B1",
            compute="compute_shared",
            keys=shared_keys,
        ),
        OutputCellSpec(
            label="moderate[2030]",
            address="Moderate!B1",
            compute="compute_shared",
            keys=shared_keys,
        ),
        OutputCellSpec(
            label="solo[2030]",
            address="Solo!B1",
            compute="compute_solo",
            keys=shared_keys,
        ),
    )
    records = {
        "compute_shared": [{"TIME_PERIOD": 2030, "OBS_VALUE": 9.0}],
        "compute_solo": [{"TIME_PERIOD": 2030, "OBS_VALUE": 3.0}],
    }

    values = outputs_from_records(specs, records)

    assert values["paris[2030]"] is None
    assert values["moderate[2030]"] is None
    assert values["solo[2030]"] == 3.0


def test_outputs_from_tuple_zips_catalog_order() -> None:
    specs = (
        OutputCellSpec(
            label="gdp[2030]",
            address="Out!B1",
            compute="compute_gdp",
            keys=(("TIME_PERIOD", 2030),),
        ),
        OutputCellSpec(
            label="gdp[2031]",
            address="Out!C1",
            compute="compute_gdp",
            keys=(("TIME_PERIOD", 2031),),
        ),
    )

    values = outputs_from_tuple(specs, {"compute_gdp": (1.0, 2.0)})

    assert values == {"gdp[2030]": 1.0, "gdp[2031]": 2.0}


def test_outputs_from_tuple_fail_closed_on_length_mismatch() -> None:
    specs = (
        OutputCellSpec(
            label="rating_a",
            address="Out!A1",
            compute="compute_rating",
            keys=(),
        ),
        OutputCellSpec(
            label="rating_b",
            address="Out!B1",
            compute="compute_rating",
            keys=(),
        ),
    )

    with pytest.raises(ValueError, match="compute_rating"):
        outputs_from_tuple(specs, {"compute_rating": ("High",)})
