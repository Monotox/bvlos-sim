"""Tests for the 2D Dubins path-to-point solver and Dubins-aware divert routing."""

import math

import pytest
from pyproj import Geod

from bvlos_sim.estimator.math.dubins import (
    _ls_path_length,
    _rs_path_length,
    dubins_path_to_point_m,
)
from bvlos_sim.estimator.execution.divert import compute_divert_estimate
from bvlos_sim.estimator.core.results import EnergyEstimate
from bvlos_sim.estimator.core.landing_zone import LandingZone
from tests.helpers import make_mission, make_vehicle

_GEOD = Geod(ellps="WGS84")
PointTuple = tuple[float, float]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point_zone(zone_id: str, *, lat: float, lon: float) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
            "altitude_amsl_m": 12.0,
            "geometry": {"points": [{"lat": lat, "lon": lon}]},
        }
    )


def _polygon_zone(zone_id: str, points: list[tuple[float, float]]) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
            "altitude_amsl_m": 12.0,
            "geometry": {
                "polygons": [
                    {
                        "exterior": [{"lat": lat, "lon": lon} for lat, lon in points],
                    }
                ]
            },
        }
    )


def _offset_point(lat: float, lon: float, east_m: float, north_m: float) -> PointTuple:
    distance_m = math.hypot(east_m, north_m)
    azimuth_deg = math.degrees(math.atan2(east_m, north_m))
    target_lon, target_lat, _ = _GEOD.fwd(lon, lat, azimuth_deg, distance_m)
    return target_lat, target_lon


def _planar_dubins_distance(
    *,
    start_lat: float,
    start_lon: float,
    target_lat: float,
    target_lon: float,
    heading_deg: float,
    turn_radius_m: float,
) -> float:
    fwd_az, _, dist_m = _GEOD.inv(start_lon, start_lat, target_lon, target_lat)
    bearing_rad = math.radians(fwd_az)
    target_e = dist_m * math.sin(bearing_rad)
    target_n = dist_m * math.cos(bearing_rad)
    return dubins_path_to_point_m(
        0.0,
        0.0,
        math.radians(heading_deg),
        target_e,
        target_n,
        turn_radius_m,
    )


def _energy(battery_capacity_wh: float = 900.0) -> EnergyEstimate:
    reserve_threshold_wh = battery_capacity_wh * 0.25
    return EnergyEstimate(
        is_feasible=True,
        total_energy_wh=0.0,
        battery_capacity_wh=battery_capacity_wh,
        usable_energy_wh=battery_capacity_wh - reserve_threshold_wh,
        reserve_threshold_percent=25.0,
        reserve_threshold_wh=reserve_threshold_wh,
        reserve_at_landing_wh=battery_capacity_wh,
        reserve_at_landing_percent=100.0,
        legs=[],
    )


# ---------------------------------------------------------------------------
# dubins_path_to_point_m — geometry invariants
# ---------------------------------------------------------------------------


def test_straight_ahead_path_equals_geodesic() -> None:
    """Target directly ahead: Dubins path degenerates to straight line."""
    r = 80.0
    dist = 1000.0
    result = dubins_path_to_point_m(0.0, 0.0, 0.0, 0.0, dist, r)
    assert math.isclose(result, dist, rel_tol=1e-6)


def test_target_behind_path_exceeds_semicircle_plus_straight() -> None:
    """Target 180° behind: path must include a U-turn arc."""
    r = 80.0
    dist = 1000.0
    result = dubins_path_to_point_m(0.0, 0.0, 0.0, 0.0, -dist, r)
    # Minimum turnaround cost is slightly more than π*r (semicircle + straight)
    assert result > math.pi * r + dist - 1.0
    assert result < 2 * math.pi * r + dist  # never more than full circle + straight


def test_target_right_uses_right_turn() -> None:
    """Target 90° right: RS path should be shorter than LS path."""
    r = 80.0
    rs = _rs_path_length(0.0, 0.0, 0.0, 1000.0, 0.0, r)
    ls = _ls_path_length(0.0, 0.0, 0.0, 1000.0, 0.0, r)
    assert rs is not None and ls is not None
    assert rs < ls


def test_target_left_uses_left_turn() -> None:
    """Target 90° left: LS path should be shorter than RS path."""
    r = 80.0
    rs = _rs_path_length(0.0, 0.0, 0.0, -1000.0, 0.0, r)
    ls = _ls_path_length(0.0, 0.0, 0.0, -1000.0, 0.0, r)
    assert rs is not None and ls is not None
    assert ls < rs


def test_symmetric_left_right_same_length() -> None:
    """Paths to mirror-image targets have the same Dubins length."""
    r = 80.0
    # Target 45° right
    d_right = dubins_path_to_point_m(0.0, 0.0, 0.0, 500.0, 500.0, r)
    # Target 45° left (mirror)
    d_left = dubins_path_to_point_m(0.0, 0.0, 0.0, -500.0, 500.0, r)
    assert math.isclose(d_right, d_left, rel_tol=1e-9)


def test_dubins_path_no_less_than_straight_line() -> None:
    """Dubins path is never shorter than the straight-line distance."""
    r = 80.0
    for target_e, target_n in [
        (500.0, 0.0),
        (0.0, 500.0),
        (-300.0, 400.0),
        (0.0, -200.0),
    ]:
        straight = math.hypot(target_e, target_n)
        dubins = dubins_path_to_point_m(0.0, 0.0, 0.0, target_e, target_n, r)
        assert dubins >= straight - 1e-9, f"Dubins {dubins} < straight {straight}"


def test_dubins_path_at_zero_distance_is_zero() -> None:
    result = dubins_path_to_point_m(0.0, 0.0, 0.0, 0.0, 0.0, 80.0)
    assert math.isclose(result, 0.0, abs_tol=1e-9)


def test_dubins_path_zero_radius_falls_back_to_euclidean() -> None:
    # 300-400-500 is a scaled 3-4-5 Pythagorean triple
    result = dubins_path_to_point_m(0.0, 0.0, 0.0, 300.0, 400.0, 0.0)
    assert math.isclose(result, 500.0, rel_tol=1e-9)


def test_rs_none_when_target_inside_right_circle() -> None:
    """Target inside right turn circle → RS returns None."""
    r = 100.0
    # Right turn center at (r, 0) for heading 0. Put target at center (r, 0).
    result = _rs_path_length(0.0, 0.0, 0.0, r, 0.0, r)
    assert result is None


def test_various_headings_consistent() -> None:
    """Rotating frame by heading change gives same Dubins distance."""
    r = 80.0
    dist = 500.0
    # Target 90° to the right of vehicle. Verify consistent regardless of absolute heading.
    for theta_deg in [0, 45, 90, 180, 270]:
        theta = math.radians(theta_deg)
        # Rotate target (500, 0) — which is East — by heading angle to get right-side target
        # Right of heading θ is direction (cos(θ), -sin(θ)) in East-North
        target_e = dist * math.cos(theta)
        target_n = -dist * math.sin(theta)
        d = dubins_path_to_point_m(0.0, 0.0, theta, target_e, target_n, r)
        # For any heading, turning 90° right to a target at 90° right should give same path length
        # Compare against base case (theta=0)
        d_base = dubins_path_to_point_m(0.0, 0.0, 0.0, dist, 0.0, r)
        assert math.isclose(d, d_base, rel_tol=1e-6), (
            f"Heading {theta_deg}°: got {d}, expected {d_base}"
        )


# ---------------------------------------------------------------------------
# Dubins-aware divert routing — compute_divert_estimate with entry_heading_deg
# ---------------------------------------------------------------------------


def test_divert_with_heading_gives_larger_or_equal_distance_than_straight() -> None:
    """Dubins path distance ≥ geodesic straight-line distance."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz", lat=52.001, lon=4.002)
    energy = _energy()

    result_straight = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )

    # Heading directly toward zone (approx NE ~50°)
    result_dubins = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=50.0,
    )

    assert result_dubins.distance_m >= result_straight.distance_m - 1.0


def test_divert_heading_directly_toward_target_equals_straight() -> None:
    """When already pointing at the target, Dubins ≈ straight-line."""
    mission = make_mission()
    vehicle = make_vehicle()
    # Place target exactly North of action point
    zone = _point_zone("lz-north", lat=52.01, lon=4.0)
    energy = _energy()

    result_straight = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-north",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )

    result_dubins = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-north",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=0.0,  # heading North, target is North
    )

    # Should be nearly identical (within turn arc resolution)
    assert math.isclose(
        result_dubins.distance_m, result_straight.distance_m, rel_tol=1e-4
    )


def test_divert_heading_perpendicular_adds_turn_cost() -> None:
    """Vehicle heading perpendicular to target produces longer Dubins path."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-north", lat=52.01, lon=4.0)
    energy = _energy()

    result_straight = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-north",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )

    result_perpendicular = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-north",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=90.0,  # heading East, target is North
    )

    assert result_perpendicular.distance_m > result_straight.distance_m


def test_divert_no_entry_heading_falls_back_to_straight_line() -> None:
    """Without entry heading, result is identical to no-heading call."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz", lat=52.001, lon=4.001)
    energy = _energy()

    r1 = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )
    r2 = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )
    assert r1.distance_m == r2.distance_m


def test_divert_no_turn_radius_falls_back_to_straight_line() -> None:
    """Vehicle without turn_radius_m falls back to straight-line geodesic."""
    mission = make_mission()
    vehicle = make_vehicle()
    vehicle.performance = vehicle.performance.model_copy(update={"turn_radius_m": None})
    zone = _point_zone("lz", lat=52.001, lon=4.001)
    energy = _energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=180.0,  # heading provided but radius is None
    )

    result_no_heading = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )

    assert result.distance_m == pytest.approx(result_no_heading.distance_m, rel=1e-9)


# ---------------------------------------------------------------------------
# Geodesic Dubins
# ---------------------------------------------------------------------------


def test_geodesic_dubins_point_zone_equals_planar_for_short_distance() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    turn_radius_m = vehicle.performance.turn_radius_m
    assert turn_radius_m is not None
    action_lat = 52.0
    action_lon = 4.0
    target_lat, target_lon = _offset_point(action_lat, action_lon, 250.0, 433.0)
    zone = _point_zone("lz-short", lat=target_lat, lon=target_lon)
    heading_deg = 30.0

    result = compute_divert_estimate(
        action_lat=action_lat,
        action_lon=action_lon,
        action_at_timeline_index=0,
        target_zone_id="lz-short",
        landing_zones=[zone],
        energy=_energy(),
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=heading_deg,
    )

    expected = _planar_dubins_distance(
        start_lat=action_lat,
        start_lon=action_lon,
        target_lat=target_lat,
        target_lon=target_lon,
        heading_deg=heading_deg,
        turn_radius_m=turn_radius_m,
    )
    assert result.distance_m == pytest.approx(expected, rel=0.01)


def test_geodesic_dubins_polygon_zone_samples_boundary() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    action_lat = 52.0
    action_lon = 4.0
    center_lat, center_lon = _offset_point(action_lat, action_lon, 0.0, 2_000.0)
    boundary_offsets = [
        (-250.0, 1_750.0),
        (250.0, 1_750.0),
        (250.0, 2_250.0),
        (-250.0, 2_250.0),
        (-250.0, 1_750.0),
    ]
    polygon = _polygon_zone(
        "lz-square",
        [
            _offset_point(action_lat, action_lon, east, north)
            for east, north in boundary_offsets
        ],
    )
    centroid = _point_zone("lz-centroid", lat=center_lat, lon=center_lon)

    boundary_result = compute_divert_estimate(
        action_lat=action_lat,
        action_lon=action_lon,
        action_at_timeline_index=0,
        target_zone_id="lz-square",
        landing_zones=[polygon],
        energy=_energy(),
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=0.0,
    )
    centroid_result = compute_divert_estimate(
        action_lat=action_lat,
        action_lon=action_lon,
        action_at_timeline_index=0,
        target_zone_id="lz-centroid",
        landing_zones=[centroid],
        energy=_energy(),
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=0.0,
    )

    assert boundary_result.distance_m < centroid_result.distance_m


def test_geodesic_dubins_vehicle_inside_zone_returns_zero() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    action_lat = 52.0
    action_lon = 4.0
    boundary_offsets = [
        (-250.0, -250.0),
        (250.0, -250.0),
        (250.0, 250.0),
        (-250.0, 250.0),
        (-250.0, -250.0),
    ]
    polygon = _polygon_zone(
        "lz-around",
        [
            _offset_point(action_lat, action_lon, east, north)
            for east, north in boundary_offsets
        ],
    )

    result = compute_divert_estimate(
        action_lat=action_lat,
        action_lon=action_lon,
        action_at_timeline_index=0,
        target_zone_id="lz-around",
        landing_zones=[polygon],
        energy=_energy(),
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=90.0,
    )

    assert result.distance_m == 0.0


def test_geodesic_dubins_heading_toward_target_approximates_geodesic() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    action_lat = 52.0
    action_lon = 4.0
    target_lat, target_lon = _offset_point(action_lat, action_lon, 0.0, 10_000.0)
    zone = _point_zone("lz-north", lat=target_lat, lon=target_lon)

    straight_result = compute_divert_estimate(
        action_lat=action_lat,
        action_lon=action_lon,
        action_at_timeline_index=0,
        target_zone_id="lz-north",
        landing_zones=[zone],
        energy=_energy(),
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )
    dubins_result = compute_divert_estimate(
        action_lat=action_lat,
        action_lon=action_lon,
        action_at_timeline_index=0,
        target_zone_id="lz-north",
        landing_zones=[zone],
        energy=_energy(),
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=0.0,
    )

    assert dubins_result.distance_m == pytest.approx(
        straight_result.distance_m, rel=0.01
    )


# ---------------------------------------------------------------------------
# Integration: Dubins heading passed via run_scenario
# ---------------------------------------------------------------------------


def test_scenario_divert_at_route_item_uses_entry_heading() -> None:
    """Lost-link at a non-start waypoint: divert uses Dubins path (distance >= straight)."""
    from bvlos_sim.estimator.execution.scenario import run_scenario
    from bvlos_sim.schemas.scenario import ScenarioPlan

    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    scenario = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "dubins-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                "lost_link_policy": {
                    "action": "divert",
                    "loiter_s": 0.0,
                    "divert_target_id": "lz-near",
                },
            },
            "events": [
                {
                    "event_id": "link-lost",
                    "kind": "lost_link",
                    "trigger": "at_route_item",
                    "trigger_route_item_id": "wp1",
                }
            ],
            "assertions": [],
        }
    )

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])

    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.policy_outcome is not None
    divert = outcome.policy_outcome.divert_estimate
    assert divert is not None
    assert divert.distance_m > 0.0
    # Time and energy remain consistently computed from distance
    assert math.isclose(
        divert.time_s,
        divert.distance_m / mission.defaults.cruise_speed_mps,
        rel_tol=1e-6,
    )


def test_scenario_divert_at_mission_start_no_heading_available() -> None:
    """At mission start, no prior leg exists — falls back to straight-line distance."""
    from bvlos_sim.estimator.execution.scenario import run_scenario
    from bvlos_sim.schemas.scenario import ScenarioPlan

    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    scenario = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "dubins-start-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                "lost_link_policy": {
                    "action": "divert",
                    "loiter_s": 0.0,
                    "divert_target_id": "lz-near",
                },
            },
            "events": [
                {
                    "event_id": "link-lost",
                    "kind": "lost_link",
                    "trigger": "at_mission_start",
                }
            ],
            "assertions": [],
        }
    )

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])
    outcome = result.event_outcomes[0]
    divert = outcome.policy_outcome.divert_estimate
    assert divert is not None
    assert divert.distance_m > 0.0
    # At mission start, no heading available — Dubins not applied, straight-line used
    # (distance_m still positive, just straight-line geodesic)
