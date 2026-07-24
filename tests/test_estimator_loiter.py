import pytest

from bvlos_sim.estimator import (
    EstimationOptions,
    FailureCode,
    SpeedSource,
    WarningCode,
    estimate_mission_distance_time,
)
from bvlos_sim.estimator.core.errors import (
    EstimatorInfeasibleError,
    UnsupportedEstimatorFeatureError,
)
from bvlos_sim.schemas import VehicleClass
from tests.helpers import make_fw_vehicle, make_mission, make_vehicle


def test_loiter_dwell_populates_wind_speed_and_null_track_components() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    result = estimate_mission_distance_time(mission, make_vehicle())

    assert len(result.legs) == 2
    dwell = result.legs[1]
    assert dwell.phase == "loiter_dwell"
    assert dwell.wind_east_mps is not None
    assert dwell.wind_north_mps is not None
    assert dwell.wind_speed_mps is not None
    assert dwell.wind_along_track_mps is None
    assert dwell.wind_cross_track_mps is None
    assert dwell.path_distance_m == 0.0
    assert dwell.speed_source == SpeedSource.STATION_KEEP_AUTHORITY


def test_loiter_fallback_to_hover_speed_emits_warning() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()
    vehicle.performance.max_station_keep_wind_mps = None
    vehicle.performance.hover_speed_mps = 6.0

    result = estimate_mission_distance_time(mission, vehicle)
    warning_codes = {warning.code for warning in result.warnings}

    assert WarningCode.HOVER_SPEED_USED_AS_STATION_KEEP_AUTHORITY in warning_codes
    assert WarningCode.LOITER_ASSUMED_ZERO_GROUND_DISTANCE in warning_codes


def test_loiter_fails_when_wind_exceeds_station_keep_authority() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()
    vehicle.performance.max_station_keep_wind_mps = 6.0

    with pytest.raises(EstimatorInfeasibleError) as exc_info:
        estimate_mission_distance_time(
            mission,
            vehicle,
            options=EstimationOptions(wind_east_mps=7.0, wind_north_mps=0.0),
        )

    assert exc_info.value.failure.code == FailureCode.STATION_KEEP_INFEASIBLE_WIND


def test_loiter_fallback_authority_equals_hover_speed_mps() -> None:
    """When max_station_keep_wind_mps is absent, hover_speed_mps is the authority.

    A wind just above hover_speed_mps must trigger STATION_KEEP_INFEASIBLE_WIND,
    proving that the fallback value used is exactly hover_speed_mps, not some default.
    """
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()
    vehicle.performance.max_station_keep_wind_mps = None
    vehicle.performance.hover_speed_mps = 6.0

    with pytest.raises(EstimatorInfeasibleError) as exc_info:
        estimate_mission_distance_time(
            mission,
            vehicle,
            options=EstimationOptions(wind_east_mps=6.5, wind_north_mps=0.0),
        )

    assert exc_info.value.failure.code == FailureCode.STATION_KEEP_INFEASIBLE_WIND


def test_fw_circular_loiter_path_distance_equals_tas_times_time() -> None:
    """Fixed-wing circular loiter path_distance_m should equal TAS × loiter_time_s."""
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_fw_vehicle()
    vehicle.performance.turn_radius_m = 80.0

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(fidelity="v2"),
    )

    loiter_legs = [leg for leg in result.legs if leg.phase == "loiter_dwell"]
    assert len(loiter_legs) == 1
    dwell = loiter_legs[0]
    expected_path_m = vehicle.performance.cruise_speed_mps * 60.0
    assert abs(dwell.path_distance_m - expected_path_m) < 0.01


def test_fw_circular_loiter_time_matches_loiter_time_s() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_fw_vehicle()
    vehicle.performance.turn_radius_m = 80.0

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(fidelity="v2"),
    )

    loiter_legs = [leg for leg in result.legs if leg.phase == "loiter_dwell"]
    assert loiter_legs[0].time_s == 60.0


def test_fw_circular_loiter_start_equals_end_position() -> None:
    """Circular loiter starts and ends at the same position (zero ground translation)."""
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_fw_vehicle()
    vehicle.performance.turn_radius_m = 80.0

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(fidelity="v2"),
    )

    loiter_legs = [leg for leg in result.legs if leg.phase == "loiter_dwell"]
    dwell = loiter_legs[0]
    assert dwell.start_lat == dwell.end_lat
    assert dwell.start_lon == dwell.end_lon


def test_fixed_wing_loiter_time_is_rejected() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()
    vehicle.vehicle_class = VehicleClass.FIXED_WING
    vehicle.capabilities.hover = False
    vehicle.capabilities.forward_flight = True

    with pytest.raises(UnsupportedEstimatorFeatureError) as exc_info:
        estimate_mission_distance_time(mission, vehicle)

    assert (
        exc_info.value.failure.code == FailureCode.UNSUPPORTED_LOITER_FOR_VEHICLE_CLASS
    )


def test_fw_circular_loiter_radius_ignored_warning_emitted() -> None:
    """LOITER_RADIUS_IGNORED warning is emitted when loiter_radius_m is set on a FW loiter."""
    mission = make_mission()
    loiter_item = mission.route[2].model_copy(update={"loiter_radius_m": 50.0})
    mission.route = [loiter_item]
    vehicle = make_fw_vehicle()
    vehicle.performance.turn_radius_m = 80.0

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(fidelity="v2"),
    )

    codes = {w.code for w in result.warnings}
    assert WarningCode.LOITER_RADIUS_IGNORED in codes


def test_hover_loiter_radius_ignored_warning_emitted() -> None:
    """LOITER_RADIUS_IGNORED warning is emitted on a hover dwell when loiter_radius_m is set."""
    mission = make_mission()
    loiter_item = mission.route[2].model_copy(update={"loiter_radius_m": 30.0})
    mission.route = [loiter_item]
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.LOITER_RADIUS_IGNORED in codes
