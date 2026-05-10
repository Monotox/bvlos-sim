"""Executor for RTL mission actions."""

from estimator.core.enums import LegPhase
from estimator.execution.runtime import EstimationContext, TargetPhase
from estimator.execution.transit import append_transit_leg
from schemas.mission import RouteItem


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
