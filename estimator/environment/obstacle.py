"""Obstacle providers for deterministic clearance checks."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from estimator.core.obstacle import Obstacle


class ObstacleProvider(Protocol):
    provider_id: str

    def obstacles(self) -> tuple[Obstacle, ...]:
        """Return static obstacles available to the estimator."""


@dataclass(frozen=True, slots=True)
class ListObstacleProvider:
    """In-memory obstacle provider backed by an immutable obstacle list."""

    items: tuple[Obstacle, ...]
    provider_id: str = field(init=False, default="static_list")

    def __init__(self, items: Sequence[Obstacle]) -> None:
        object.__setattr__(self, "items", tuple(items))

    def obstacles(self) -> tuple[Obstacle, ...]:
        return self.items


def obstacle_provider_id(provider: ObstacleProvider) -> str:
    return getattr(provider, "provider_id", provider.__class__.__name__)


__all__ = [
    "ListObstacleProvider",
    "ObstacleProvider",
    "obstacle_provider_id",
]
