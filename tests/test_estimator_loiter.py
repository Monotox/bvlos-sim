import pytest

from estimator import EstimationOptions
from estimator import FailureCode
from estimator import SpeedSource
from estimator import WarningCode
from estimator import estimate_mission_distance_time
from estimator.core.errors import EstimatorInfeasibleError
from estimator.core.errors import UnsupportedEstimatorFeatureError
from schemas import VehicleClass
from tests.helpers import make_mission
from tests.helpers import make_vehicle


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


def test_fixed_wing_loiter_time_is_rejected() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()
    vehicle.vehicle_class = VehicleClass.FIXED_WING
    vehicle.capabilities.hover = False
    vehicle.capabilities.forward_flight = True

    with pytest.raises(UnsupportedEstimatorFeatureError) as exc_info:
        estimate_mission_distance_time(mission, vehicle)

    assert exc_info.value.failure.code == FailureCode.UNSUPPORTED_LOITER_FOR_VEHICLE_CLASS
