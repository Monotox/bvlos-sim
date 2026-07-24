import math

from bvlos_sim.estimator import (
    EstimationOptions,
    EstimateStatus,
    FailureCode,
    FidelityMode,
    LegPhase,
    WindVector,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from bvlos_sim.estimator.core.results import LegEstimate
from bvlos_sim.schemas import AltitudeReference, MissionEstimation
from tests.helpers import make_mission, make_vehicle


def test_internal_leg_path_geometry_is_not_part_of_the_public_contract() -> None:
    assert "path_coordinates" not in LegEstimate.model_fields
    assert "path_coordinates" not in LegEstimate.model_json_schema()["properties"]


def test_leg_provenance_tracks_expanded_route_items() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    result = estimate_mission_distance_time(mission, make_vehicle())

    assert [leg.leg_index for leg in result.legs] == [0, 1]
    assert [leg.route_item_index for leg in result.legs] == [0, 0]


def test_mission_estimation_values_are_used_when_runtime_options_are_absent() -> None:
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.lat = mission.planned_home.lat
    waypoint.lon = 4.01
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [waypoint]
    mission.estimation = MissionEstimation(
        wind_east_mps=-5.0,
        wind_north_mps=0.0,
        min_groundspeed_mps=4.0,
    )

    result = estimate_mission_distance_time(mission, make_vehicle())
    leg = result.legs[0]

    assert result.metadata["options_source"] == "mission_estimation"
    assert leg.wind_east_mps == -5.0


def test_runtime_options_override_mission_estimation_values() -> None:
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.lat = mission.planned_home.lat
    waypoint.lon = 4.01
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [waypoint]
    mission.estimation = MissionEstimation(
        wind_east_mps=-5.0,
        wind_north_mps=0.0,
        min_groundspeed_mps=4.0,
    )

    mission_only = estimate_mission_distance_time(mission, make_vehicle())
    overridden = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(
            wind_east_mps=5.0,
            wind_north_mps=0.0,
            min_groundspeed_mps=6.0,
        ),
    )

    assert overridden.metadata["options_source"] == "runtime_options"
    assert overridden.legs[0].wind_east_mps == 5.0
    assert overridden.total_time_s < mission_only.total_time_s


def test_partial_runtime_options_preserve_mission_wind_layers() -> None:
    mission = make_mission()
    mission.estimation = MissionEstimation.model_validate(
        {
            "wind_layers": [
                {"altitude_m": 0.0, "wind_east_mps": 5.0, "wind_north_mps": 0.0},
            ]
        }
    )

    result = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(fidelity=FidelityMode.V2),
    )

    assert result.metadata["options_source"] == "runtime_options"
    assert result.metadata["wind_provider_id"] == "layered"
    assert any(leg.wind_east_mps == 5.0 for leg in result.legs)
    assert "mission_wind_layers_ignored" not in result.metadata


def test_fidelity_only_runtime_option_cannot_erase_infeasible_mission_wind() -> None:
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.lat = mission.planned_home.lat
    waypoint.lon = mission.planned_home.lon + 0.01
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [waypoint]
    mission.estimation = MissionEstimation.model_validate(
        {
            "wind_layers": [
                {"altitude_m": 0.0, "wind_east_mps": 0.0, "wind_north_mps": 30.0}
            ]
        }
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=EstimationOptions(fidelity=FidelityMode.V2),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.WIND_TRIANGLE_NO_SOLUTION


def test_capabilities_are_derived_from_vehicle_class_when_omitted() -> None:
    mission = make_mission()
    mission.route = [mission.route[2]]
    vehicle = make_vehicle()
    vehicle.capabilities = None

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.metadata["capabilities_source"] == "derived_from_vehicle_class"
    assert result.legs[-1].phase == LegPhase.LOITER_DWELL


def test_default_wind_provider_metadata_uses_stable_identifier() -> None:
    result = estimate_mission_distance_time(make_mission(), make_vehicle())

    assert result.metadata["wind_provider_id"] == "constant"


def test_custom_wind_provider_metadata_uses_generic_identifier() -> None:
    class TestWindProvider:
        def wind_at(
            self,
            lat: float,
            lon: float,
            altitude_amsl_m: float,
            elapsed_time_s: float,
        ) -> WindVector:
            return WindVector(wind_east_mps=0.0, wind_north_mps=0.0)

    result = estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        wind_provider=TestWindProvider(),
    )

    assert result.metadata["wind_provider_id"] == "custom"


def test_totals_match_the_sum_of_returned_legs() -> None:
    mission = make_mission()
    first = mission.route[1]
    first.altitude_reference = AltitudeReference.AMSL
    first.altitude_m = 100.0

    second = mission.route[1].model_copy(deep=True)
    second.id = "wp2"
    second.lat = 52.002
    second.lon = 4.003
    second.altitude_reference = AltitudeReference.AMSL
    second.altitude_m = 50.0

    mission.route = [first, second]
    result = estimate_mission_distance_time(mission, make_vehicle())

    assert result.totals_are_partial is False
    assert math.isclose(
        result.total_horizontal_distance_m,
        sum(leg.horizontal_distance_m for leg in result.legs),
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.total_vertical_distance_m,
        sum(leg.vertical_distance_m for leg in result.legs),
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.total_path_distance_m,
        sum(leg.path_distance_m for leg in result.legs),
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.total_time_s,
        sum(leg.time_s for leg in result.legs),
        rel_tol=1e-9,
    )
