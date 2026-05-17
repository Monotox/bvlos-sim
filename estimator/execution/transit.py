"""Transit geometry and forward-flight leg estimation.

Fidelity v2 inserts a TURN_ARC leg at each waypoint heading change and
subtracts the tangent-point offset (turn_radius_m * tan(|Δθ|/2)) from the
path_distance_m of both adjacent transit legs so that total path distance
reflects the true Dubins-path length.
"""

import math
from dataclasses import dataclass

from estimator.core.constants import (
    CRAB_ANGLE_WARNING_MARGIN,
    EPS_DISTANCE_M,
    GROUNDSPEED_WARNING_MARGIN,
    MIN_TURN_ANGLE_DEG,
)
from estimator.core.enums import (
    FailureCode,
    FailureKind,
    FidelityMode,
    LegPhase,
    WarningCode,
)
from estimator.core.results import EstimatorContextValue, LegEstimate, WindVector
from estimator.execution.rules import resolve_transit_tas
from estimator.execution.runtime import EstimationContext, TargetPhase
from estimator.execution.vertical import VerticalProfile, compute_vertical_time
from estimator.math.turn_arc import compute_turn_arc_geometry
from estimator.math.wind_triangle import normalize_deg, solve_wind_triangle
from schemas.mission import RouteItem


@dataclass(frozen=True)
class TransitGeometry:
    track_deg: float
    horizontal_distance_m: float


@dataclass(frozen=True)
class TransitConstraintCheck:
    violated: bool
    code: FailureCode
    message: str
    context: dict[str, EstimatorContextValue]


@dataclass(frozen=True)
class TransitWarningCheck:
    triggered: bool
    code: WarningCode


def compute_transit_geometry(
    context: EstimationContext,
    *,
    start_lat: float,
    start_lon: float,
    target: TargetPhase,
) -> TransitGeometry:
    azimuth_deg, _, horizontal_distance_m = context.geod.inv(
        start_lon,
        start_lat,
        target.target_lon,
        target.target_lat,
    )
    if horizontal_distance_m <= EPS_DISTANCE_M:
        horizontal_distance_m = 0.0

    return TransitGeometry(
        track_deg=normalize_deg(azimuth_deg),
        horizontal_distance_m=horizontal_distance_m,
    )


def build_vertical_only_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
    vertical: VerticalProfile,
    start_lat: float,
    start_lon: float,
    start_alt: float,
) -> LegEstimate:
    return LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=target.phase,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt_amsl_m=start_alt,
        end_lat=target.target_lat,
        end_lon=target.target_lon,
        end_alt_amsl_m=target.target_alt_amsl_m,
        horizontal_distance_m=0.0,
        vertical_delta_m=vertical.delta_m,
        vertical_distance_m=vertical.distance_m,
        path_distance_m=vertical.distance_m,
        time_s=vertical.time_s,
    )


def _wind_at_fraction(
    context: EstimationContext,
    *,
    start_lon: float,
    start_lat: float,
    track_deg: float,
    horizontal_distance_m: float,
    altitude_m: float,
    elapsed_s: float,
    fraction: float,
) -> WindVector:
    mid_lon, mid_lat, _ = context.geod.fwd(
        start_lon, start_lat, track_deg, horizontal_distance_m * fraction
    )
    return context.wind_provider.wind_at(
        lat=mid_lat, lon=mid_lon, altitude_amsl_m=altitude_m, elapsed_time_s=elapsed_s
    )


def _sub_segment_horizontal_time_s(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    geometry: TransitGeometry,
    start_lat: float,
    start_lon: float,
    start_alt: float,
    end_alt: float,
    tas_mps: float,
    elapsed_s: float,
    max_segment_length_m: float,
    vertical_time_s: float,
) -> float:
    n = max(1, math.ceil(geometry.horizontal_distance_m / max_segment_length_m))
    seg_len = geometry.horizontal_distance_m / n
    total_s = 0.0
    for i in range(n):
        mid_frac = (i + 0.5) / n
        # Use time elapsed so far to interpolate altitude. This decouples
        # altitude from horizontal position: on climb-dominated legs the
        # aircraft hasn't gained as much altitude at each horizontal fraction
        # as a linear spatial interpolation would imply.
        # Altitude at segment start, not midpoint — decouples altitude from
        # horizontal position but means segment i=0 always samples at start_alt.
        alt_frac = min(1.0, total_s / vertical_time_s) if vertical_time_s > 0.0 else 1.0
        mid_alt = start_alt + (end_alt - start_alt) * alt_frac
        wind = _wind_at_fraction(
            context,
            start_lon=start_lon,
            start_lat=start_lat,
            track_deg=geometry.track_deg,
            horizontal_distance_m=geometry.horizontal_distance_m,
            altitude_m=mid_alt,
            elapsed_s=elapsed_s + total_s,
            fraction=mid_frac,
        )
        solution = solve_wind_triangle(
            track_deg=geometry.track_deg,
            tas_mps=tas_mps,
            wind_east_mps=wind.wind_east_mps,
            wind_north_mps=wind.wind_north_mps,
        )
        if solution is None:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.WIND_TRIANGLE_NO_SOLUTION,
                message=f"No wind-triangle solution in sub-segment {i + 1}/{n}.",
                route_item_index=route_item_index,
                route_item_id=item.id,
                context={
                    "action": item.action.value,
                    "segment_index": i,
                    "n_segments": n,
                    "wind_east_mps": wind.wind_east_mps,
                    "wind_north_mps": wind.wind_north_mps,
                    "tas_mps": tas_mps,
                },
            )
        if solution.groundspeed_mps <= 0:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.GROUNDSPEED_NON_POSITIVE,
                message=f"Non-positive groundspeed in sub-segment {i + 1}/{n}.",
                route_item_index=route_item_index,
                route_item_id=item.id,
                context={
                    "action": item.action.value,
                    "segment_index": i,
                    "n_segments": n,
                    "groundspeed_mps": solution.groundspeed_mps,
                    "wind_east_mps": wind.wind_east_mps,
                    "wind_north_mps": wind.wind_north_mps,
                    "tas_mps": tas_mps,
                },
            )
        total_s += seg_len / solution.groundspeed_mps
    return total_s


def build_forward_transit_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
    geometry: TransitGeometry,
    vertical: VerticalProfile,
    start_lat: float,
    start_lon: float,
    start_alt: float,
    tangent_offset_m: float = 0.0,
) -> LegEstimate:
    if not context.capabilities.forward_flight:
        context.fail(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.INVALID_MISSION_PROFILE,
            message="forward-flight transit requires forward_flight capability.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )

    tas_mps, speed_source = resolve_transit_tas(
        context,
        item,
        route_item_index=route_item_index,
    )
    wind = context.wind_provider.wind_at(
        lat=start_lat,
        lon=start_lon,
        altitude_amsl_m=start_alt,
        elapsed_time_s=context.state.elapsed_time_s,
    )

    solution = solve_wind_triangle(
        track_deg=geometry.track_deg,
        tas_mps=tas_mps,
        wind_east_mps=wind.wind_east_mps,
        wind_north_mps=wind.wind_north_mps,
    )
    if solution is None:
        context.fail(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.WIND_TRIANGLE_NO_SOLUTION,
            message="No wind-triangle solution exists for required crosswind correction.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={
                "action": item.action.value,
                "track_azimuth_deg": geometry.track_deg,
                "wind_east_mps": wind.wind_east_mps,
                "wind_north_mps": wind.wind_north_mps,
                "tas_mps": tas_mps,
            },
        )

    base_context = {
        "action": item.action.value,
        "track_azimuth_deg": geometry.track_deg,
        "wind_east_mps": wind.wind_east_mps,
        "wind_north_mps": wind.wind_north_mps,
        "tas_mps": tas_mps,
    }
    checks = (
        TransitConstraintCheck(
            violated=abs(solution.crab_angle_deg) > context.max_crab_angle_deg,
            code=FailureCode.CRAB_ANGLE_LIMIT_EXCEEDED,
            message="Required crab angle exceeds max_crab_angle_deg.",
            context=base_context
            | {
                "crab_angle_deg": solution.crab_angle_deg,
                "max_crab_angle_deg": context.max_crab_angle_deg,
                "groundspeed_mps": solution.groundspeed_mps,
            },
        ),
        TransitConstraintCheck(
            violated=solution.groundspeed_mps <= 0,
            code=FailureCode.GROUNDSPEED_NON_POSITIVE,
            message="Solved groundspeed is non-positive.",
            context=base_context | {"groundspeed_mps": solution.groundspeed_mps},
        ),
        TransitConstraintCheck(
            violated=solution.groundspeed_mps
            < context.resolved_options.min_groundspeed_mps,
            code=FailureCode.GROUNDSPEED_BELOW_MIN,
            message="Solved groundspeed is below min_groundspeed_mps.",
            context=base_context
            | {
                "groundspeed_mps": solution.groundspeed_mps,
                "min_groundspeed_mps": context.resolved_options.min_groundspeed_mps,
            },
        ),
    )
    for check in checks:
        if check.violated:
            context.fail(
                kind=FailureKind.INFEASIBLE,
                code=check.code,
                message=check.message,
                route_item_index=route_item_index,
                route_item_id=item.id,
                context=check.context,
            )

    max_seg = context.resolved_options.max_segment_length_m
    if max_seg is not None and geometry.horizontal_distance_m > max_seg:
        horizontal_time_s = _sub_segment_horizontal_time_s(
            context,
            item,
            route_item_index=route_item_index,
            geometry=geometry,
            start_lat=start_lat,
            start_lon=start_lon,
            start_alt=start_alt,
            end_alt=target.target_alt_amsl_m,
            tas_mps=tas_mps,
            elapsed_s=context.state.elapsed_time_s,
            max_segment_length_m=max_seg,
            vertical_time_s=vertical.time_s,
        )
    else:
        horizontal_time_s = geometry.horizontal_distance_m / solution.groundspeed_mps
    leg_time_s = max(horizontal_time_s, vertical.time_s)

    warning_checks = (
        TransitWarningCheck(
            triggered=(
                context.resolved_options.min_groundspeed_mps > 0
                and solution.groundspeed_mps
                < (
                    GROUNDSPEED_WARNING_MARGIN
                    * context.resolved_options.min_groundspeed_mps
                )
            ),
            code=WarningCode.LOW_GROUNDSPEED_MARGIN,
        ),
        TransitWarningCheck(
            triggered=abs(solution.crab_angle_deg)
            > (CRAB_ANGLE_WARNING_MARGIN * context.max_crab_angle_deg),
            code=WarningCode.HIGH_CRAB_MARGIN,
        ),
    )
    leg_warnings = [check.code for check in warning_checks if check.triggered]

    return LegEstimate(
        leg_index=context.current_leg_index,
        route_item_index=route_item_index,
        route_item_id=item.id,
        action=item.action.value,
        phase=target.phase,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt_amsl_m=start_alt,
        end_lat=target.target_lat,
        end_lon=target.target_lon,
        end_alt_amsl_m=target.target_alt_amsl_m,
        horizontal_distance_m=geometry.horizontal_distance_m,
        vertical_delta_m=vertical.delta_m,
        vertical_distance_m=vertical.distance_m,
        path_distance_m=max(0.0, geometry.horizontal_distance_m - tangent_offset_m),
        time_s=leg_time_s,
        tas_mps=tas_mps,
        groundspeed_mps=solution.groundspeed_mps,
        ground_track_deg=geometry.track_deg,
        required_heading_deg=solution.required_heading_deg,
        crab_angle_deg=solution.crab_angle_deg,
        wind_east_mps=wind.wind_east_mps,
        wind_north_mps=wind.wind_north_mps,
        wind_speed_mps=context.wind_speed(wind),
        wind_along_track_mps=solution.wind_along_track_mps,
        wind_cross_track_mps=solution.wind_cross_track_mps,
        speed_source=speed_source,
        warnings=leg_warnings,
    )


def _build_turn_arc_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    outgoing_track_deg: float,
) -> LegEstimate | None:
    """Return a TURN_ARC leg if the heading change is above the negligible threshold.

    Pre-conditions (enforced by caller):
    - context.state.last_track_deg is not None
    - context.vehicle.performance.turn_radius_m is not None
    """
    incoming_track_deg = context.state.last_track_deg
    turn_radius_m = context.vehicle.performance.turn_radius_m
    if incoming_track_deg is None or turn_radius_m is None:
        return None

    arc = compute_turn_arc_geometry(
        incoming_track_deg=incoming_track_deg,
        outgoing_track_deg=outgoing_track_deg,
        radius_m=turn_radius_m,
    )
    if arc.turn_angle_deg < MIN_TURN_ANGLE_DEG:
        return None

    tas_mps, _ = resolve_transit_tas(context, item, route_item_index=route_item_index)
    arc_time_s = arc.arc_length_m / tas_mps

    arc_wind = context.wind_provider.wind_at(
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
        phase=LegPhase.TURN_ARC,
        start_lat=context.state.lat,
        start_lon=context.state.lon,
        start_alt_amsl_m=context.state.alt_amsl_m,
        end_lat=context.state.lat,
        end_lon=context.state.lon,
        end_alt_amsl_m=context.state.alt_amsl_m,
        horizontal_distance_m=0.0,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=arc.arc_length_m,
        time_s=arc_time_s,
        tas_mps=tas_mps,
        ground_track_deg=outgoing_track_deg,
        wind_east_mps=arc_wind.wind_east_mps,
        wind_north_mps=arc_wind.wind_north_mps,
        wind_speed_mps=context.wind_speed(arc_wind),
    )


def append_transit_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
) -> None:
    """Build and append a transit leg, prepending a TURN_ARC leg in v2 fidelity.

    In fidelity v2, a turn arc is injected whenever:
    - the vehicle has a known incoming track from the previous leg,
    - the vehicle has forward-flight capability with a defined turn radius, and
    - the new transit leg has a non-trivial horizontal distance.

    When a TURN_ARC is injected, the tangent-point offset
    (turn_radius_m * tan(|Δθ|/2)) is subtracted from the path_distance_m of
    both the preceding transit leg and the new transit leg so that total path
    distance reflects the true Dubins-path length.
    """
    tangent_offset_m = 0.0

    if (
        context.resolved_options.fidelity == FidelityMode.V2
        and context.state.last_track_deg is not None
        and context.capabilities.forward_flight
        and context.vehicle.performance.turn_radius_m is not None
    ):
        geometry = compute_transit_geometry(
            context,
            start_lat=context.state.lat,
            start_lon=context.state.lon,
            target=target,
        )
        if geometry.horizontal_distance_m > EPS_DISTANCE_M:
            turn_arc = _build_turn_arc_leg(
                context,
                item,
                route_item_index=route_item_index,
                outgoing_track_deg=geometry.track_deg,
            )
            if turn_arc is not None:
                turn_radius_m = context.vehicle.performance.turn_radius_m
                turn_angle_rad = turn_arc.path_distance_m / turn_radius_m
                tangent_offset_m = turn_radius_m * math.tan(turn_angle_rad / 2.0)
                context.append_leg(turn_arc)
                # Retroactively trim the transit leg that leads into this arc.
                if len(context.route_legs) >= 2:
                    prev = context.route_legs[-2]
                    context.route_legs[-2] = prev.model_copy(
                        update={
                            "path_distance_m": max(
                                0.0, prev.path_distance_m - tangent_offset_m
                            )
                        }
                    )

    context.append_leg(
        estimate_transit_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=target,
            tangent_offset_m=tangent_offset_m,
        )
    )


def estimate_transit_leg(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    target: TargetPhase,
    tangent_offset_m: float = 0.0,
) -> LegEstimate:
    start_lat = context.state.lat
    start_lon = context.state.lon
    start_alt = context.state.alt_amsl_m

    geometry = compute_transit_geometry(
        context,
        start_lat=start_lat,
        start_lon=start_lon,
        target=target,
    )
    vertical = compute_vertical_time(
        context,
        item,
        route_item_index=route_item_index,
        start_alt_amsl_m=start_alt,
        end_alt_amsl_m=target.target_alt_amsl_m,
    )

    if geometry.horizontal_distance_m == 0.0:
        return build_vertical_only_leg(
            context,
            item,
            route_item_index=route_item_index,
            target=target,
            vertical=vertical,
            start_lat=start_lat,
            start_lon=start_lon,
            start_alt=start_alt,
        )

    return build_forward_transit_leg(
        context,
        item,
        route_item_index=route_item_index,
        target=target,
        geometry=geometry,
        vertical=vertical,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt=start_alt,
        tangent_offset_m=tangent_offset_m,
    )
