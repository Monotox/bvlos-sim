import math

import pytest

from estimator import (
    EstimationOptions,
    FailureCode,
    WarningCode,
    estimate_mission_distance_time,
)
from estimator.core.errors import UnsupportedEstimatorFeatureError
from schemas import AltitudeReference
from tests.helpers import make_mission, make_vehicle


def test_tailwind_shortens_time_vs_headwind() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.altitude_reference = AltitudeReference.AMSL
    wp.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [wp]
    mission.defaults.cruise_speed_mps = 20.0

    tail = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(wind_east_mps=5.0, wind_north_mps=0.0),
    )
    head = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(wind_east_mps=-5.0, wind_north_mps=0.0),
    )

    assert tail.total_time_s < head.total_time_s


def test_crosswind_reduces_along_track_speed() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = 52.01
    wp.lon = 4.0
    mission.route = [wp]
    mission.defaults.cruise_speed_mps = 20.0

    calm = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(wind_east_mps=0.0, wind_north_mps=0.0),
    )
    cross = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(wind_east_mps=8.0, wind_north_mps=0.0),
    )

    calm_leg = calm.legs[0]
    cross_leg = cross.legs[0]
    assert calm_leg.groundspeed_mps is not None
    assert cross_leg.groundspeed_mps is not None
    assert cross_leg.groundspeed_mps < calm_leg.groundspeed_mps


def test_rtl_returns_to_home_coordinates_and_altitude() -> None:
    mission = make_mission()
    mission.route = [mission.route[1], mission.route[3]]
    result = estimate_mission_distance_time(mission, make_vehicle())

    rtl_leg = result.legs[-1]
    assert math.isclose(rtl_leg.end_lat, mission.planned_home.lat, rel_tol=1e-9)
    assert math.isclose(rtl_leg.end_lon, mission.planned_home.lon, rel_tol=1e-9)
    assert math.isclose(
        rtl_leg.end_alt_amsl_m,
        mission.planned_home.altitude_amsl_m,
        rel_tol=1e-9,
    )


def test_climb_time_can_dominate_leg_time() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = 52.00001
    wp.lon = 4.00001
    wp.altitude_m = 200.0
    mission.route = [wp]
    mission.defaults.cruise_speed_mps = 30.0
    vehicle = make_vehicle()
    vehicle.performance.climb_rate_mps = 1.0

    result = estimate_mission_distance_time(mission, vehicle)
    leg = result.legs[0]
    expected_vertical = abs(leg.vertical_delta_m) / vehicle.performance.climb_rate_mps
    assert math.isclose(leg.time_s, expected_vertical, rel_tol=1e-9)


def test_zero_horizontal_vertical_only_leg_skips_wind_triangle_fields() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = mission.planned_home.lat
    wp.lon = mission.planned_home.lon
    wp.altitude_m = 220.0
    mission.route = [wp]

    result = estimate_mission_distance_time(mission, make_vehicle())
    leg = result.legs[0]

    assert leg.horizontal_distance_m == 0.0
    assert leg.path_distance_m == leg.vertical_distance_m
    assert leg.tas_mps is None
    assert leg.groundspeed_mps is None
    assert leg.ground_track_deg is None
    assert leg.required_heading_deg is None
    assert leg.crab_angle_deg is None
    assert leg.wind_east_mps is None
    assert leg.wind_north_mps is None
    assert leg.wind_speed_mps is None
    assert leg.wind_along_track_mps is None
    assert leg.wind_cross_track_mps is None


def test_low_groundspeed_margin_warning_is_emitted_before_infeasible() -> None:
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.lat = mission.planned_home.lat
    waypoint.lon = 4.01
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [waypoint]
    mission.defaults.cruise_speed_mps = 20.0
    mission.constraints.max_wind_mps = None

    vehicle = make_vehicle()
    vehicle.performance.max_crab_angle_deg = 89.0
    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(
            wind_east_mps=-15.8,
            wind_north_mps=0.0,
            min_groundspeed_mps=4.0,
        ),
    )

    assert result.legs[0].groundspeed_mps is not None
    assert result.legs[0].groundspeed_mps > 4.0
    assert WarningCode.LOW_GROUNDSPEED_MARGIN in result.legs[0].warnings


def test_high_crab_margin_warning_is_emitted_before_limit() -> None:
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.lat = 52.01
    waypoint.lon = mission.planned_home.lon
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [waypoint]
    mission.defaults.cruise_speed_mps = 20.0
    mission.constraints.max_wind_mps = None

    result = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(wind_east_mps=11.0, wind_north_mps=0.0),
    )

    assert WarningCode.HIGH_CRAB_MARGIN in result.legs[0].warnings


def test_terrain_altitude_reference_is_unsupported() -> None:
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.altitude_reference = AltitudeReference.TERRAIN
    mission.route = [waypoint]

    with pytest.raises(UnsupportedEstimatorFeatureError) as exc_info:
        estimate_mission_distance_time(mission, make_vehicle())

    assert (
        exc_info.value.failure.code
        == FailureCode.UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN
    )
