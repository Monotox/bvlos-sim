"""Tests for fidelity v2: turn-arc dynamics and fixed-wing circular loiter."""

import math

import pytest

from estimator import EstimationOptions
from estimator import FailureCode
from estimator import FidelityMode
from estimator import LegPhase
from estimator import SpeedSource
from estimator import estimate_mission_distance_time
from estimator.core.errors import UnsupportedEstimatorFeatureError
from estimator.math.turn_arc import compute_turn_arc_geometry
from schemas import VehicleClass
from schemas.mission import MissionAction, RouteItem
from tests.helpers import make_mission
from tests.helpers import make_vehicle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fw_vehicle():
    v = make_vehicle()
    v.vehicle_class = VehicleClass.FIXED_WING
    v.capabilities.hover = False
    v.capabilities.forward_flight = True
    return v


def _v2_options(**kwargs):
    return EstimationOptions(fidelity=FidelityMode.V2, **kwargs)


def _v1_options(**kwargs):
    return EstimationOptions(fidelity=FidelityMode.V1, **kwargs)


def _make_turning_mission():
    """Mission with a clear ~90° heading change: home→north, then east."""
    mission = make_mission()
    # wp1 due north, wp2 due east – forces a 90° right turn at wp1
    wp1 = RouteItem(
        id="north",
        action=MissionAction.WAYPOINT,
        lat=52.01,
        lon=4.0,
        altitude_m=120.0,
    )
    wp2 = RouteItem(
        id="east",
        action=MissionAction.WAYPOINT,
        lat=52.01,
        lon=4.02,
        altitude_m=120.0,
    )
    rtl = mission.route[-1]
    mission.route = [wp1, wp2, rtl]
    return mission


# ---------------------------------------------------------------------------
# Turn-arc math
# ---------------------------------------------------------------------------

def test_turn_arc_zero_change_gives_zero_arc_length() -> None:
    arc = compute_turn_arc_geometry(
        incoming_track_deg=45.0,
        outgoing_track_deg=45.0,
        radius_m=100.0,
    )
    assert arc.turn_angle_deg == 0.0
    assert arc.arc_length_m == 0.0


def test_turn_arc_90_degree_turn() -> None:
    arc = compute_turn_arc_geometry(
        incoming_track_deg=0.0,
        outgoing_track_deg=90.0,
        radius_m=100.0,
    )
    assert math.isclose(arc.turn_angle_deg, 90.0, rel_tol=1e-9)
    assert math.isclose(arc.arc_length_m, 100.0 * math.pi / 2, rel_tol=1e-9)


def test_turn_arc_left_and_right_same_magnitude() -> None:
    arc_right = compute_turn_arc_geometry(
        incoming_track_deg=0.0, outgoing_track_deg=45.0, radius_m=80.0
    )
    arc_left = compute_turn_arc_geometry(
        incoming_track_deg=0.0, outgoing_track_deg=315.0, radius_m=80.0
    )
    assert math.isclose(arc_right.arc_length_m, arc_left.arc_length_m, rel_tol=1e-9)


def test_turn_arc_wraps_across_360() -> None:
    # 350° → 10°: only 20° of turn, not 340°
    arc = compute_turn_arc_geometry(
        incoming_track_deg=350.0,
        outgoing_track_deg=10.0,
        radius_m=100.0,
    )
    assert math.isclose(arc.turn_angle_deg, 20.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# v1/v2 fidelity separation – transit
# ---------------------------------------------------------------------------

def test_v1_produces_no_turn_arc_legs() -> None:
    mission = make_mission()
    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v1_options())
    phases = {leg.phase for leg in result.legs}
    assert LegPhase.TURN_ARC not in phases


def test_v2_injects_turn_arc_between_transit_legs() -> None:
    mission = _make_turning_mission()
    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    phases = [leg.phase for leg in result.legs]
    assert LegPhase.TURN_ARC in phases


def test_v2_turn_arc_has_correct_arc_length() -> None:
    """Arc length must equal R · |Δθ| within floating-point tolerance."""
    mission = _make_turning_mission()
    vehicle = make_vehicle()
    turn_radius_m = vehicle.performance.turn_radius_m
    assert turn_radius_m is not None

    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    for leg in result.legs:
        if leg.phase != LegPhase.TURN_ARC:
            continue
        # path_distance = time * tas (re-derive expected arc length from time)
        assert leg.tas_mps is not None
        expected_arc = leg.tas_mps * leg.time_s
        assert math.isclose(leg.path_distance_m, expected_arc, rel_tol=1e-9)
        # Arc must be non-negative and ≤ π·R (≤ 180° turn)
        assert leg.path_distance_m >= 0.0
        assert leg.path_distance_m <= math.pi * turn_radius_m + 1e-9


def test_v2_turn_arc_adds_to_total_path_distance() -> None:
    mission = _make_turning_mission()
    vehicle = make_vehicle()
    r_v1 = estimate_mission_distance_time(mission, vehicle, options=_v1_options())
    r_v2 = estimate_mission_distance_time(mission, vehicle, options=_v2_options())

    arc_total = sum(
        leg.path_distance_m for leg in r_v2.legs if leg.phase == LegPhase.TURN_ARC
    )
    assert arc_total > 0.0
    assert math.isclose(
        r_v2.total_path_distance_m, r_v1.total_path_distance_m + arc_total, rel_tol=1e-9
    )


def test_v2_turn_arc_zero_displacement() -> None:
    mission = _make_turning_mission()
    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    for leg in result.legs:
        if leg.phase != LegPhase.TURN_ARC:
            continue
        assert leg.horizontal_distance_m == 0.0
        assert leg.vertical_delta_m == 0.0
        assert leg.start_lat == leg.end_lat
        assert leg.start_lon == leg.end_lon


def test_v2_turn_arc_ground_track_equals_outgoing_direction() -> None:
    """ground_track_deg on a TURN_ARC must match the next transit's ground_track_deg."""
    mission = _make_turning_mission()
    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    legs = result.legs
    for i, leg in enumerate(legs):
        if leg.phase != LegPhase.TURN_ARC:
            continue
        if i + 1 < len(legs) and legs[i + 1].ground_track_deg is not None:
            assert math.isclose(
                leg.ground_track_deg,
                legs[i + 1].ground_track_deg,
                rel_tol=1e-9,
            )


def test_v2_turn_arc_contributes_to_total_time() -> None:
    mission = _make_turning_mission()
    vehicle = make_vehicle()
    r_v1 = estimate_mission_distance_time(mission, vehicle, options=_v1_options())
    r_v2 = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    assert r_v2.total_time_s > r_v1.total_time_s


def test_v1_and_v2_leg_count_differ_by_turn_arc_count() -> None:
    mission = _make_turning_mission()
    vehicle = make_vehicle()
    r_v1 = estimate_mission_distance_time(mission, vehicle, options=_v1_options())
    r_v2 = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    turn_arc_count = sum(1 for leg in r_v2.legs if leg.phase == LegPhase.TURN_ARC)
    assert turn_arc_count > 0, "test fixture must produce at least one turn"
    assert len(r_v2.legs) == len(r_v1.legs) + turn_arc_count


# ---------------------------------------------------------------------------
# v2 metadata
# ---------------------------------------------------------------------------

def test_v2_metadata_records_estimator_version() -> None:
    mission = make_mission()
    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    assert result.metadata["estimator_version"] == "v2"


def test_v1_metadata_records_estimator_version() -> None:
    mission = make_mission()
    result = estimate_mission_distance_time(mission, make_vehicle())
    assert result.metadata["estimator_version"] == "v1"


# ---------------------------------------------------------------------------
# Fixed-wing circular loiter – v2
# ---------------------------------------------------------------------------

def test_fw_loiter_accepted_in_v2() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]  # loiter_time item
    vehicle = _fw_vehicle()

    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    dwell_legs = [leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL]
    assert len(dwell_legs) == 1


def test_fw_loiter_v1_still_rejected() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = _fw_vehicle()

    with pytest.raises(UnsupportedEstimatorFeatureError) as exc_info:
        estimate_mission_distance_time(mission, vehicle, options=_v1_options())
    assert exc_info.value.failure.code == FailureCode.UNSUPPORTED_LOITER_FOR_VEHICLE_CLASS


def test_fw_circular_loiter_path_distance_equals_tas_times_time() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = _fw_vehicle()
    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())

    dwell = next(leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL)
    assert dwell.tas_mps is not None
    assert math.isclose(
        dwell.path_distance_m, dwell.tas_mps * dwell.time_s, rel_tol=1e-9
    )


def test_fw_circular_loiter_zero_net_displacement() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = _fw_vehicle()
    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())

    dwell = next(leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL)
    assert dwell.horizontal_distance_m == 0.0
    assert dwell.start_lat == dwell.end_lat
    assert dwell.start_lon == dwell.end_lon


def test_fw_circular_loiter_time_equals_loiter_time_s() -> None:
    mission = make_mission()
    loiter_item = mission.route[2]
    loiter_item.loiter_time_s = 90.0
    mission.route = [loiter_item]
    vehicle = _fw_vehicle()
    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())

    dwell = next(leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL)
    assert math.isclose(dwell.time_s, 90.0, rel_tol=1e-9)


def test_fw_circular_loiter_populates_wind_fields() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = _fw_vehicle()
    result = estimate_mission_distance_time(
        mission, vehicle, options=_v2_options(wind_east_mps=3.0)
    )

    dwell = next(leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL)
    assert dwell.wind_east_mps is not None
    assert dwell.wind_north_mps is not None
    assert dwell.wind_speed_mps is not None


def test_fw_circular_loiter_speed_source_is_cruise() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = _fw_vehicle()
    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())

    dwell = next(leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL)
    assert dwell.speed_source in (
        SpeedSource.MISSION_DEFAULT_CRUISE_SPEED,
        SpeedSource.VEHICLE_CRUISE_SPEED,
    )


# ---------------------------------------------------------------------------
# v2 VTOL loiter: hover-capable vehicles still use station-keep
# ---------------------------------------------------------------------------

def test_vtol_loiter_still_uses_station_keep_in_v2() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()  # VTOL with hover=True
    assert vehicle.capabilities.hover

    result = estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    dwell = next(leg for leg in result.legs if leg.phase == LegPhase.LOITER_DWELL)
    # Station-keep: path_distance == 0, speed_source == STATION_KEEP_AUTHORITY
    assert dwell.path_distance_m == 0.0
    assert dwell.speed_source == SpeedSource.STATION_KEEP_AUTHORITY


# ---------------------------------------------------------------------------
# No turn arc after loiter dwell
# ---------------------------------------------------------------------------

def test_no_turn_arc_injected_after_loiter_dwell() -> None:
    """After loiter dwell, last_track_deg is reset so no stale turn arc appears."""
    mission = make_mission()
    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    legs = result.legs
    loiter_dwell_found = any(leg.phase == LegPhase.LOITER_DWELL for leg in legs)
    assert loiter_dwell_found
    for i, leg in enumerate(legs):
        if leg.phase == LegPhase.LOITER_DWELL and i + 1 < len(legs):
            assert legs[i + 1].phase != LegPhase.TURN_ARC


# ---------------------------------------------------------------------------
# Energy model for FW circular loiter (uses cruise power, not hover power)
# ---------------------------------------------------------------------------

def test_fw_circular_loiter_dwell_uses_cruise_power_in_energy() -> None:
    from estimator import EnergyPowerSource, try_estimate_mission_distance_time

    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = _fw_vehicle()
    # Ensure hover_power_w is None (proper FW vehicle has no hover power)
    setattr(vehicle.energy, "hover_power_w", None)

    result = try_estimate_mission_distance_time(mission, vehicle, options=_v2_options())
    assert result.failure is None
    assert result.energy is not None
    dwell_energy = next(
        e for e in result.energy.legs if e.phase == LegPhase.LOITER_DWELL
    )
    assert dwell_energy.power_source == EnergyPowerSource.CRUISE_POWER


# ---------------------------------------------------------------------------
# Straight leg gets no turn arc (collinear waypoints)
# ---------------------------------------------------------------------------

def test_collinear_waypoints_produce_no_turn_arc() -> None:
    """Two waypoints on the same bearing should not inject a TURN_ARC leg."""
    mission = make_mission()
    mission.defaults.cruise_speed_mps = 20.0
    wp = mission.route[1]
    # Place both waypoints due north of home so the bearing is constant ~0°
    wp.lat = 52.01
    wp.lon = 4.0
    from schemas.mission import RouteItem, MissionAction
    wp2 = RouteItem(
        id="wp2",
        action=MissionAction.WAYPOINT,
        lat=52.02,
        lon=4.0,
        altitude_m=120.0,
    )
    mission.route = [wp, wp2]

    result = estimate_mission_distance_time(mission, make_vehicle(), options=_v2_options())
    turn_arcs = [leg for leg in result.legs if leg.phase == LegPhase.TURN_ARC]
    assert len(turn_arcs) == 0
