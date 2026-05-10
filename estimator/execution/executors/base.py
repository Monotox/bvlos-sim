"""Base protocol for route-item executors."""

from typing import Protocol

from estimator.execution.runtime import EstimationContext
from schemas.mission import RouteItem


class RouteActionExecutor(Protocol):
    """Strategy interface for turning one route item into one or more legs."""

    def execute(
        self,
        context: EstimationContext,
        item: RouteItem,
        *,
        route_item_index: int,
    ) -> None: ...
