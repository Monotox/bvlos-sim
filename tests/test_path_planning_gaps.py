"""Tests for Ticket 039: path-planning model gaps.

Covers:
- Fidelity v2 tangent-point offset subtraction on transit legs adjacent to turn arcs
- 3D slant path distance for vertical-only (takeoff/landing-transit) legs
- Dubins divert planar approximation limit warning
"""

import math

import pytest

from estimator import (
    DivertRouteEstimate,
    EstimationOptions,
    FidelityMode,
    LandingZone,
    LegPhase,
    estimate_mission_distance_time,
)
from estimator.core.enums import WarningCode
from estimator.core.results import EnergyEstimate
from estimator.execution.divert import compute_divert_estimate
from schemas.mission import MissionAction, RouteItem
from tests.helpers import make_mission, make_vehicle


def _v1_options(**kwargs):
    return EstimationOptions(fidelity=FidelityMode.V1, **kwargs)


def _v2_options(**kwargs):
    return EstimationOptions(fidelity=FidelityMode.V2, **kwargs)


def _right_angle_mission():
    """Two waypoints that force a ~90° right turn at wp1."""
    mission = make_mission()
    wp1 = RouteItem(id="north", action=MissionAction.WAYPOINT, lat=52.01, lon=4.0, altitude_m=120.0)
    wp2 = RouteItem(id="east", action=MissionAction.WAYPOINT, lat=52.01, lon=4.02, altitude_m=120.0)
    mission.route = [wp1, wp2]
    return mission


def _point_zone(zone_id: str, *, lat: float, lon: float) -> LandingZone:
    return LandingZone.model_validate(
        {"id": zone_id, "geometry": {"points": [{"lat": lat, "lon": lon}]}}
    )


def _minimal_energy(battery_capacity_wh: float = 900.0) -> EnergyEstimate:
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
# Tangent-point offset — fidelity v2
# ---------------------------------------------------------------------------


def test_v2_transit_leg_before_turn_arc_is_trimmed_by_tangent_offset() -> None:
    """The transit leg that precedes a TURN_ARC must have path_distance_m reduced."""
    mission = _right_angle_mission()
    vehicle = make_vehicle()
    turn_radius_m = vehicle.performance.turn_radius_m
    assert turn_radius_m is not None

    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    legs = result.legs

    for i, leg in enumerate(legs):
        if leg.phase != LegPhase.TURN_ARC:
            continue
        # The leg before the TURN_ARC is the incoming transit leg.
        assert i > 0, "TURN_ARC must have a preceding leg"
        prev = legs[i - 1]
        # The tangent offset for this arc
        arc_angle_rad = leg.path_distance_m / turn_radius_m
        expected_offset = turn_radius_m * math.tan(arc_angle_rad / 2.0)
        # path_distance_m must have been reduced by the offset (clamped to 0)
        assert prev.path_distance_m <= prev.horizontal_distance_m
        assert prev.path_distance_m == pytest.approx(
            max(0.0, prev.horizontal_distance_m - expected_offset), rel=1e-9
        )


def test_v2_transit_leg_after_turn_arc_is_trimmed_by_tangent_offset() -> None:
    """The transit leg that follows a TURN_ARC must have path_distance_m reduced."""
    mission = _right_angle_mission()
    vehicle = make_vehicle()
    turn_radius_m = vehicle.performance.turn_radius_m
    assert turn_radius_m is not None

    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    legs = result.legs

    for i, leg in enumerate(legs):
        if leg.phase != LegPhase.TURN_ARC:
            continue
        assert i + 1 < len(legs), "TURN_ARC must have a following leg"
        nxt = legs[i + 1]
        arc_angle_rad = leg.path_distance_m / turn_radius_m
        expected_offset = turn_radius_m * math.tan(arc_angle_rad / 2.0)
        assert nxt.path_distance_m <= nxt.horizontal_distance_m
        assert nxt.path_distance_m == pytest.approx(
            max(0.0, nxt.horizontal_distance_m - expected_offset), rel=1e-9
        )


def test_v2_total_path_less_than_v1_plus_raw_arc_total() -> None:
    """With tangent offsets removed, v2 total < v1 total + sum of raw arc lengths."""
    mission = _right_angle_mission()
    vehicle = make_vehicle()
    r_v1 = estimate_mission_distance_time(mission, vehicle, options=_v1_options())
    r_v2 = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    arc_total = sum(leg.path_distance_m for leg in r_v2.legs if leg.phase == LegPhase.TURN_ARC)
    assert r_v2.total_path_distance_m < r_v1.total_path_distance_m + arc_total


def test_v2_total_equals_sum_of_all_leg_distances() -> None:
    """total_path_distance_m is always the exact sum of individual leg distances."""
    mission = _right_angle_mission()
    vehicle = make_vehicle()
    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    assert math.isclose(
        result.total_path_distance_m,
        sum(leg.path_distance_m for leg in result.legs),
        rel_tol=1e-12,
    )


def test_v1_transit_path_distance_equals_horizontal_distance() -> None:
    """Fidelity v1 is unchanged: path_distance_m == horizontal_distance_m for transit legs."""
    mission = _right_angle_mission()
    vehicle = make_vehicle()
    result = estimate_mission_distance_time(mission, vehicle, options=_v1_options())
    for leg in result.legs:
        if leg.phase in (LegPhase.TRANSIT, LegPhase.RTL_TRANSIT):
            assert math.isclose(
                leg.path_distance_m, leg.horizontal_distance_m, rel_tol=1e-12
            ), f"v1 leg {leg.phase} path_distance_m != horizontal_distance_m"


def test_v2_no_tangent_offset_without_turn_radius() -> None:
    """Without turn_radius_m, no TURN_ARC is injected and path_distance equals horizontal."""
    mission = _right_angle_mission()
    vehicle = make_vehicle()
    vehicle.performance.turn_radius_m = None

    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    for leg in result.legs:
        assert leg.phase != LegPhase.TURN_ARC
        if leg.phase in (LegPhase.TRANSIT, LegPhase.RTL_TRANSIT):
            assert math.isclose(leg.path_distance_m, leg.horizontal_distance_m, rel_tol=1e-12)


def test_v2_tangent_offset_does_not_make_path_distance_negative() -> None:
    """Even for very sharp turns or short legs, path_distance_m is clamped to 0."""
    mission = make_mission()
    # Very short segment (1 cm north) then sharp turn — offset will exceed segment length
    wp1 = RouteItem(id="near", action=MissionAction.WAYPOINT, lat=52.00001, lon=4.0, altitude_m=120.0)
    wp2 = RouteItem(id="east", action=MissionAction.WAYPOINT, lat=52.00001, lon=4.02, altitude_m=120.0)
    mission.route = [wp1, wp2]

    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    for leg in result.legs:
        assert leg.path_distance_m >= 0.0, f"Negative path_distance_m on {leg.phase}"


# ---------------------------------------------------------------------------
# 3D slant path distance — vertical-only legs
# ---------------------------------------------------------------------------


def test_vertical_only_takeoff_leg_path_distance_equals_vertical_distance() -> None:
    """A purely vertical takeoff leg must report path_distance_m == vertical_distance_m."""
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = mission.planned_home.lat
    wp.lon = mission.planned_home.lon
    wp.altitude_m = 100.0
    mission.route = [wp]

    result = estimate_mission_distance_time(mission, make_vehicle())
    leg = result.legs[0]

    assert leg.horizontal_distance_m == 0.0
    assert leg.vertical_distance_m > 0.0
    assert math.isclose(leg.path_distance_m, leg.vertical_distance_m, rel_tol=1e-12)


def test_vertical_only_leg_path_distance_is_zero_when_no_vertical_change() -> None:
    """A leg with no horizontal or vertical displacement has path_distance_m == 0."""
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = mission.planned_home.lat
    wp.lon = mission.planned_home.lon
    # Same altitude as home (relative_home 0 → AMSL home altitude)
    wp.altitude_m = 0.0
    mission.route = [wp]

    result = estimate_mission_distance_time(mission, make_vehicle())
    leg = result.legs[0]

    assert leg.horizontal_distance_m == 0.0
    assert leg.vertical_distance_m == 0.0
    assert leg.path_distance_m == 0.0


def test_vertical_leg_total_path_distance_includes_slant() -> None:
    """total_path_distance_m accounts for the vertical leg's slant path."""
    mission = make_mission()
    # Vertical-only leg followed by horizontal transit
    wp_up = RouteItem(
        id="up",
        action=MissionAction.WAYPOINT,
        lat=mission.planned_home.lat,
        lon=mission.planned_home.lon,
        altitude_m=80.0,
    )
    wp_across = RouteItem(
        id="across",
        action=MissionAction.WAYPOINT,
        lat=52.01,
        lon=4.0,
        altitude_m=80.0,
    )
    mission.route = [wp_up, wp_across]

    result = estimate_mission_distance_time(mission, make_vehicle())
    vertical_leg = next(leg for leg in result.legs if leg.horizontal_distance_m == 0.0)
    assert vertical_leg.path_distance_m == pytest.approx(vertical_leg.vertical_distance_m)
    assert math.isclose(
        result.total_path_distance_m,
        sum(leg.path_distance_m for leg in result.legs),
        rel_tol=1e-12,
    )


def test_v1_and_v2_agree_on_vertical_leg_slant_path() -> None:
    """3D slant path applies in both v1 and v2 (it is fidelity-independent)."""
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = mission.planned_home.lat
    wp.lon = mission.planned_home.lon
    wp.altitude_m = 60.0
    mission.route = [wp]

    r_v1 = estimate_mission_distance_time(mission, make_vehicle(), options=_v1_options())
    r_v2 = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())

    assert math.isclose(
        r_v1.legs[0].path_distance_m, r_v2.legs[0].path_distance_m, rel_tol=1e-12
    )


# ---------------------------------------------------------------------------
# Dubins divert planar approximation limit warning
# ---------------------------------------------------------------------------


def test_no_planar_warning_for_short_divert() -> None:
    """No warning for a divert route well within the 50 km planar accuracy limit."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    energy = _minimal_energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert isinstance(result, DivertRouteEstimate)
    assert WarningCode.DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT not in result.warnings


def test_planar_warning_emitted_for_long_divert() -> None:
    """DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT is emitted when geodesic divert > 50 km."""
    mission = make_mission()
    vehicle = make_vehicle()
    # Target zone ~60° longitude away — well beyond 50 km at mid-latitudes
    zone = _point_zone("lz-far", lat=52.0, lon=65.0)
    energy = _minimal_energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-far",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert WarningCode.DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT in result.warnings


def test_planar_warning_applies_regardless_of_heading_availability() -> None:
    """Warning is emitted even when falling back to straight-line distance."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-far", lat=52.0, lon=65.0)
    energy = _minimal_energy()

    # No entry heading → straight-line fallback, but warning should still fire
    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-far",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        entry_heading_deg=None,
    )

    assert WarningCode.DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT in result.warnings


def test_divert_warnings_empty_by_default() -> None:
    """DivertRouteEstimate.warnings is an empty list when no warnings apply."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    energy = _minimal_energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.warnings == []
