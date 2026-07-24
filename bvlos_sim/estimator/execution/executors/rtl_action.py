"""Executor for RTL mission actions."""

from bvlos_sim.estimator.core.enums import LegPhase
from bvlos_sim.estimator.execution.runtime import EstimationContext, TargetPhase
from bvlos_sim.estimator.execution.transit import append_transit_leg
from bvlos_sim.schemas.mission import RouteItem


class RtlActionExecutor:
    """Executor for returning to planned home."""

    def execute(
        self,
        context: EstimationContext,
        item: RouteItem,
        *,
        route_item_index: int,
    ) -> None:
        append_transit_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=TargetPhase(
                target_lat=context.mission.planned_home.lat,
                target_lon=context.mission.planned_home.lon,
                target_alt_amsl_m=context.mission.planned_home.altitude_amsl_m,
                phase=LegPhase.RTL_TRANSIT,
            ),
        )
