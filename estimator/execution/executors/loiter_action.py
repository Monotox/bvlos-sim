"""Executor for loiter-time mission actions."""

from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
from estimator.core.enums import FidelityMode
from estimator.core.enums import LegPhase
from estimator.execution.executors.support import build_transit_target
from estimator.execution.executors.support import require_hover_capability
from estimator.execution.loiter import estimate_fw_circular_loiter_dwell_leg
from estimator.execution.loiter import estimate_loiter_dwell_leg
from estimator.execution.runtime import EstimationContext
from estimator.execution.transit import append_transit_leg
from schemas.mission import RouteItem


class LoiterTimeActionExecutor:
    """Executor for transit plus loiter dwell.

    v1 / hover-capable: station-keep dwell (requires hover capability).
    v2 fixed-wing: circular orbit at turn_radius_m (requires turn_radius_m).
    """

    def execute(
        self,
        context: EstimationContext,
        item: RouteItem,
        *,
        route_item_index: int,
    ) -> None:
        loiter_time_s = item.loiter_time_s
        if loiter_time_s is not None and loiter_time_s < 0:
            context.fail(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_MISSION_PROFILE,
                message="loiter_time_s must be non-negative.",
                route_item_index=route_item_index,
                route_item_id=item.id,
                context={"loiter_time_s": loiter_time_s},
            )

        use_fw_circular_loiter = (
            context.resolved_options.fidelity == FidelityMode.V2
            and context.capabilities.forward_flight
            and not context.capabilities.hover
        )

        if use_fw_circular_loiter:
            if context.vehicle.performance.turn_radius_m is None:
                context.fail(
                    kind=FailureKind.INVALID_INPUT,
                    code=FailureCode.MISSING_REQUIRED_SPEED_PROFILE,
                    message=(
                        "turn_radius_m is required for fixed-wing circular loiter "
                        "in fidelity v2."
                    ),
                    route_item_index=route_item_index,
                    route_item_id=item.id,
                    context={"action": item.action.value},
                )
        else:
            require_hover_capability(
                context,
                item,
                route_item_index=route_item_index,
                code=FailureCode.UNSUPPORTED_LOITER_FOR_VEHICLE_CLASS,
                message="loiter_time station-keep is unsupported without hover capability.",
            )

        append_transit_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=build_transit_target(
                context,
                item,
                route_item_index=route_item_index,
                phase=LegPhase.LOITER_TRANSIT,
            ),
        )

        if use_fw_circular_loiter:
            context.append_leg(
                estimate_fw_circular_loiter_dwell_leg(
                    context,
                    item,
                    route_item_index=route_item_index,
                )
            )
        else:
            context.append_leg(
                estimate_loiter_dwell_leg(
                    context,
                    item,
                    route_item_index=route_item_index,
                )
            )
