"""Shared core spatial validation helpers."""

from collections.abc import Sequence
from typing import Protocol


class RingCoordinate(Protocol):
    """Coordinate shape required for closed-ring validation."""

    lat: float
    lon: float


def validate_closed_ring(ring: Sequence[RingCoordinate], field_name: str) -> None:
    if len(ring) < 4:
        raise ValueError(f"{field_name} must contain at least four coordinates")

    first = ring[0]
    last = ring[-1]
    if first.lat != last.lat or first.lon != last.lon:
        raise ValueError(f"{field_name} must be closed")


__all__ = [
    "RingCoordinate",
    "validate_closed_ring",
]
