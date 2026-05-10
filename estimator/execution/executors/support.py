"""Shared support helpers for route-item executors."""

from estimator.core.enums import FailureCode, FailureKind, LegPhase
from estimator.execution.altitude import resolve_target_altitude_amsl
from estimator.execution.runtime import EstimationContext, TargetPhase
from schemas.mission import RouteItem


def require_hover_capability(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    code: FailureCode,
    message: str,
    kind: FailureKind = FailureKind.UNSUPPORTED,
) -> None:
    if context.capabilities.hover:
        return
    context.fail(
        kind=kind,
        code=code,
        message=message,
        route_item_index=route_item_index,
        route_item_id=item.id,
        context={"action": item.action.value},
    )


def resolve_item_target_altitude(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> float:
    if item.altitude_m is None:
        if item.altitude_reference is not None:
            context.fail(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_MISSION_PROFILE,
                message="altitude_reference requires altitude_m.",
                route_item_index=route_item_index,
                route_item_id=item.id,
                context={"action": item.action.value},
            )
        return context.state.alt_amsl_m
    return resolve_target_altitude_amsl(
        context,
        item,
        route_item_index=route_item_index,
    )


def resolve_item_target_coordinates(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> tuple[float, float]:
    if item.lat is None and item.lon is None:
        return context.state.lat, context.state.lon
    if item.lat is None or item.lon is None:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message="lat and lon must either both be provided or both be omitted.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )
    return item.lat, item.lon


def build_transit_target(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    phase: LegPhase,
) -> TargetPhase:
    target_lat, target_lon = resolve_item_target_coordinates(
        context,
        item,
        route_item_index=route_item_index,
    )
    return TargetPhase(
        target_lat=target_lat,
        target_lon=target_lon,
        target_alt_amsl_m=resolve_item_target_altitude(
            context,
            item,
            route_item_index=route_item_index,
        ),
        phase=phase,
    )
