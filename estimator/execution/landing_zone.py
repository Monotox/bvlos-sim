"""Deterministic static landing-zone reachability evaluation."""

import bisect
from dataclasses import dataclass
import math

from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union
from shapely.validation import explain_validity

from estimator.core.enums import FailureCode, FailureKind
from estimator.core.landing_zone import LandingZone
from estimator.core.results import (
    EnergyEstimate,
    EstimatorContextValue,
    EstimatorFailure,
    LandingZoneEstimate,
    LandingZoneStateReachability,
    LegEstimate,
)
from estimator.execution.energy import EmergencyPathEstimate, estimate_emergency_path
from estimator.execution.runtime import EstimationContext
from estimator.execution.spatial import polygon_set_to_geometry_list
from estimator.execution.spatial_sampling import (
    SpatialSample,
    SpatialSamplingError,
    route_leg_samples,
)
from estimator.math.dubins import geodesic_dubins_path_to_point_m

_MIN_BOUNDARY_SAMPLES = 24
_MAX_BOUNDARY_SAMPLES = 360
_BOUNDARY_SAMPLES_PER_DEGREE = 2_000.0


@dataclass(frozen=True)
class CompiledLandingZone:
    zone: LandingZone
    geometry: BaseGeometry


@dataclass(frozen=True)
class LandingZoneEvaluation:
    landing_zone: LandingZoneEstimate | None
    failure: EstimatorFailure | None


@dataclass(frozen=True)
class ZoneDistance:
    zone_id: str
    distance_m: float


@dataclass(frozen=True)
class RouteReachabilityState:
    state_index: int
    leg: LegEstimate
    lat: float
    lon: float
    altitude_amsl_m: float
    heading_deg: float | None
    elapsed_time_s: float
    energy_used_wh: float
    coverage_half_gap_m: float


@dataclass(frozen=True)
class ZoneTarget:
    zone_id: str
    lat: float
    lon: float
    altitude_amsl_m: float
    distance_m: float


@dataclass(frozen=True)
class ReachableZonePath:
    target: ZoneTarget
    emergency: EmergencyPathEstimate


def evaluate_landing_zone_reachability(
    context: EstimationContext,
    energy: EnergyEstimate | None,
    *,
    unavailable_zone_ids_by_state: list[frozenset[str]] | None = None,
) -> LandingZoneEvaluation:
    """Evaluate landing-zone reachability after energy feasibility.

    When ``unavailable_zone_ids_by_state`` is provided (one frozenset per
    state index), zones in each set are excluded from consideration at that
    state. All zones are available when the argument is None.
    """

    if context.landing_zones is None:
        return LandingZoneEvaluation(landing_zone=None, failure=None)
    if energy is None:
        return LandingZoneEvaluation(
            landing_zone=None,
            failure=_mission_failure(
                code=FailureCode.MISSING_ENERGY_MODEL,
                message="Energy estimate is required for landing-zone reachability.",
                context={},
            ),
        )

    compiled_zones: list[CompiledLandingZone] = []
    for zone in context.landing_zones:
        compiled, failure = _compile_zone(zone)
        if failure is not None:
            return LandingZoneEvaluation(landing_zone=None, failure=failure)
        compiled_zones.append(compiled)

    tas_mps, tas_failure = _resolve_divert_tas(context)
    if tas_failure is not None:
        return LandingZoneEvaluation(landing_zone=None, failure=tas_failure)

    max_distance_m = context.mission.constraints.min_distance_to_landing_zone_m
    has_availability_filter = unavailable_zone_ids_by_state is not None

    try:
        route_states = _route_reachability_states(context, energy)
    except SpatialSamplingError as exc:
        return LandingZoneEvaluation(
            landing_zone=None,
            failure=EstimatorFailure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_GEOMETRY,
                message=str(exc),
                leg_index=exc.leg.leg_index,
                route_item_index=exc.leg.route_item_index,
                route_item_id=exc.leg.route_item_id,
            ),
        )

    all_unavailable: set[str] = set()
    states: list[LandingZoneStateReachability] = []
    path_failures: list[EstimatorFailure] = []
    for route_state in route_states:
        unavailable_at_state: frozenset[str] = (
            unavailable_zone_ids_by_state[route_state.leg.leg_index]
            if has_availability_filter
            and route_state.leg.leg_index < len(unavailable_zone_ids_by_state)
            else frozenset()
        )
        all_unavailable.update(unavailable_at_state)
        available_zones = [
            z for z in compiled_zones if z.zone.id not in unavailable_at_state
        ]
        state, path_failure = _evaluate_state(
            context=context,
            energy=energy,
            available_zones=available_zones,
            all_zone_count=len(compiled_zones),
            route_state=route_state,
            tas_mps=tas_mps,
            max_distance_m=max_distance_m,
            has_availability_filter=has_availability_filter,
        )
        states.append(state)
        if path_failure is not None:
            path_failures.append(path_failure)

    landing_zone = LandingZoneEstimate(
        is_feasible=all(state.is_reachable and state.reserve_ok for state in states),
        checked_zone_count=len(compiled_zones),
        checked_state_count=len(states),
        max_allowed_distance_m=max_distance_m,
        reserve_threshold_percent=energy.reserve_threshold_percent,
        reserve_threshold_wh=energy.reserve_threshold_wh,
        unavailable_zone_ids=sorted(all_unavailable),
        states=states,
    )
    failed_state = next((state for state in states if state.code is not None), None)
    return LandingZoneEvaluation(
        landing_zone=landing_zone,
        failure=(
            path_failures[0]
            if path_failures
            else _failure_from_state(failed_state)
            if failed_state is not None
            else None
        ),
    )


def _compile_zone(
    zone: LandingZone,
) -> tuple[CompiledLandingZone, EstimatorFailure | None]:
    geometries: list[BaseGeometry] = [
        Point(point.lon, point.lat) for point in zone.geometry.points
    ]
    geometries.extend(polygon_set_to_geometry_list(zone.geometry.polygons))
    geometry = unary_union(geometries)

    if geometry.is_empty or not geometry.is_valid:
        return (
            CompiledLandingZone(zone=zone, geometry=geometry),
            _zone_geometry_failure(
                zone=zone,
                reason=explain_validity(geometry),
            ),
        )

    return CompiledLandingZone(zone=zone, geometry=geometry), None


def _resolve_divert_tas(
    context: EstimationContext,
) -> tuple[float, EstimatorFailure | None]:
    tas_mps = (
        context.mission.defaults.cruise_speed_mps
        if context.mission.defaults.cruise_speed_mps is not None
        else context.vehicle.performance.cruise_speed_mps
    )
    if tas_mps is None:
        return (
            0.0,
            _mission_failure(
                code=FailureCode.MISSING_REQUIRED_SPEED_PROFILE,
                message="A TAS source is required for landing-zone divert estimation.",
                context={},
            ),
        )
    if tas_mps <= 0:
        return (
            tas_mps,
            _mission_failure(
                code=FailureCode.INVALID_SPEED_PROFILE,
                message="Landing-zone divert tas_mps must be greater than zero.",
                context={"tas_mps": tas_mps},
            ),
        )
    return tas_mps, None


def _leg_elapsed_at_fraction(leg: LegEstimate, fraction: float) -> float:
    profile = leg.timing_profile
    if profile is None:
        if not math.isclose(leg.start_alt_amsl_m, leg.end_alt_amsl_m):
            raise SpatialSamplingError(
                "altitude-changing leg has no transit timing profile",
                leg=leg,
            )
        return leg.time_s * fraction

    points = profile.distance_time_points
    fractions = tuple(point[0] for point in points)
    upper_index = bisect.bisect_right(fractions, fraction)
    if upper_index <= 0:
        return points[0][1]
    if upper_index >= len(points):
        return points[-1][1]
    lower_fraction, lower_time_s = points[upper_index - 1]
    upper_fraction, upper_time_s = points[upper_index]
    if math.isclose(lower_fraction, upper_fraction):
        return min(lower_time_s, upper_time_s)
    local_fraction = (fraction - lower_fraction) / (upper_fraction - lower_fraction)
    return lower_time_s + local_fraction * (upper_time_s - lower_time_s)


def _sample_heading_deg(
    context: EstimationContext,
    samples: list[SpatialSample],
    *,
    index: int,
) -> float | None:
    sample = samples[index]
    for other_index in (index + 1, index - 1):
        if not 0 <= other_index < len(samples):
            continue
        other = samples[other_index]
        if other_index > index:
            start, end = sample, other
        else:
            start, end = other, sample
        track_deg, _, distance_m = context.geod.inv(
            start.lon,
            start.lat,
            end.lon,
            end.lat,
        )
        if abs(float(distance_m)) > 0.01:
            return float(track_deg)
    return sample.leg.ground_track_deg


def _sample_half_gap_m(
    context: EstimationContext,
    samples: list[SpatialSample],
    *,
    index: int,
) -> float:
    sample = samples[index]
    gaps: list[float] = []
    for other_index in (index - 1, index + 1):
        if not 0 <= other_index < len(samples):
            continue
        other = samples[other_index]
        _, _, distance_m = context.geod.inv(
            sample.lon,
            sample.lat,
            other.lon,
            other.lat,
        )
        gaps.append(abs(float(distance_m)))
    return max(gaps, default=0.0) * 0.5


def _route_reachability_states(
    context: EstimationContext,
    energy: EnergyEstimate,
) -> list[RouteReachabilityState]:
    samples_by_leg = route_leg_samples(
        context.route_legs,
        geod=context.geod,
        max_segment_length_m=context.resolved_options.max_segment_length_m,
    )
    energy_by_leg = {leg.leg_index: leg for leg in energy.legs}
    states: list[RouteReachabilityState] = []
    elapsed_before_leg_s = 0.0
    energy_before_leg_wh = 0.0
    for leg, original_samples in zip(
        context.route_legs,
        samples_by_leg,
        strict=True,
    ):
        samples = list(original_samples)
        if len(samples) == 1 and leg.time_s > 0.0:
            samples.append(
                SpatialSample(
                    leg=leg,
                    fraction=1.0,
                    lat=leg.end_lat,
                    lon=leg.end_lon,
                    altitude_amsl_m=leg.end_alt_amsl_m,
                )
            )
        energy_leg = energy_by_leg[leg.leg_index]
        for sample_index, sample in enumerate(samples):
            is_terminal_vertical_sample = (
                sample_index == len(samples) - 1
                and sample.fraction == 1.0
                and sample.altitude_amsl_m == leg.end_alt_amsl_m
            )
            leg_elapsed_s = (
                leg.time_s
                if is_terminal_vertical_sample
                else _leg_elapsed_at_fraction(leg, sample.fraction)
            )
            energy_fraction = (
                1.0 if leg.time_s <= 0.0 else min(1.0, leg_elapsed_s / leg.time_s)
            )
            states.append(
                RouteReachabilityState(
                    state_index=len(states),
                    leg=leg,
                    lat=sample.lat,
                    lon=sample.lon,
                    altitude_amsl_m=sample.altitude_amsl_m,
                    heading_deg=_sample_heading_deg(
                        context,
                        samples,
                        index=sample_index,
                    ),
                    elapsed_time_s=elapsed_before_leg_s + leg_elapsed_s,
                    energy_used_wh=(
                        energy_before_leg_wh + energy_leg.energy_wh * energy_fraction
                    ),
                    coverage_half_gap_m=_sample_half_gap_m(
                        context,
                        samples,
                        index=sample_index,
                    ),
                )
            )
        elapsed_before_leg_s += leg.time_s
        energy_before_leg_wh += energy_leg.energy_wh
    return states


def _evaluate_state(
    *,
    context: EstimationContext,
    energy: EnergyEstimate,
    available_zones: list[CompiledLandingZone],
    all_zone_count: int,
    route_state: RouteReachabilityState,
    tas_mps: float,
    max_distance_m: float | None,
    has_availability_filter: bool,
) -> tuple[LandingZoneStateReachability, EstimatorFailure | None]:
    del all_zone_count
    leg = route_state.leg
    available_zone_count = len(available_zones) if has_availability_filter else None
    energy_remaining_wh = energy.deliverable_capacity_wh - route_state.energy_used_wh

    if has_availability_filter and len(available_zones) == 0:
        return _state_record(
            leg=leg,
            route_state=route_state,
            nearest=None,
            reachable=None,
            energy_remaining_wh=energy_remaining_wh,
            available_zone_count=available_zone_count,
            code=FailureCode.ALL_LANDING_ZONES_UNAVAILABLE,
            message="All landing zones are marked unavailable at this route state.",
        ), None

    targets: list[ZoneTarget] = []
    altitude_failure: EstimatorFailure | None = None
    for zone in available_zones:
        target, failure = _zone_target(context, route_state, zone)
        if failure is not None:
            altitude_failure = altitude_failure or failure
            continue
        assert target is not None
        targets.append(target)
    nearest_target = min(targets, key=lambda target: target.distance_m, default=None)
    nearest = (
        None
        if nearest_target is None
        else ZoneDistance(
            zone_id=nearest_target.zone_id,
            distance_m=nearest_target.distance_m,
        )
    )
    distance_reachable_targets = [
        target
        for target in targets
        if max_distance_m is None
        or target.distance_m + route_state.coverage_half_gap_m <= max_distance_m
    ]

    if not distance_reachable_targets:
        state = _state_record(
            leg=leg,
            route_state=route_state,
            nearest=nearest,
            reachable=None,
            energy_remaining_wh=energy_remaining_wh,
            available_zone_count=available_zone_count,
            code=(
                altitude_failure.code
                if nearest is None and altitude_failure is not None
                else FailureCode.NO_REACHABLE_LANDING_ZONE
            ),
            message=(
                altitude_failure.message
                if nearest is None and altitude_failure is not None
                else "No landing zone is continuously reachable from this route state."
            ),
        )
        return state, altitude_failure if nearest is None else None

    feasible_paths: list[ReachableZonePath] = []
    path_failures: list[EstimatorFailure] = []
    for target in distance_reachable_targets:
        emergency, failure = estimate_emergency_path(
            context,
            leg,
            start_lat=route_state.lat,
            start_lon=route_state.lon,
            start_altitude_amsl_m=route_state.altitude_amsl_m,
            start_heading_deg=route_state.heading_deg,
            target_lat=target.lat,
            target_lon=target.lon,
            target_altitude_amsl_m=target.altitude_amsl_m,
            tas_mps=tas_mps,
            elapsed_time_s=route_state.elapsed_time_s,
            path_label="landing-zone divert",
        )
        if failure is not None:
            path_failures.append(failure)
            continue
        assert emergency is not None
        feasible_paths.append(ReachableZonePath(target=target, emergency=emergency))

    if not feasible_paths:
        failure = path_failures[0]
        state = _state_record(
            leg=leg,
            route_state=route_state,
            nearest=nearest,
            reachable=None,
            energy_remaining_wh=energy_remaining_wh,
            available_zone_count=available_zone_count,
            code=failure.code,
            message=failure.message,
        )
        return state, failure

    selected = min(
        feasible_paths,
        key=lambda path: path.emergency.total_energy_wh,
    )
    reachable = ZoneDistance(
        zone_id=selected.target.zone_id,
        distance_m=selected.target.distance_m,
    )
    divert_energy_wh = selected.emergency.total_energy_wh
    reserve_after_divert_wh = energy_remaining_wh - divert_energy_wh
    reserve_after_divert_percent = (
        reserve_after_divert_wh / energy.battery_capacity_wh * 100.0
    )
    reserve_ok = reserve_after_divert_wh >= energy.reserve_threshold_wh
    return _state_record(
        leg=leg,
        route_state=route_state,
        nearest=nearest,
        reachable=reachable,
        energy_remaining_wh=energy_remaining_wh,
        available_zone_count=available_zone_count,
        divert_energy_wh=divert_energy_wh,
        reserve_after_divert_wh=reserve_after_divert_wh,
        reserve_after_divert_percent=reserve_after_divert_percent,
        reserve_ok=reserve_ok,
        code=(
            None if reserve_ok else FailureCode.LANDING_ZONE_REACHABLE_BUT_BELOW_RESERVE
        ),
        message=(
            None
            if reserve_ok
            else "Reachable landing-zone divert would fall below reserve threshold."
        ),
    ), None


def _target_distance_m(
    context: EstimationContext,
    route_state: RouteReachabilityState,
    target: Point,
) -> float:
    heading_deg = route_state.heading_deg
    turn_radius_m = context.vehicle.performance.turn_radius_m
    if heading_deg is not None and turn_radius_m is not None:
        return geodesic_dubins_path_to_point_m(
            context.geod,
            start_lat=route_state.lat,
            start_lon=route_state.lon,
            heading_deg=heading_deg,
            target_lat=target.y,
            target_lon=target.x,
            turn_radius_m=turn_radius_m,
        )

    _, _, distance_m = context.geod.inv(
        route_state.lon,
        route_state.lat,
        target.x,
        target.y,
    )
    return float(distance_m)


def _zone_target(
    context: EstimationContext,
    route_state: RouteReachabilityState,
    compiled: CompiledLandingZone,
) -> tuple[ZoneTarget | None, EstimatorFailure | None]:
    state_point = Point(route_state.lon, route_state.lat)
    candidates = (
        [state_point]
        if compiled.geometry.covers(state_point)
        else _candidate_target_points(state_point, compiled.geometry)
    )
    target_point = min(
        candidates,
        key=lambda target: _target_distance_m(context, route_state, target),
    )
    distance_m = _target_distance_m(context, route_state, target_point)
    altitude_amsl_m = compiled.zone.altitude_amsl_m
    if altitude_amsl_m is None and context.terrain_provider is not None:
        altitude_amsl_m = context.terrain_provider.elevation_at(
            target_point.y,
            target_point.x,
        )
    try:
        altitude_amsl_m = (
            None
            if altitude_amsl_m is None or isinstance(altitude_amsl_m, bool)
            else float(altitude_amsl_m)
        )
    except (TypeError, ValueError):
        altitude_amsl_m = None
    if altitude_amsl_m is None or not math.isfinite(altitude_amsl_m):
        return None, EstimatorFailure(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.TERRAIN_COVERAGE_MISSING,
            message=(
                "Landing-zone surface altitude is required for descent and "
                "landing-energy reachability."
            ),
            leg_index=route_state.leg.leg_index,
            route_item_index=route_state.leg.route_item_index,
            route_item_id=route_state.leg.route_item_id,
            context={"zone_id": compiled.zone.id},
        )
    return (
        ZoneTarget(
            zone_id=compiled.zone.id,
            lat=float(target_point.y),
            lon=float(target_point.x),
            altitude_amsl_m=altitude_amsl_m,
            distance_m=distance_m,
        ),
        None,
    )


def _candidate_target_points(
    state_point: Point,
    geometry: BaseGeometry,
) -> list[Point]:
    if geometry.geom_type == "Point":
        return [geometry]

    boundary = geometry.boundary
    if not boundary.is_empty and boundary.geom_type in {
        "LineString",
        "LinearRing",
        "MultiLineString",
    }:
        sample_count = max(
            _MIN_BOUNDARY_SAMPLES,
            min(
                _MAX_BOUNDARY_SAMPLES,
                int(geometry.length * _BOUNDARY_SAMPLES_PER_DEGREE),
            ),
        )
        return [
            boundary.interpolate(index / sample_count, normalized=True)
            for index in range(sample_count)
        ]

    sub_geometries = getattr(geometry, "geoms", None)
    if sub_geometries is not None:
        candidates = [
            candidate
            for sub_geometry in sub_geometries
            for candidate in _candidate_target_points(state_point, sub_geometry)
        ]
        if candidates:
            return candidates

    _, nearest = nearest_points(state_point, geometry)
    return [nearest]


def _state_record(
    *,
    leg: LegEstimate,
    route_state: RouteReachabilityState,
    nearest: ZoneDistance | None,
    reachable: ZoneDistance | None,
    energy_remaining_wh: float,
    available_zone_count: int | None = None,
    divert_energy_wh: float | None = None,
    reserve_after_divert_wh: float | None = None,
    reserve_after_divert_percent: float | None = None,
    reserve_ok: bool = False,
    code: FailureCode | None,
    message: str | None,
) -> LandingZoneStateReachability:
    return LandingZoneStateReachability(
        state_index=route_state.state_index,
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
        lat=route_state.lat,
        lon=route_state.lon,
        altitude_amsl_m=route_state.altitude_amsl_m,
        nearest_zone_id=None if nearest is None else nearest.zone_id,
        nearest_zone_distance_m=None if nearest is None else nearest.distance_m,
        reachable_zone_id=None if reachable is None else reachable.zone_id,
        reachable_zone_distance_m=None if reachable is None else reachable.distance_m,
        divert_energy_wh=divert_energy_wh,
        energy_remaining_before_divert_wh=energy_remaining_wh,
        reserve_after_divert_wh=reserve_after_divert_wh,
        reserve_after_divert_percent=reserve_after_divert_percent,
        is_reachable=reachable is not None,
        reserve_ok=reserve_ok,
        available_zone_count=available_zone_count,
        code=code,
        message=message,
    )


def _failure_from_state(state: LandingZoneStateReachability) -> EstimatorFailure:
    context: dict[str, EstimatorContextValue] = {
        "state_index": state.state_index,
        "nearest_zone_id": state.nearest_zone_id,
        "nearest_zone_distance_m": state.nearest_zone_distance_m,
        "reachable_zone_id": state.reachable_zone_id,
        "reachable_zone_distance_m": state.reachable_zone_distance_m,
        "divert_energy_wh": state.divert_energy_wh,
        "energy_remaining_before_divert_wh": state.energy_remaining_before_divert_wh,
        "reserve_after_divert_wh": state.reserve_after_divert_wh,
        "reserve_after_divert_percent": state.reserve_after_divert_percent,
    }
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=state.code,
        message=state.message or "Landing-zone reachability check failed.",
        leg_index=state.leg_index,
        route_item_index=state.route_item_index,
        route_item_id=state.route_item_id,
        context=context,
    )


def _mission_failure(
    *,
    code: FailureCode,
    message: str,
    context: dict[str, EstimatorContextValue],
) -> EstimatorFailure:
    return EstimatorFailure(
        kind=FailureKind.INVALID_INPUT,
        code=code,
        message=message,
        context=context,
    )


def _zone_geometry_failure(*, zone: LandingZone, reason: str) -> EstimatorFailure:
    return EstimatorFailure(
        kind=FailureKind.INVALID_INPUT,
        code=FailureCode.INVALID_GEOMETRY,
        message="Landing-zone geometry is invalid.",
        context={
            "zone_id": zone.id,
            "reason": reason,
        },
    )
