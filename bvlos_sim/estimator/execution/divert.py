"""Deterministic divert route estimation for lost-link policy outcomes."""

import math
from collections.abc import Sequence

from pyproj import Geod
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union

from bvlos_sim.estimator.core.constants import (
    DEFAULT_MAX_CRAB_ANGLE_DEG,
    DEFAULT_MIN_GROUNDSPEED_MPS,
)
from bvlos_sim.estimator.core.enums import WarningCode
from bvlos_sim.estimator.core.landing_zone import LandingZone
from bvlos_sim.estimator.core.results import EnergyEstimate
from bvlos_sim.estimator.core.scenario import DivertRouteEstimate
from bvlos_sim.estimator.execution.energy import adjusted_cruise_power_for_vehicle
from bvlos_sim.estimator.execution.spatial import polygon_set_to_geometry_list
from bvlos_sim.estimator.math.dubins import dubins_path_to_point_m
from bvlos_sim.estimator.math.wind_triangle import WindTriangleSolution, solve_wind_triangle
from bvlos_sim.schemas.mission import MissionPlan
from bvlos_sim.schemas.vehicle import VehicleProfile

_GEOD = Geod(ellps="WGS84")
_SECONDS_PER_HOUR = 3600.0
_MIN_BOUNDARY_SAMPLES = 8
_MAX_BOUNDARY_SAMPLES = 64
_BOUNDARY_SAMPLES_PER_DEGREE = 2
# Heading resolution used to bound the turn a Dubins divert flies.
_SWEPT_HEADING_STEP_DEG = 5.0


def _still_air_solution(tas_mps: float) -> WindTriangleSolution:
    return WindTriangleSolution(
        required_heading_deg=0.0,
        crab_angle_deg=0.0,
        groundspeed_mps=tas_mps,
        wind_along_track_mps=0.0,
        wind_cross_track_mps=0.0,
    )


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
    entry_heading_deg: float | None = None,
    wind_east_mps: float = 0.0,
    wind_north_mps: float = 0.0,
    wind_corrected: bool = False,
    action_altitude_amsl_m: float = 0.0,
) -> DivertRouteEstimate:
    """Compute a deterministic divert route estimate.

    When entry_heading_deg and vehicle.performance.turn_radius_m are available,
    uses Dubins path distance (bank-angle-constrained arc + straight). Otherwise
    falls back to straight-line geodesic distance.

    When wind_corrected=True the transit time and energy use a wind-triangle
    ground speed. When wind_corrected=False (the default), TAS is used and a
    DIVERT_ENERGY_TAS_ONLY advisory warning is emitted.
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

    geodesic_dist_m = _distance_to_geometry_m(action_lat, action_lon, geometry)
    turn_radius_m = vehicle.performance.turn_radius_m
    if entry_heading_deg is not None and turn_radius_m is not None:
        distance_m = _dubins_distance_to_geometry_m(
            action_lat, action_lon, entry_heading_deg, turn_radius_m, geometry
        )
    else:
        distance_m = geodesic_dist_m

    tas_mps = _resolve_tas(mission, vehicle)
    if tas_mps is None or tas_mps <= 0:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason="No valid cruise TAS available for divert estimate.",
        )

    solution = _resolve_groundspeed(
        action_lat,
        action_lon,
        geometry,
        tas_mps,
        wind_east_mps=wind_east_mps,
        wind_north_mps=wind_north_mps,
        wind_corrected=wind_corrected,
        entry_heading_deg=entry_heading_deg,
    )
    if solution is None or solution.groundspeed_mps <= 0:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason="Headwind exceeds cruise TAS; divert groundspeed is zero or negative.",
        )

    # A divert the aircraft cannot aerodynamically fly is not a divert. These
    # are the same two gates the RTH and landing-zone paths already apply.
    max_crab_deg = (
        vehicle.performance.max_crab_angle_deg
        if vehicle.performance.max_crab_angle_deg is not None
        else DEFAULT_MAX_CRAB_ANGLE_DEG
    )
    if abs(solution.crab_angle_deg) > max_crab_deg:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason=(
                f"Divert requires a {abs(solution.crab_angle_deg):.1f} deg crab "
                f"angle, above the {max_crab_deg:.1f} deg vehicle limit."
            ),
        )
    min_groundspeed_mps = (
        mission.estimation.min_groundspeed_mps
        if mission.estimation is not None
        and mission.estimation.min_groundspeed_mps is not None
        else DEFAULT_MIN_GROUNDSPEED_MPS
    )
    if solution.groundspeed_mps < min_groundspeed_mps:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason=(
                f"Divert groundspeed {solution.groundspeed_mps:.2f} m/s is below "
                f"the {min_groundspeed_mps:.2f} m/s minimum."
            ),
        )

    gs_mps = solution.groundspeed_mps
    time_s = distance_m / gs_mps
    divert_power_w = adjusted_cruise_power_for_vehicle(
        vehicle,
        altitude_amsl_m=action_altitude_amsl_m,
    )
    divert_energy_wh = divert_power_w * time_s / _SECONDS_PER_HOUR
    descent_energy_wh = _terminal_descent_energy_wh(
        vehicle,
        action_altitude_amsl_m=action_altitude_amsl_m,
        surface_altitude_amsl_m=target_zone.altitude_amsl_m,
    )
    if descent_energy_wh is None:
        return _no_estimate(
            target_zone_id,
            energy=energy,
            action_at_timeline_index=action_at_timeline_index,
            reason=(
                "Descent rate and power are required to budget the terminal "
                "descent to the divert zone."
            ),
        )
    divert_energy_wh += descent_energy_wh
    energy_remaining_wh = _energy_remaining_at_index(energy, action_at_timeline_index)
    reserve_after_wh = energy_remaining_wh - divert_energy_wh
    reserve_after_percent = reserve_after_wh / energy.battery_capacity_wh * 100.0
    is_feasible = reserve_after_wh >= energy.reserve_threshold_wh
    warnings = [] if wind_corrected else [WarningCode.DIVERT_ENERGY_TAS_ONLY]

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
        infeasible_reason=None
        if is_feasible
        else "Insufficient reserve after completing the divert leg.",
        warnings=warnings,
    )


def _compile_zone_geometry(zone: LandingZone) -> BaseGeometry | None:
    geometries: list[BaseGeometry] = [Point(p.lon, p.lat) for p in zone.geometry.points]
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


def _dubins_distance_to_geometry_m(
    lat: float,
    lon: float,
    heading_deg: float,
    turn_radius_m: float,
    geometry: BaseGeometry,
) -> float:
    """Dubins path distance from pose (lat, lon, heading) to nearest zone point.

    Uses geodesic-aware sampling in a local East-North frame centred on the
    vehicle position.
    """
    return _geodesic_dubins_distance_m(lat, lon, heading_deg, turn_radius_m, geometry)


def _geodesic_dubins_distance_m(
    lat: float,
    lon: float,
    heading_deg: float,
    turn_radius_m: float,
    geometry: BaseGeometry,
) -> float:
    """Geodesic-aware Dubins distance from pose to target geometry."""
    state_point = Point(lon, lat)
    if geometry.covers(state_point):
        return 0.0

    candidates = list(_candidate_target_points(state_point, geometry))
    heading_rad = math.radians(heading_deg)
    return min(
        _dubins_distance_to_target_m(
            lat,
            lon,
            heading_rad,
            turn_radius_m,
            candidate,
        )
        for candidate in candidates
    )


def _candidate_target_points(
    state_point: Point,
    geometry: BaseGeometry,
) -> Sequence[Point]:
    if geometry.geom_type == "Point":
        return [geometry]

    boundary = geometry.boundary
    if not boundary.is_empty and boundary.geom_type in {
        "LineString",
        "LinearRing",
        "MultiLineString",
    }:
        sample_count = _boundary_sample_count(geometry)
        return [
            boundary.interpolate(i / sample_count, normalized=True)
            for i in range(sample_count)
        ]

    geoms = getattr(geometry, "geoms", None)
    if geoms is not None:
        candidates = [
            candidate
            for geom in geoms
            for candidate in _candidate_target_points(state_point, geom)
        ]
        if candidates:
            return candidates

    _, nearest = nearest_points(state_point, geometry)
    return [nearest]


def _boundary_sample_count(geometry: BaseGeometry) -> int:
    return max(
        _MIN_BOUNDARY_SAMPLES,
        min(
            _MAX_BOUNDARY_SAMPLES,
            int(geometry.length * _BOUNDARY_SAMPLES_PER_DEGREE),
        ),
    )


def _dubins_distance_to_target_m(
    lat: float,
    lon: float,
    heading_rad: float,
    turn_radius_m: float,
    target: Point,
) -> float:
    fwd_az, _, dist_m = _GEOD.inv(lon, lat, target.x, target.y)
    bearing_rad = math.radians(fwd_az)
    target_e = dist_m * math.sin(bearing_rad)
    target_n = dist_m * math.cos(bearing_rad)
    return dubins_path_to_point_m(
        0.0, 0.0, heading_rad, target_e, target_n, turn_radius_m
    )


def _resolve_groundspeed(
    action_lat: float,
    action_lon: float,
    target_geometry: BaseGeometry,
    tas_mps: float,
    *,
    wind_east_mps: float,
    wind_north_mps: float,
    wind_corrected: bool,
    entry_heading_deg: float | None = None,
) -> WindTriangleSolution | None:
    """Return groundspeed for the divert leg.

    When wind_corrected=True, computes the track bearing to the nearest target
    geometry point and applies a wind-triangle correction. Returns None when
    the headwind exceeds TAS (no valid triangle solution).
    """
    if not wind_corrected:
        return _still_air_solution(tas_mps)

    state_point = Point(action_lon, action_lat)
    if target_geometry.covers(state_point):
        return _still_air_solution(tas_mps)

    _, nearest = nearest_points(state_point, target_geometry)
    fwd_az, _, _ = _GEOD.inv(action_lon, action_lat, nearest.x, nearest.y)
    return _worst_swept_solution(
        fwd_az,
        entry_heading_deg,
        tas_mps=tas_mps,
        wind_east_mps=wind_east_mps,
        wind_north_mps=wind_north_mps,
    )


def _swept_headings_deg(
    track_deg: float,
    entry_heading_deg: float | None,
) -> list[float]:
    """Headings the divert actually flies, entry heading through final track.

    A Dubins divert turns from its entry heading onto the track to the zone, so
    the whole path is not flown on the final bearing. Sampling the swept range
    lets the wind triangle see the headings the turn passes through.
    """

    if entry_heading_deg is None:
        return [track_deg]
    delta_deg = (track_deg - entry_heading_deg + 180.0) % 360.0 - 180.0
    steps = max(1, math.ceil(abs(delta_deg) / _SWEPT_HEADING_STEP_DEG))
    return [
        entry_heading_deg + delta_deg * index / steps for index in range(steps + 1)
    ]


def _worst_swept_solution(
    track_deg: float,
    entry_heading_deg: float | None,
    *,
    tas_mps: float,
    wind_east_mps: float,
    wind_north_mps: float,
) -> WindTriangleSolution | None:
    """Worst wind-triangle solution over the headings the divert sweeps.

    Charging the whole Dubins path at the final bearing's groundspeed
    understates time and energy whenever the entry arc turns into wind. This
    bounds the path by its harshest heading, which is conservative by
    construction: it can overstate the divert cost, never understate it.
    """

    worst: WindTriangleSolution | None = None
    for heading_deg in _swept_headings_deg(track_deg, entry_heading_deg):
        solution = solve_wind_triangle(
            track_deg=heading_deg,
            tas_mps=tas_mps,
            wind_east_mps=wind_east_mps,
            wind_north_mps=wind_north_mps,
        )
        if solution is None:
            return None
        if worst is None or solution.groundspeed_mps < worst.groundspeed_mps:
            worst = solution
    return worst


def _terminal_descent_energy_wh(
    vehicle: VehicleProfile,
    *,
    action_altitude_amsl_m: float,
    surface_altitude_amsl_m: float | None,
) -> float | None:
    """Energy to descend from the divert altitude to the landing surface.

    Omitting it budgeted a divert as pure horizontal transit, understating the
    cost of the manoeuvre the reserve check is supposed to prove. Returns None
    when the descent cannot be budgeted, so the caller fails closed the way
    landing-zone reachability already does for an unknown surface altitude.
    """

    if surface_altitude_amsl_m is None or not math.isfinite(surface_altitude_amsl_m):
        return None
    drop_m = action_altitude_amsl_m - surface_altitude_amsl_m
    if drop_m <= 0.0:
        return 0.0
    rate_mps = vehicle.performance.descent_rate_mps
    if rate_mps is None or not math.isfinite(rate_mps) or rate_mps <= 0.0:
        return None
    power_w = vehicle.energy.descent_power_w or vehicle.energy.cruise_power_w
    if power_w is None or not math.isfinite(power_w) or power_w <= 0.0:
        return None
    return power_w * (drop_m / rate_mps) / _SECONDS_PER_HOUR


def _resolve_tas(mission: MissionPlan, vehicle: VehicleProfile) -> float | None:
    if mission.defaults.cruise_speed_mps is not None:
        return mission.defaults.cruise_speed_mps
    return vehicle.performance.cruise_speed_mps


def _energy_remaining_at_index(energy: EnergyEstimate, timeline_index: int) -> float:
    max_leg_index = timeline_index - 1
    used_wh = sum(
        leg.energy_wh for leg in energy.legs if leg.leg_index <= max_leg_index
    )
    return energy.deliverable_capacity_wh - used_wh


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
