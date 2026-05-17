import pytest

from estimator import (
    EstimateStatus,
    FailureCode,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.core.errors import EstimatorError
from schemas import AltitudeReference
from tests.helpers import make_mission, make_vehicle


def test_tas_non_positive_fails_with_invalid_speed_profile() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    mission.defaults.cruise_speed_mps = None
    vehicle = make_vehicle()
    vehicle.performance.cruise_speed_mps = 0.0

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, vehicle)

    assert exc_info.value.failure.code == FailureCode.INVALID_SPEED_PROFILE


def test_missing_tas_fails_with_missing_required_speed_profile() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    mission.defaults.cruise_speed_mps = None
    vehicle = make_vehicle()
    vehicle.performance = vehicle.performance.model_copy(
        update={"cruise_speed_mps": None}
    )

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, vehicle)

    assert exc_info.value.failure.code == FailureCode.MISSING_REQUIRED_SPEED_PROFILE


def test_climb_rate_required_only_when_climbing() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.altitude_m = 200.0
    mission.route = [wp]
    vehicle = make_vehicle()
    vehicle.performance = vehicle.performance.model_copy(
        update={"climb_rate_mps": None}
    )

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, vehicle)

    assert exc_info.value.failure.code == FailureCode.MISSING_REQUIRED_SPEED_PROFILE


def test_descent_rate_required_only_when_descending() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.altitude_reference = AltitudeReference.AMSL
    wp.altitude_m = 1.0
    mission.route = [wp]
    vehicle = make_vehicle()
    vehicle.performance = vehicle.performance.model_copy(
        update={"descent_rate_mps": None}
    )

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, vehicle)

    assert exc_info.value.failure.code == FailureCode.MISSING_REQUIRED_SPEED_PROFILE


def test_flat_transit_does_not_require_climb_or_descent_rates() -> None:
    mission = make_mission()
    wp = mission.route[1]
    wp.altitude_reference = AltitudeReference.AMSL
    wp.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [wp]
    vehicle = make_vehicle()
    vehicle.performance = vehicle.performance.model_copy(
        update={"climb_rate_mps": None, "descent_rate_mps": None}
    )

    result = estimate_mission_distance_time(mission, vehicle)
    assert result.status == EstimateStatus.SUCCESS


def test_negative_loiter_time_fails_with_invalid_mission_profile() -> None:
    mission = make_mission()
    loiter = mission.route[2]
    loiter.loiter_time_s = -1.0
    mission.route = [loiter]

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, make_vehicle())

    assert exc_info.value.failure.code == FailureCode.INVALID_MISSION_PROFILE


def test_partial_coordinate_pair_fails_before_estimation() -> None:
    mission = make_mission()
    takeoff = mission.route[0]
    takeoff.lat = mission.planned_home.lat

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, make_vehicle())

    assert exc_info.value.failure.code == FailureCode.INVALID_MISSION_PROFILE


def test_altitude_reference_without_altitude_fails_before_estimation() -> None:
    mission = make_mission()
    rtl = mission.route[3]
    rtl.altitude_reference = AltitudeReference.AMSL

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, make_vehicle())

    assert exc_info.value.failure.code == FailureCode.INVALID_MISSION_PROFILE


def test_mission_vehicle_profile_mismatch_fails_before_context_build() -> None:
    mission = make_mission()
    mission.vehicle_profile = "different_vehicle"

    with pytest.raises(EstimatorError) as exc_info:
        estimate_mission_distance_time(mission, make_vehicle())

    assert exc_info.value.failure.code == FailureCode.INVALID_MISSION_PROFILE


def test_try_api_failure_before_first_leg_returns_non_partial_zero_totals() -> None:
    mission = make_mission()
    loiter = mission.route[2]
    loiter.loiter_time_s = -1.0
    mission.route = [loiter]

    result = try_estimate_mission_distance_time(mission, make_vehicle())
    assert result.totals_are_partial is False
    assert result.legs == []
    assert result.total_horizontal_distance_m == 0
    assert result.total_vertical_distance_m == 0
    assert result.total_path_distance_m == 0
    assert result.total_time_s == 0


def test_try_api_failure_after_completed_leg_returns_partial_totals() -> None:
    mission = make_mission()
    first = mission.route[1]
    loiter = mission.route[2]
    loiter.loiter_time_s = -1.0
    mission.route = [first, loiter]

    result = try_estimate_mission_distance_time(mission, make_vehicle())
    assert result.totals_are_partial is True
    assert len(result.legs) == 1
    assert result.total_path_distance_m > 0
    assert result.total_time_s > 0


def test_try_api_invalid_input_failure_maps_to_status_error_not_infeasible() -> None:
    """INVALID_INPUT failures must map to status=ERROR, not status=INFEASIBLE."""
    mission = make_mission()
    mission.route = [mission.route[1]]
    mission.defaults.cruise_speed_mps = None
    vehicle = make_vehicle()
    vehicle.performance = vehicle.performance.model_copy(
        update={"cruise_speed_mps": None}
    )

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.MISSING_REQUIRED_SPEED_PROFILE
