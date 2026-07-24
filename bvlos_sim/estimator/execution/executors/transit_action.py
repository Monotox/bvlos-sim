"""Executor for one-leg transit-style mission actions."""

from dataclasses import dataclass

from bvlos_sim.estimator.core.enums import FailureCode, LegPhase
from bvlos_sim.estimator.execution.executors.support import (
    build_transit_target,
    require_hover_capability,
)
from bvlos_sim.estimator.execution.runtime import EstimationContext
from bvlos_sim.estimator.execution.transit import append_transit_leg
from bvlos_sim.schemas.mission import RouteItem


@dataclass(frozen=True)
class TransitActionExecutor:
    """Shared executor for one-leg route items that only estimate transit."""

    phase: LegPhase
    require_hover: bool = False

    def execute(
        self,
        context: EstimationContext,
        item: RouteItem,
        *,
        route_item_index: int,
    ) -> None:
        if self.require_hover:
            require_hover_capability(
                context,
                item,
                route_item_index=route_item_index,
                code=FailureCode.INVALID_MISSION_PROFILE,
                message=f"{item.action.value} requires hover capability.",
            )

        append_transit_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=build_transit_target(
                context,
                item,
                route_item_index=route_item_index,
                phase=self.phase,
            ),
        )
