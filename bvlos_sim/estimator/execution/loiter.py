"""Loiter dwell estimation: station-keep (hover) and circular orbit (fixed-wing)."""

import math

from bvlos_sim.estimator.core.enums import (
    FailureCode,
    FailureKind,
    LegPhase,
    SpeedSource,
    WarningCode,
)
from bvlos_sim.estimator.core.results import LegEstimate, LegTimingProfile
from bvlos_sim.estimator.execution.rules import (
    resolve_station_keep_authority,
    resolve_transit_tas,
)
from bvlos_sim.estimator.execution.runtime import EstimationContext
from bvlos_sim.estimator.execution.weather import sample_wind_interval
from bvlos_sim.schemas.mission import RouteItem


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

    wind_samples = sample_wind_interval(
        context.wind_provider,
        lat=context.state.lat,
        lon=context.state.lon,
        start_altitude_amsl_m=context.state.alt_amsl_m,
        end_altitude_amsl_m=context.state.alt_amsl_m,
        start_elapsed_time_s=context.state.elapsed_time_s,
        duration_s=loiter_time_s,
    )
    violating_sample = next(
        (
            sample
            for sample in wind_samples
            if context.wind_speed(sample.wind) > authority
        ),
        None,
    )
    if violating_sample is not None:
        violating_wind_speed = context.wind_speed(violating_sample.wind)
        context.fail(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.STATION_KEEP_INFEASIBLE_WIND,
            message="Station-keep infeasible because wind exceeds station-keep authority.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={
                "wind_speed_mps": violating_wind_speed,
                "station_keep_authority_mps": authority,
                "elapsed_time_s": violating_sample.elapsed_time_s,
            },
        )
    worst_wind_sample = max(
        wind_samples,
        key=lambda sample: context.wind_speed(sample.wind),
    )
    dwell_wind = worst_wind_sample.wind
    dwell_wind_speed = context.wind_speed(dwell_wind)

    if item.loiter_radius_m is not None:
        context.add_warning(
            WarningCode.LOITER_RADIUS_IGNORED,
            f"loiter_radius_m={item.loiter_radius_m} m is set but ignored; "
            "station-keep loiter uses max_station_keep_wind_mps as authority.",
            route_item_index=route_item_index,
            route_item_id=item.id,
        )

    context.add_warning(
        WarningCode.LOITER_ASSUMED_ZERO_GROUND_DISTANCE,
        "Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.",
        route_item_index=route_item_index,
        route_item_id=item.id,
    )
    leg_warning_codes.append(WarningCode.LOITER_ASSUMED_ZERO_GROUND_DISTANCE)

    leg = LegEstimate(
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
    leg._set_timing_profile(
        LegTimingProfile(
            distance_time_points=((0.0, 0.0), (1.0, loiter_time_s)),
            vertical_time_s=0.0,
        )
    )
    return leg


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

    if item.loiter_radius_m is not None:
        context.add_warning(
            WarningCode.LOITER_RADIUS_IGNORED,
            f"loiter_radius_m={item.loiter_radius_m} m is set but ignored; "
            "fixed-wing circular loiter uses vehicle.performance.turn_radius_m.",
            route_item_index=route_item_index,
            route_item_id=item.id,
        )

    tas_mps, speed_source = resolve_transit_tas(
        context, item, route_item_index=route_item_index
    )
    path_distance_m = tas_mps * loiter_time_s

    wind_samples = sample_wind_interval(
        context.wind_provider,
        lat=context.state.lat,
        lon=context.state.lon,
        start_altitude_amsl_m=context.state.alt_amsl_m,
        end_altitude_amsl_m=context.state.alt_amsl_m,
        start_elapsed_time_s=context.state.elapsed_time_s,
        duration_s=loiter_time_s,
    )
    worst_wind_sample = max(
        wind_samples,
        key=lambda sample: context.wind_speed(sample.wind),
    )
    loiter_wind = worst_wind_sample.wind
    loiter_wind_speed = context.wind_speed(loiter_wind)
    for sample in wind_samples:
        wind_speed_mps = context.wind_speed(sample.wind)
        failure_context = {
            "wind_speed_mps": wind_speed_mps,
            "tas_mps": tas_mps,
            "elapsed_time_s": sample.elapsed_time_s,
        }
        if wind_speed_mps >= tas_mps:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.WIND_TRIANGLE_NO_SOLUTION,
                message=(
                    "Fixed-wing circular loiter cannot sustain every orbit "
                    "track because wind equals or exceeds TAS."
                ),
                route_item_index=route_item_index,
                route_item_id=item.id,
                context=failure_context,
            )
        minimum_orbit_groundspeed_mps = tas_mps - wind_speed_mps
        if minimum_orbit_groundspeed_mps < context.resolved_options.min_groundspeed_mps:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.GROUNDSPEED_BELOW_MIN,
                message=(
                    "Fixed-wing circular loiter upwind groundspeed is below "
                    "min_groundspeed_mps."
                ),
                route_item_index=route_item_index,
                route_item_id=item.id,
                context=failure_context
                | {
                    "groundspeed_mps": minimum_orbit_groundspeed_mps,
                    "min_groundspeed_mps": context.resolved_options.min_groundspeed_mps,
                },
            )
        maximum_crab_angle_deg = math.degrees(math.asin(wind_speed_mps / tas_mps))
        if maximum_crab_angle_deg > context.max_crab_angle_deg:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.CRAB_ANGLE_LIMIT_EXCEEDED,
                message=(
                    "Fixed-wing circular loiter requires a crab angle above "
                    "max_crab_angle_deg on part of the orbit."
                ),
                route_item_index=route_item_index,
                route_item_id=item.id,
                context=failure_context
                | {
                    "crab_angle_deg": maximum_crab_angle_deg,
                    "max_crab_angle_deg": context.max_crab_angle_deg,
                },
            )

    leg = LegEstimate(
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
        wind_speed_mps=loiter_wind_speed,
        wind_cross_track_mps=loiter_wind_speed,
        speed_source=speed_source,
    )
    leg._set_timing_profile(
        LegTimingProfile(
            distance_time_points=((0.0, 0.0), (1.0, loiter_time_s)),
            vertical_time_s=0.0,
        )
    )
    return leg
