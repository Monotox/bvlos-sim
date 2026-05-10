"""Deterministic static landing-zone reachability evaluation."""

from dataclasses import dataclass

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
from estimator.execution.energy import SECONDS_PER_HOUR
from estimator.execution.runtime import EstimationContext
from estimator.execution.spatial import polygon_set_to_geometry_list


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


def evaluate_landing_zone_reachability(
    context: EstimationContext,
    energy: EnergyEstimate | None,
) -> LandingZoneEvaluation:
    """Evaluate static landing-zone reachability after energy feasibility."""

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

    energy_used_by_leg = _energy_used_by_leg(energy)
    max_distance_m = context.mission.constraints.min_distance_to_landing_zone_m
    states = [
        _evaluate_state(
            context=context,
            energy=energy,
            compiled_zones=compiled_zones,
            leg=leg,
            state_index=state_index,
            energy_used_wh=energy_used_by_leg.get(leg.leg_index, 0.0),
            tas_mps=tas_mps,
            max_distance_m=max_distance_m,
        )
        for state_index, leg in enumerate(context.route_legs)
    ]

    landing_zone = LandingZoneEstimate(
        is_feasible=all(state.is_reachable and state.reserve_ok for state in states),
        checked_zone_count=len(compiled_zones),
        checked_state_count=len(states),
        max_allowed_distance_m=max_distance_m,
        reserve_threshold_percent=energy.reserve_threshold_percent,
        reserve_threshold_wh=energy.reserve_threshold_wh,
        states=states,
    )
    failed_state = next((state for state in states if state.code is not None), None)
    return LandingZoneEvaluation(
        landing_zone=landing_zone,
        failure=_failure_from_state(failed_state) if failed_state is not None else None,
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


def _energy_used_by_leg(energy: EnergyEstimate) -> dict[int, float]:
    energy_used_wh = 0.0
    used_by_leg: dict[int, float] = {}
    for leg in energy.legs:
        energy_used_wh += leg.energy_wh
        used_by_leg[leg.leg_index] = energy_used_wh
    return used_by_leg


def _evaluate_state(
    *,
    context: EstimationContext,
    energy: EnergyEstimate,
    compiled_zones: list[CompiledLandingZone],
    leg: LegEstimate,
    state_index: int,
    energy_used_wh: float,
    tas_mps: float,
    max_distance_m: float | None,
) -> LandingZoneStateReachability:
    nearest = _nearest_zone_distance(context, compiled_zones, leg)
    reachable = (
        nearest
        if nearest is not None
        and (max_distance_m is None or nearest.distance_m <= max_distance_m)
        else None
    )
    energy_remaining_wh = energy.battery_capacity_wh - energy_used_wh

    if reachable is None:
        return _state_record(
            leg=leg,
            state_index=state_index,
            nearest=nearest,
            reachable=None,
            energy_remaining_wh=energy_remaining_wh,
            code=FailureCode.NO_REACHABLE_LANDING_ZONE,
            message="No landing zone is reachable from this route state.",
        )

    divert_energy_wh = _divert_energy_wh(
        distance_m=reachable.distance_m,
        tas_mps=tas_mps,
        cruise_power_w=context.vehicle.energy.cruise_power_w,
    )
    reserve_after_divert_wh = energy_remaining_wh - divert_energy_wh
    reserve_after_divert_percent = (
        reserve_after_divert_wh / energy.battery_capacity_wh * 100.0
    )
    reserve_ok = reserve_after_divert_wh >= energy.reserve_threshold_wh
    return _state_record(
        leg=leg,
        state_index=state_index,
        nearest=nearest,
        reachable=reachable,
        energy_remaining_wh=energy_remaining_wh,
        divert_energy_wh=divert_energy_wh,
        reserve_after_divert_wh=reserve_after_divert_wh,
        reserve_after_divert_percent=reserve_after_divert_percent,
        reserve_ok=reserve_ok,
        code=(
            None
            if reserve_ok
            else FailureCode.LANDING_ZONE_REACHABLE_BUT_BELOW_RESERVE
        ),
        message=(
            None
            if reserve_ok
            else "Reachable landing-zone divert would fall below reserve threshold."
        ),
    )


def _nearest_zone_distance(
    context: EstimationContext,
    compiled_zones: list[CompiledLandingZone],
    leg: LegEstimate,
) -> ZoneDistance | None:
    distances = [
        ZoneDistance(
            zone_id=zone.zone.id,
            distance_m=_distance_to_geometry_m(context, leg, zone.geometry),
        )
        for zone in compiled_zones
    ]
    return min(distances, key=lambda distance: distance.distance_m, default=None)


def _distance_to_geometry_m(
    context: EstimationContext,
    leg: LegEstimate,
    geometry: BaseGeometry,
) -> float:
    state_point = Point(leg.end_lon, leg.end_lat)
    if geometry.covers(state_point):
        return 0.0

    _, nearest = nearest_points(state_point, geometry)
    _, _, distance_m = context.geod.inv(
        leg.end_lon,
        leg.end_lat,
        nearest.x,
        nearest.y,
    )
    return distance_m


def _divert_energy_wh(
    *,
    distance_m: float,
    tas_mps: float,
    cruise_power_w: float,
) -> float:
    return cruise_power_w * (distance_m / tas_mps) / SECONDS_PER_HOUR


def _state_record(
    *,
    leg: LegEstimate,
    state_index: int,
    nearest: ZoneDistance | None,
    reachable: ZoneDistance | None,
    energy_remaining_wh: float,
    divert_energy_wh: float | None = None,
    reserve_after_divert_wh: float | None = None,
    reserve_after_divert_percent: float | None = None,
    reserve_ok: bool = False,
    code: FailureCode | None,
    message: str | None,
) -> LandingZoneStateReachability:
    return LandingZoneStateReachability(
        state_index=state_index,
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
        lat=leg.end_lat,
        lon=leg.end_lon,
        altitude_amsl_m=leg.end_alt_amsl_m,
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
