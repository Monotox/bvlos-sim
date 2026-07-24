"""Altitude-reference resolution for estimator execution."""

from bvlos_sim.estimator.core.enums import FailureCode, FailureKind
from bvlos_sim.estimator.execution.runtime import EstimationContext
from bvlos_sim.schemas.mission import AltitudeReference, RouteItem


def _resolve_amsl(context: EstimationContext, altitude_m: float) -> float:
    return altitude_m


def _resolve_relative_home(context: EstimationContext, altitude_m: float) -> float:
    return context.mission.planned_home.altitude_amsl_m + altitude_m


_ALTITUDE_RESOLVERS = {
    AltitudeReference.AMSL: _resolve_amsl,
    AltitudeReference.RELATIVE_HOME: _resolve_relative_home,
}


def _effective_terrain_position(
    context: EstimationContext, item: RouteItem
) -> tuple[float, float]:
    if item.lat is not None and item.lon is not None:
        return item.lat, item.lon
    return context.mission.planned_home.lat, context.mission.planned_home.lon


def _resolve_terrain(
    context: EstimationContext,
    altitude_m: float,
    lat: float,
    lon: float,
    *,
    route_item_index: int,
    route_item_id: str,
    action: str,
) -> float:
    if context.terrain_provider is None:
        context.fail(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN,
            message=(
                "terrain altitude reference requires a terrain provider. "
                "Set assets.terrain_file in the mission or pass terrain_provider at runtime."
            ),
            route_item_index=route_item_index,
            route_item_id=route_item_id,
            context={"action": action},
        )
    ground_elevation_m = context.terrain_provider.elevation_at(lat, lon)
    if ground_elevation_m is None:
        context.fail(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.TERRAIN_COVERAGE_MISSING,
            message=f"terrain provider has no coverage at ({lat:.6f}, {lon:.6f}).",
            route_item_index=route_item_index,
            route_item_id=route_item_id,
            context={
                "action": action,
                "lat": lat,
                "lon": lon,
                "terrain_provider_id": context.terrain_provider.provider_id,
            },
        )
    return ground_elevation_m + altitude_m


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
        lat, lon = _effective_terrain_position(context, item)
        return _resolve_terrain(
            context,
            item.altitude_m,
            lat,
            lon,
            route_item_index=route_item_index,
            route_item_id=item.id,
            action=item.action.value,
        )
    return _ALTITUDE_RESOLVERS[reference](context, item.altitude_m)
