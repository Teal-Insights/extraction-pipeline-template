"""Bindings-driven Excel/library adapter for the inverted-tree differential."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from excel_grapher.core.address_keys import normalize_key

from tests.differential.binding_adapter import (
    call_compute,
    excel_writes_for_inputs,
    expressible_input_cells,
    input_kwargs_for_compute,
    overlay_series_values,
)


@dataclass(frozen=True)
class _FakeAxis:
    name: str


@dataclass(frozen=True)
class _FakeDomain:
    axes: tuple[_FakeAxis, ...]
    coordinates: tuple[tuple[Any, ...], ...]

    def __len__(self) -> int:
        return len(self.coordinates)


@dataclass(frozen=True)
class _FakeSeries:
    """Duck-typed named-axis series: has a domain, but is not a Sequence."""

    domain: _FakeDomain
    _values: tuple[Any, ...]

    def items(self) -> Iterator[tuple[tuple[Any, ...], Any]]:
        return zip(self.domain.coordinates, self._values, strict=True)

    def with_records(
        self, records: Iterable[tuple[tuple[Any, ...], Any]]
    ) -> _FakeSeries:
        collected = dict(records)
        values = tuple(collected[coord] for coord in self.domain.coordinates)
        return _FakeSeries(self.domain, values)

    def __getitem__(self, key: Any) -> Any:
        coord = key if isinstance(key, tuple) else (key,)
        return dict(self.items())[coord]


def _shock_series(values: tuple[Any, ...]) -> _FakeSeries:
    cells = _shocks()["cells"]
    axes = (_FakeAxis("SCENARIO"), _FakeAxis("TIME_PERIOD"))
    coordinates = tuple(
        (cell["key"]["SCENARIO"], cell["key"]["TIME_PERIOD"]) for cell in cells
    )
    return _FakeSeries(_FakeDomain(axes, coordinates[: len(values)]), values)


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


def test_overlay_series_values_patches_named_series_by_coordinate() -> None:
    patched = overlay_series_values(
        _shocks(),
        _shock_series((0.0, 0.0, 0.0)),
        ({"SCENARIO": "base", "TIME_PERIOD": 2035, "OBS_VALUE": 1.5},),
    )
    assert isinstance(patched, _FakeSeries)
    assert tuple(value for _, value in patched.items()) == (0.0, 1.5, 0.0)


def test_overlay_series_values_fail_closed_on_named_series_length_mismatch() -> None:
    with pytest.raises(ValueError, match="revenue_shocks"):
        overlay_series_values(_shocks(), _shock_series((0.0, 0.0)), ())


def test_overlay_series_values_fail_closed_on_unknown_named_series_key() -> None:
    with pytest.raises(LookupError, match="revenue_shocks"):
        overlay_series_values(
            _shocks(),
            _shock_series((0.0, 0.0, 0.0)),
            ({"SCENARIO": "base", "TIME_PERIOD": 2040, "OBS_VALUE": 1.0},),
        )


def test_overlay_series_values_fail_closed_on_key_fields_axis_mismatch() -> None:
    series = {
        "id": "revenue_shocks",
        "key_fields": ["SCENARIO", "YEAR"],
        "cells": _shocks()["cells"],
    }
    with pytest.raises(ValueError, match="key_fields"):
        overlay_series_values(
            series,
            _shock_series((0.0, 0.0, 0.0)),
            ({"SCENARIO": "base", "YEAR": 2035, "OBS_VALUE": 1.0},),
        )


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


def test_input_kwargs_overlay_named_series_defaults() -> None:
    def compute(*, country_name: str, revenue_shocks: _FakeSeries) -> _FakeSeries:
        return revenue_shocks

    data = SimpleNamespace(REVENUE_SHOCKS_DEFAULT=_shock_series((0.0, 0.0, 0.0)))
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
    assert kwargs["country_name"] == "France"
    patched = kwargs["revenue_shocks"]
    assert isinstance(patched, _FakeSeries)
    assert tuple(value for _, value in patched.items()) == (0.0, 2.0, 0.0)


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


@dataclass(frozen=True)
class FooInputs:
    country_name: str
    revenue_shocks: tuple[object, ...]

    @classmethod
    def from_defaults(cls, **overrides: object) -> FooInputs:
        country_name = overrides["country_name"]
        revenue_shocks = overrides["revenue_shocks"]
        if not isinstance(country_name, str):
            raise TypeError("country_name must be str")
        if not isinstance(revenue_shocks, tuple):
            raise TypeError("revenue_shocks must be a tuple")
        return cls(country_name=country_name, revenue_shocks=revenue_shocks)


@dataclass(frozen=True)
class BareInputs:
    country_name: str


def test_input_kwargs_for_inputs_bundle_walks_dataclass_fields() -> None:
    def compute(inputs: FooInputs) -> tuple[float, ...]:
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
    assert "inputs" not in kwargs


def test_input_kwargs_for_inputs_bundle_without_series_keep_data_defaults() -> None:
    def compute(inputs: FooInputs) -> tuple[float, ...]:
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
    assert "inputs" not in kwargs


def test_call_compute_passes_inputs_from_defaults_as_sole_argument() -> None:
    received: list[object] = []

    def compute(inputs: FooInputs) -> FooInputs:
        received.append(inputs)
        return inputs

    pkg = SimpleNamespace(FooInputs=FooInputs)
    kwargs = {
        "country_name": "France",
        "revenue_shocks": (0.0, 2.0, 0.0),
    }
    result = call_compute(pkg, compute, kwargs)
    assert result is received[0]
    assert isinstance(result, FooInputs)
    assert result == FooInputs.from_defaults(**kwargs)


def test_call_compute_fail_closed_without_from_defaults() -> None:
    def compute(inputs: BareInputs) -> BareInputs:
        return inputs

    pkg = SimpleNamespace(BareInputs=BareInputs)
    with pytest.raises(TypeError, match="from_defaults"):
        call_compute(pkg, compute, {"country_name": "France"})


def test_call_compute_fail_closed_on_keyword_leaf_signature() -> None:
    def compute(*, country_name: str) -> str:
        return country_name

    with pytest.raises(TypeError, match="from_defaults"):
        call_compute(SimpleNamespace(), compute, {"country_name": "France"})
