"""Shared deterministic JSON rendering helpers."""

from __future__ import annotations

import json
import math
from typing import TypeAlias

JsonPrimitive: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonPrimitive | list["JsonValue"] | dict[str, "JsonValue"]

_FLOAT_DECIMAL_PLACES = 8


def canonical_json_value(value: JsonValue) -> JsonValue:
    """Return a JSON-compatible value with stable float precision."""
    if isinstance(value, float):
        return canonical_float(value)
    if isinstance(value, list):
        return [canonical_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: canonical_json_value(item) for key, item in value.items()}
    return value


def canonical_float(value: float) -> float:
    """Round insignificant platform-specific float noise."""
    if not math.isfinite(value):
        raise ValueError(f"Canonical JSON cannot represent non-finite float {value!r}")
    rounded = round(value, _FLOAT_DECIMAL_PLACES)
    return 0.0 if rounded == 0.0 else rounded


def format_canonical_float(value: float) -> str:
    """Format a float using canonical JSON precision."""
    return str(canonical_float(value))


def render_canonical_json(
    payload: JsonValue,
    *,
    ensure_ascii: bool = True,
) -> str:
    """Render sorted, indented JSON with stable float precision."""
    return (
        json.dumps(
            canonical_json_value(payload),
            indent=2,
            sort_keys=True,
            ensure_ascii=ensure_ascii,
            allow_nan=False,
        )
        + "\n"
    )
