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
        vehicle.energy.battery_capacity_wh * result.energy.reserve_threshold_percent / 100.0,
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


def test_missing_phase_energy_model_fails_after_kinematics_are_complete() -> None:
    vehicle = make_vehicle()
    setattr(vehicle.energy, "hover_power_w", None)

    with pytest.raises(InvalidEstimatorInputError) as exc_info:
        estimate_mission_distance_time(make_mission(), vehicle)

    error = exc_info.value
    assert error.failure.code == FailureCode.MISSING_ENERGY_MODEL
    assert error.failure.leg_index is not None
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
