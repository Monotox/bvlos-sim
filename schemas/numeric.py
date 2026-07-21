"""Strict finite numeric types for safety-relevant input contracts."""

import math
from typing import Annotated

from pydantic import BeforeValidator


def _finite_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("must be a numeric value, not a boolean or string")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("must be finite")
    return number


FiniteFloat = Annotated[float, BeforeValidator(_finite_float)]

__all__ = ["FiniteFloat"]
