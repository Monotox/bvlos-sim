"""Loiter dwell estimation: station-keep (hover) and circular orbit (fixed-wing)."""

from estimator.core.enums import (
    FailureCode,
    FailureKind,
    LegPhase,
    SpeedSource,
    WarningCode,
)
from estimator.core.results import LegEstimate
from estimator.execution.rules import (
    resolve_station_keep_authority,
    resolve_transit_tas,
)
from estimator.execution.runtime import EstimationContext
from schemas.mission import RouteItem


def estimate_loiter_dwell_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> LegEstimate:
    if not context.capabilities.hover:
        context.fail(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.UNSUPPORTED_LOITER_FOR_VEHICLE_CLASS,
            message="loiter_time station-keep is unsupported without hover capability.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"vehicle_class": context.vehicle.vehicle_class.value},
        )

    loiter_time_s = item.loiter_time_s
    if loiter_time_s is None:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message="loiter_time requires loiter_time_s.",
            route_item_index=route_item_index,
            route_item_id=item.id,
        )

    authority, leg_warning_codes = resolve_station_keep_authority(
        context,
        route_item_index=route_item_index,
        route_item_id=item.id,
    )
    if authority is None:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.MISSING_REQUIRED_SPEED_PROFILE,
            message=(
                "Station-keep authority missing: provide "
                "max_station_keep_wind_mps or hover_speed_mps."
            ),
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )
    if authority <= 0:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_SPEED_PROFILE,
            message="Station-keep authority must be greater than zero.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"station_keep_authority_mps": authority},
        )

    dwell_wind = context.wind_provider.wind_at(
        lat=context.state.lat,
        lon=context.state.lon,
        altitude_amsl_m=context.state.alt_amsl_m,
        elapsed_time_s=context.state.elapsed_time_s,
    )
    dwell_wind_speed = context.wind_speed(dwell_wind)
    if dwell_wind_speed > authority:
        context.fail(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.STATION_KEEP_INFEASIBLE_WIND,
            message="Station-keep infeasible because wind exceeds station-keep authority.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={
                "wind_speed_mps": dwell_wind_speed,
                "station_keep_authority_mps": authority,
            },
        )

    context.add_warning(
        WarningCode.LOITER_ASSUMED_ZERO_GROUND_DISTANCE,
        "Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.",
        route_item_index=route_item_index,
        route_item_id=item.id,
    )
    leg_warning_codes.append(WarningCode.LOITER_ASSUMED_ZERO_GROUND_DISTANCE)

    return LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=LegPhase.LOITER_DWELL,
        start_lat=context.state.lat,
        start_lon=context.state.lon,
        start_alt_amsl_m=context.state.alt_amsl_m,
        end_lat=context.state.lat,
        end_lon=context.state.lon,
        end_alt_amsl_m=context.state.alt_amsl_m,
        horizontal_distance_m=0.0,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=0.0,
        time_s=loiter_time_s,
        wind_east_mps=dwell_wind.wind_east_mps,
        wind_north_mps=dwell_wind.wind_north_mps,
        wind_speed_mps=dwell_wind_speed,
        speed_source=SpeedSource.STATION_KEEP_AUTHORITY,
        warnings=leg_warning_codes,
    )


def estimate_fw_circular_loiter_dwell_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> LegEstimate:
    """Model a fixed-wing loiter as a constant-radius circular orbit.

    The path distance is TAS × loiter_time_s (airspeed distance along the orbit
    path). Wind averages to zero over full orbits at the model level.
    Orbit radius equals vehicle.performance.turn_radius_m.

    Pre-condition: turn_radius_m is not None (enforced by executor before calling).
    """
    loiter_time_s = item.loiter_time_s  # guaranteed by schema and executor

    tas_mps, speed_source = resolve_transit_tas(
        context, item, route_item_index=route_item_index
    )
    path_distance_m = tas_mps * loiter_time_s

    loiter_wind = context.wind_provider.wind_at(
        lat=context.state.lat,
        lon=context.state.lon,
        altitude_amsl_m=context.state.alt_amsl_m,
        elapsed_time_s=context.state.elapsed_time_s,
    )

    return LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=LegPhase.LOITER_DWELL,
        start_lat=context.state.lat,
        start_lon=context.state.lon,
        start_alt_amsl_m=context.state.alt_amsl_m,
        end_lat=context.state.lat,
        end_lon=context.state.lon,
        end_alt_amsl_m=context.state.alt_amsl_m,
        horizontal_distance_m=0.0,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=path_distance_m,
        time_s=loiter_time_s,
        tas_mps=tas_mps,
        wind_east_mps=loiter_wind.wind_east_mps,
        wind_north_mps=loiter_wind.wind_north_mps,
        wind_speed_mps=context.wind_speed(loiter_wind),
        speed_source=speed_source,
    )
