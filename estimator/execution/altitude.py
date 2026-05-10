"""Altitude-reference resolution for estimator execution."""

from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
from estimator.execution.runtime import EstimationContext
from schemas.mission import AltitudeReference
from schemas.mission import RouteItem


def _resolve_amsl(context: EstimationContext, altitude_m: float) -> float:
    return altitude_m


def _resolve_relative_home(context: EstimationContext, altitude_m: float) -> float:
    return context.mission.planned_home.altitude_amsl_m + altitude_m


_ALTITUDE_RESOLVERS = {
    AltitudeReference.AMSL: _resolve_amsl,
    AltitudeReference.RELATIVE_HOME: _resolve_relative_home,
}


def route_altitude_reference(
    context: EstimationContext,
    item: RouteItem,
) -> AltitudeReference:
    return item.altitude_reference or context.mission.defaults.altitude_reference


def resolve_target_altitude_amsl(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> float:
    if item.altitude_m is None:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message="altitude_m is required for this route item.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )

    reference = route_altitude_reference(context, item)
    if reference == AltitudeReference.TERRAIN:
        context.fail(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN,
            message="terrain altitude reference is unsupported in estimator v1.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )

    return _ALTITUDE_RESOLVERS[reference](context, item.altitude_m)
