"""Map inverted-tree ``compute_*`` calls to Excel cells via derived series."""

from __future__ import annotations

import dataclasses
import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from excel_grapher.core.address_keys import normalize_key

_RECORD_VALUE_FIELD = "OBS_VALUE"


def _cell_key(cell: Mapping[str, Any], key_fields: Sequence[str]) -> tuple[Any, ...]:
    key = cell["key"]
    return tuple(key[field] for field in key_fields)


def _record_key(
    record: Mapping[str, Any], key_fields: Sequence[str]
) -> tuple[Any, ...]:
    return tuple(record[field] for field in key_fields)


def _default_attr_name(parameter: str) -> str:
    return f"{parameter.upper()}_DEFAULT"


def expressible_input_cells(
    input_series: Sequence[Mapping[str, Any]],
) -> frozenset[str]:
    """Normalized addresses of every bound input cell."""
    return frozenset(
        normalize_key(str(cell["address"]))
        for series in input_series
        for cell in series["cells"]
    )


def _record_sequence(value: object) -> Sequence[Mapping[str, Any]]:
    if not value:
        return ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return cast(Sequence[Mapping[str, Any]], value)
    raise TypeError(f"expected a sequence of records, got {type(value).__name__}")


def _named_series_domain_size(value: object) -> int | None:
    """Return ``len(value.domain)`` for a named-axis series, else ``None``.

    Generated ``data.*_DEFAULT`` tensors are not sequences: they have a
    ``domain`` and ``items()`` / ``with_records()``, but no ``__len__``.
    """
    if isinstance(value, (str, bytes, Sequence)):
        return None
    domain = getattr(value, "domain", None)
    if domain is None:
        return None
    try:
        return len(domain)
    except TypeError:
        return None


def _axis_names(default: object) -> tuple[str, ...]:
    axes = getattr(getattr(default, "domain", None), "axes", ())
    names: list[str] = []
    for axis in axes:
        name = getattr(axis, "name", None)
        if not isinstance(name, str) or not name:
            raise TypeError(
                f"named series domain axes must have string names, got {axis!r}"
            )
        names.append(name)
    return tuple(names)


def _overlay_named_series(
    series: Mapping[str, Any],
    default: object,
    records: Sequence[Mapping[str, Any]],
) -> object:
    series_id = str(series["id"])
    cells = series["cells"]
    size = _named_series_domain_size(default)
    if size != len(cells):
        raise ValueError(
            f"{series_id} default length {size} does not match {len(cells)} bound cells"
        )
    if not records:
        return default
    with_records = getattr(default, "with_records", None)
    items = getattr(default, "items", None)
    if not callable(with_records) or not callable(items):
        raise TypeError(
            f"{series_id} default is a named series but has no items/with_records"
        )
    axis_names = _axis_names(default)
    key_fields = tuple(series["key_fields"])
    if set(key_fields) != set(axis_names):
        raise ValueError(
            f"{series_id} key_fields {key_fields} do not match series axes {axis_names}"
        )
    merged = dict(items())
    for record in records:
        coord = tuple(record[field] for field in axis_names)
        if coord not in merged:
            raise LookupError(
                f"{series_id} has no cell for "
                f"{dict(zip(axis_names, coord, strict=True))}"
            )
        merged[coord] = record[_RECORD_VALUE_FIELD]
    return with_records(tuple(merged.items()))


def overlay_series_values(
    series: Mapping[str, Any],
    default: object,
    records: Sequence[Mapping[str, Any]] = (),
) -> object:
    """Return catalog-order values, or a named-axis series, with sparse overlays."""
    if _named_series_domain_size(default) is not None:
        return _overlay_named_series(series, default, records)
    series_id = str(series["id"])
    cells = series["cells"]
    if not isinstance(default, Sequence) or isinstance(default, (str, bytes)):
        raise TypeError(
            f"{series_id} default must be a sequence or named series, got "
            f"{type(default).__name__}"
        )
    if len(default) != len(cells):
        raise ValueError(
            f"{series_id} default length {len(default)} does not match "
            f"{len(cells)} bound cells"
        )
    values = list(default)
    if not records:
        return tuple(values)
    key_fields = tuple(series["key_fields"])
    index = {_cell_key(cell, key_fields): i for i, cell in enumerate(cells)}
    for record in records:
        key = _record_key(record, key_fields)
        try:
            position = index[key]
        except KeyError as exc:
            raise LookupError(
                f"{series_id} has no cell for {dict(zip(key_fields, key, strict=True))}"
            ) from exc
        values[position] = record[_RECORD_VALUE_FIELD]
    return tuple(values)


def excel_writes_for_inputs(
    input_series: Sequence[Mapping[str, Any]],
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    """Sparse Excel writes: every scalar, plus matrix cells named by records."""
    writes: dict[str, Any] = {}
    for series in input_series:
        series_id = str(series["id"])
        cells = series["cells"]
        key_fields = tuple(series["key_fields"])
        if not key_fields:
            if len(cells) != 1:
                raise ValueError(
                    f"{series_id} is a scalar series but has {len(cells)} cells"
                )
            if series_id not in inputs:
                raise TypeError(
                    f"scenario inputs are missing scalar series {series_id!r}"
                )
            writes[normalize_key(str(cells[0]["address"]))] = inputs[series_id]
            continue
        records = inputs.get(series_id) or ()
        index = {_cell_key(cell, key_fields): cell for cell in cells}
        for record in records:
            key = _record_key(record, key_fields)
            try:
                cell = index[key]
            except KeyError as exc:
                raise LookupError(
                    f"{series_id} has no cell for {dict(zip(key_fields, key, strict=True))}"
                ) from exc
            writes[normalize_key(str(cell["address"]))] = record[_RECORD_VALUE_FIELD]
    return writes


def _resolve_annotation(function: Callable[..., object], name: str) -> object:
    annotation = function.__annotations__.get(name)
    if isinstance(annotation, str):
        return getattr(function, "__globals__", {}).get(annotation)
    return annotation


def compute_leaf_names(function: Callable[..., object]) -> tuple[str, ...]:
    """Leaf names required by ``compute``, including generated Inputs fields."""
    parameters = inspect.signature(function).parameters
    function_name = getattr(function, "__name__", type(function).__name__)
    if list(parameters) == ["inputs"]:
        annotation = _resolve_annotation(function, "inputs")
        if annotation is not None and dataclasses.is_dataclass(annotation):
            return tuple(field.name for field in dataclasses.fields(annotation))
    names: list[str] = []
    for name, parameter in parameters.items():
        if parameter.kind is inspect.Parameter.VAR_POSITIONAL:
            raise TypeError(f"{function_name} has unsupported *args")
        if parameter.kind is inspect.Parameter.VAR_KEYWORD:
            raise TypeError(f"{function_name} has unsupported **kwargs")
        names.append(name)
    return tuple(names)


def call_compute(
    pkg: object, compute: Callable[..., object], kwargs: Mapping[str, object]
) -> object:
    """Call ``compute`` with a constructed ``{Output}Inputs`` bundle."""
    annotation = compute.__annotations__.get("inputs")
    if isinstance(annotation, str):
        annotation = getattr(pkg, annotation, None) or getattr(
            compute, "__globals__", {}
        ).get(annotation)
    if annotation is None or not hasattr(annotation, "from_defaults"):
        compute_name = getattr(compute, "__name__", type(compute).__name__)
        raise TypeError(
            f"{compute_name}() expected an Inputs class with from_defaults(), "
            "not leaf keywords"
        )
    return compute(annotation.from_defaults(**kwargs))


def input_kwargs_for_compute(
    function: Callable[..., object],
    data: object,
    *,
    inputs: Mapping[str, object],
    input_series: Sequence[Mapping[str, Any]] | None = None,
    scalar_input_keys: frozenset[str] | None = None,
) -> dict[str, object]:
    """Build leaf kwargs for an inverted-tree ``compute_*`` function.

    When the signature is a single ``inputs`` parameter whose annotation is an
    Inputs dataclass, walk those fields (excel-grapher 22). Otherwise walk
    keyword-only leaf parameters. Overlay ``data.*_DEFAULT`` sequences at
    catalog index, or named-axis series by coordinate. Constant kwargs that
    already have generated defaults are omitted so ``from_defaults`` can fill
    them.
    """
    series_by_id = (
        {str(series["id"]): series for series in input_series}
        if input_series is not None
        else {}
    )
    dashboard_keys = scalar_input_keys or frozenset()
    kwargs: dict[str, object] = {}
    function_name = getattr(function, "__name__", type(function).__name__)
    parameters = inspect.signature(function).parameters
    bundled = list(parameters) == ["inputs"]
    for name in compute_leaf_names(function):
        parameter = parameters.get(name)
        series = series_by_id.get(name)
        if series is not None:
            if series["key_fields"]:
                attr = _default_attr_name(name)
                if not hasattr(data, attr):
                    module_name = getattr(data, "__name__", type(data).__name__)
                    raise TypeError(
                        f"{function_name} required parameter {name!r} needs "
                        f"{module_name}.{attr}"
                    )
                kwargs[name] = overlay_series_values(
                    series,
                    getattr(data, attr),
                    _record_sequence(inputs.get(name)),
                )
            else:
                if name not in inputs:
                    raise TypeError(
                        f"{function_name} required parameter {name!r} is a "
                        "bound input series but is missing from inputs"
                    )
                kwargs[name] = inputs[name]
            continue
        if name in dashboard_keys:
            if name not in inputs:
                raise TypeError(
                    f"{function_name} required parameter {name!r} is a "
                    "canonical dashboard input but is missing from inputs"
                )
            kwargs[name] = inputs[name]
            continue
        if (
            not bundled
            and parameter is not None
            and parameter.default is not inspect.Parameter.empty
        ):
            continue
        attr = _default_attr_name(name)
        if not hasattr(data, attr):
            if bundled:
                continue
            module_name = getattr(data, "__name__", type(data).__name__)
            raise TypeError(
                f"{function_name} required parameter {name!r} is not a "
                f"canonical dashboard input and {module_name} is missing {attr}"
            )
        kwargs[name] = getattr(data, attr)
    return kwargs
