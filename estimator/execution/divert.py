"""Deterministic divert route estimation for lost-link policy outcomes."""

from collections.abc import Sequence

from pyproj import Geod
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from estimator.core.landing_zone import LandingZone
from estimator.core.results import EnergyEstimate
from estimator.core.scenario import DivertRouteEstimate
from estimator.execution.spatial import polygon_set_to_geometry_list
from schemas.mission import MissionPlan
from schemas.vehicle import VehicleProfile

_GEOD = Geod(ellps="WGS84")
_SECONDS_PER_HOUR = 3600.0


def compute_divert_estimate(
    *,
    action_lat: float,
    action_lon: float,
    action_at_timeline_index: int,
    target_zone_id: str,
    landing_zones: Sequence[LandingZone],
    energy: EnergyEstimate | None,
    mission: MissionPlan,
    vehicle: VehicleProfile,
) -> DivertRouteEstimate:
    """Compute a deterministic straight-line divert route estimate.

    Uses TAS-based transit time and cruise-power energy without wind correction
    or geofence intersection on the divert leg.
    """
    if energy is None:
        return _no_estimate(
            target_zone_id,
            reason="Energy estimate is not available; cannot compute divert route.",
        )

    target_zone = next((z for z in landing_zones if z.id == target_zone_id), None)
    if target_zone is None:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason=f"Divert target zone '{target_zone_id}' not found in configured landing zones.",
        )

    geometry = _compile_zone_geometry(target_zone)
    if geometry is None:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason=f"Divert target zone '{target_zone_id}' has invalid or empty geometry.",
        )

    distance_m = _distance_to_geometry_m(action_lat, action_lon, geometry)

    tas_mps = _resolve_tas(mission, vehicle)
    if tas_mps is None or tas_mps <= 0:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason="No valid cruise TAS available for divert estimate.",
        )

    time_s = distance_m / tas_mps
    divert_energy_wh = vehicle.energy.cruise_power_w * time_s / _SECONDS_PER_HOUR
    energy_remaining_wh = _energy_remaining_at_index(energy, action_at_timeline_index)
    reserve_after_wh = energy_remaining_wh - divert_energy_wh
    reserve_after_percent = reserve_after_wh / energy.battery_capacity_wh * 100.0
    is_feasible = reserve_after_wh >= energy.reserve_threshold_wh

    return DivertRouteEstimate(
        target_zone_id=target_zone_id,
        distance_m=distance_m,
        time_s=time_s,
        energy_wh=divert_energy_wh,
        energy_remaining_at_action_wh=energy_remaining_wh,
        reserve_after_divert_wh=reserve_after_wh,
        reserve_after_divert_percent=reserve_after_percent,
        reserve_threshold_wh=energy.reserve_threshold_wh,
        is_feasible=is_feasible,
        infeasible_reason=None if is_feasible else "Insufficient reserve after completing the divert leg.",
    )


def _compile_zone_geometry(zone: LandingZone) -> BaseGeometry | None:
    geometries: list[BaseGeometry] = [
        Point(p.lon, p.lat) for p in zone.geometry.points
    ]
    geometries.extend(polygon_set_to_geometry_list(zone.geometry.polygons))
    geometry = unary_union(geometries)
    if geometry.is_empty or not geometry.is_valid:
        return None
    return geometry


def _distance_to_geometry_m(lat: float, lon: float, geometry: BaseGeometry) -> float:
    state_point = Point(lon, lat)
    if geometry.covers(state_point):
        return 0.0
    _, nearest = nearest_points(state_point, geometry)
    _, _, distance_m = _GEOD.inv(lon, lat, nearest.x, nearest.y)
    return distance_m


def _resolve_tas(mission: MissionPlan, vehicle: VehicleProfile) -> float | None:
    if mission.defaults.cruise_speed_mps is not None:
        return mission.defaults.cruise_speed_mps
    return vehicle.performance.cruise_speed_mps


def _energy_remaining_at_index(energy: EnergyEstimate, timeline_index: int) -> float:
    max_leg_index = timeline_index - 1
    used_wh = sum(leg.energy_wh for leg in energy.legs if leg.leg_index <= max_leg_index)
    return energy.battery_capacity_wh - used_wh


def _no_estimate(
    target_zone_id: str,
    *,
    reason: str,
    energy: EnergyEstimate | None = None,
    action_at_timeline_index: int = 0,
) -> DivertRouteEstimate:
    energy_remaining = (
        _energy_remaining_at_index(energy, action_at_timeline_index)
        if energy is not None
        else 0.0
    )
    reserve_threshold = energy.reserve_threshold_wh if energy is not None else 0.0
    return DivertRouteEstimate(
        target_zone_id=target_zone_id,
        distance_m=0.0,
        time_s=0.0,
        energy_wh=0.0,
        energy_remaining_at_action_wh=energy_remaining,
        reserve_after_divert_wh=energy_remaining,
        reserve_after_divert_percent=(
            energy_remaining / energy.battery_capacity_wh * 100.0
            if energy is not None and energy.battery_capacity_wh > 0
            else 0.0
        ),
        reserve_threshold_wh=reserve_threshold,
        is_feasible=False,
        infeasible_reason=reason,
    )
