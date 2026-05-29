import math

import pytest

from estimator import (
    EnergyPowerSource,
    EstimateStatus,
    FailureCode,
    InvalidEstimatorInputError,
    LegPhase,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.execution.context_builder import build_estimation_context
from estimator.execution.energy import evaluate_energy_feasibility
from estimator.execution.executors import execute_route_item
from pyproj import Geod
from schemas import MissionAction, RouteItem
from tests.helpers import make_mission, make_vehicle


def test_successful_estimate_includes_energy_breakdown_and_reserve() -> None:
    mission = make_mission()
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert len(result.energy.legs) == len(result.legs)
    assert result.energy.legs[0].power_source == EnergyPowerSource.CLIMB_POWER
    assert any(
        leg.power_source == EnergyPowerSource.HOVER_POWER
        for leg in result.energy.legs
        if leg.phase == LegPhase.LOITER_DWELL
    )
    assert math.isclose(
        result.energy.total_energy_wh,
        sum(leg.energy_wh for leg in result.energy.legs),
        rel_tol=1e-9,
    )
    assert result.energy.reserve_threshold_percent == (
        mission.constraints.min_landing_reserve_percent
    )
    assert math.isclose(
        result.energy.reserve_threshold_wh,
        vehicle.energy.battery_capacity_wh
        * result.energy.reserve_threshold_percent
        / 100.0,
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.energy.usable_energy_wh,
        vehicle.energy.battery_capacity_wh - result.energy.reserve_threshold_wh,
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.energy.reserve_at_landing_wh,
        vehicle.energy.battery_capacity_wh - result.energy.total_energy_wh,
        rel_tol=1e-9,
    )


def test_energy_reserve_below_threshold_returns_complete_infeasible_result() -> None:
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 45.0

    result = try_estimate_mission_distance_time(make_mission(), vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.RESERVE_BELOW_THRESHOLD
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.energy.is_feasible is False
    assert len(result.energy.legs) == len(result.legs)
    assert result.energy.total_energy_wh <= result.energy.battery_capacity_wh
    assert result.energy.reserve_at_landing_wh < result.energy.reserve_threshold_wh


def test_vehicle_reserve_default_is_used_when_mission_has_no_override() -> None:
    mission = make_mission()
    mission.constraints.min_landing_reserve_percent = None
    vehicle = make_vehicle()
    vehicle.energy.reserve_percent_default = 30.0

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.reserve_threshold_percent == 30.0
    assert result.energy.reserve_threshold_wh == 270.0


def test_energy_capacity_exhaustion_returns_insufficient_energy() -> None:
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 30.0

    result = try_estimate_mission_distance_time(make_mission(), vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.INSUFFICIENT_ENERGY
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.energy.total_energy_wh > result.energy.battery_capacity_wh


def test_missing_hover_power_detected_before_per_leg_energy_evaluation() -> None:
    vehicle = make_vehicle()
    vehicle.energy = vehicle.energy.model_copy(update={"hover_power_w": None})

    with pytest.raises(InvalidEstimatorInputError) as exc_info:
        estimate_mission_distance_time(make_mission(), vehicle)

    error = exc_info.value
    assert error.failure.code == FailureCode.MISSING_ENERGY_MODEL
    assert "hover_power_w" in error.failure.message
    assert error.totals_are_partial is False
    assert error.energy is None
    assert len(error.partial_legs) > 0


def test_invalid_energy_policy_fails_after_kinematics_are_complete() -> None:
    mission = make_mission()
    mission.constraints.min_landing_reserve_percent = -1.0

    result = try_estimate_mission_distance_time(mission, make_vehicle())

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.INVALID_ENERGY_POLICY
    assert result.totals_are_partial is False
    assert result.energy is None
    assert len(result.legs) > 0


def test_hover_capable_vehicle_without_hover_power_fails_before_kinematics() -> None:
    vehicle = make_vehicle()
    assert vehicle.capabilities.hover is True
    vehicle.energy = vehicle.energy.model_copy(update={"hover_power_w": None})

    result = try_estimate_mission_distance_time(make_mission(), vehicle)

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.MISSING_ENERGY_MODEL
    assert "hover_power_w" in result.failure.message


def test_rth_reserve_timeline_feasible_for_all_legs() -> None:
    result = estimate_mission_distance_time(make_mission(), make_vehicle())

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    assert len(result.energy.rth_reserve_timeline) == len(result.legs)
    assert result.rth_is_feasible is True
    assert all(point.is_feasible for point in result.energy.rth_reserve_timeline)


def test_rth_distance_from_leg_endpoint_to_home_is_geodesic() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.01,
            altitude_m=120.0,
        )
    ]

    result = estimate_mission_distance_time(mission, make_vehicle())

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    point = result.energy.rth_reserve_timeline[0]
    _, _, expected_distance_m = Geod(ellps="WGS84").inv(
        result.legs[0].end_lon,
        result.legs[0].end_lat,
        mission.planned_home.lon,
        mission.planned_home.lat,
    )
    assert math.isclose(point.rth_distance_m, expected_distance_m, rel_tol=1e-9)


def test_rth_energy_uses_cruise_power_and_tas() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.01,
            altitude_m=120.0,
        )
    ]
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    point = result.energy.rth_reserve_timeline[0]
    expected_energy_wh = (
        vehicle.energy.cruise_power_w
        * (point.rth_distance_m / mission.defaults.cruise_speed_mps)
        / 3600.0
    )
    assert math.isclose(point.rth_energy_wh, expected_energy_wh, rel_tol=1e-9)


def test_rth_reserve_can_fail_at_intermediate_leg_without_landing_failure() -> None:
    mission = make_mission()
    mission.constraints.min_landing_reserve_percent = 25.0
    mission.route = [
        RouteItem(
            id="far",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.05,
            altitude_m=120.0,
        ),
        RouteItem(
            id="near_far",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat + 0.001,
            lon=mission.planned_home.lon + 0.05,
            altitude_m=120.0,
        ),
    ]
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 60.0

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert result.rth_is_feasible is False
    assert result.energy.rth_reserve_timeline is not None
    failed_points = [
        point for point in result.energy.rth_reserve_timeline if not point.is_feasible
    ]
    assert failed_points
    assert failed_points[0].route_item_id == "far"


def test_rth_reserve_short_mission_is_feasible() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="home_hold",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            altitude_m=80.0,
        )
    ]

    result = estimate_mission_distance_time(mission, make_vehicle())

    assert result.rth_is_feasible is True
    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    assert result.energy.rth_reserve_timeline[0].rth_distance_m == 0.0
    assert result.energy.rth_reserve_timeline[0].is_feasible is True


def test_rth_reserve_timeline_is_none_when_home_is_missing() -> None:
    mission = make_mission()
    context = build_estimation_context(mission, make_vehicle())
    for route_item_index, item in enumerate(context.mission.route):
        execute_route_item(context, item, route_item_index=route_item_index)
    context.mission = mission.model_copy(update={"planned_home": None})

    evaluation = evaluate_energy_feasibility(context)

    assert evaluation.failure is None
    assert evaluation.energy is not None
    assert evaluation.energy.rth_reserve_timeline is None
