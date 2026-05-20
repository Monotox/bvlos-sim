"""Tests for stochastic state propagation (Ticket 047)."""

from pathlib import Path

import pytest

from adapters.io import load_mission, load_vehicle
from estimator.execution.propagator import run_stochastic_propagation
from schemas.stochastic import StochasticPropagationPlan
from schemas.uncertainty import NormalDistribution, UncertaintyParameters

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"


def _mission_vehicle():
    mission, _mission_document = load_mission(MISSION_PATH)
    vehicle, _vehicle_document = load_vehicle(VEHICLE_PATH)
    return mission, vehicle


def _plan(
    *,
    samples: int,
    seed: int,
    dt_s: float = 2.0,
    wind_process_noise_std_mps: float = 0.5,
    parameters: UncertaintyParameters | None = None,
) -> StochasticPropagationPlan:
    return StochasticPropagationPlan(
        schema_version="stochastic.v1",
        propagation_id="test-stochastic",
        mission_file=str(MISSION_PATH),
        vehicle_file=str(VEHICLE_PATH),
        dt_s=dt_s,
        samples=samples,
        seed=seed,
        wind_process_noise_std_mps=wind_process_noise_std_mps,
        parameters=(
            parameters
            if parameters is not None
            else UncertaintyParameters(
                battery_capacity_wh=NormalDistribution(
                    kind="normal", mean=260.0, std=80.0
                )
            )
        ),
    )


def test_single_sample_zero_noise_matches_deterministic_baseline() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(
        samples=1,
        seed=0,
        wind_process_noise_std_mps=0.0,
        parameters=UncertaintyParameters(
            wind_east_mps=NormalDistribution(kind="normal", mean=0.0, std=0.001),
        ),
    )

    result = run_stochastic_propagation(plan, mission, vehicle)

    assert result.baseline.energy is not None
    baseline_reserve = result.baseline.energy.reserve_at_landing_wh
    final_reserve = result.timeline[-1].energy_remaining_wh.mean
    assert abs(final_reserve - baseline_reserve) / baseline_reserve < 0.01


def test_p_reserve_violation_is_non_decreasing() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(
        _plan(samples=50, seed=7, dt_s=5.0), mission, vehicle
    )

    probabilities = [point.p_reserve_violation for point in result.timeline]

    assert all(
        current <= following
        for current, following in zip(probabilities, probabilities[1:])
    )


def test_feasibility_rate_matches_final_violation_complement() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(_plan(samples=30, seed=3), mission, vehicle)

    final_violation_rate = result.timeline[-1].p_reserve_violation

    assert result.feasibility_rate == pytest.approx(1 - final_violation_rate, abs=0.02)


def test_same_seed_produces_identical_results() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(samples=30, seed=11)

    first = run_stochastic_propagation(plan, mission, vehicle)
    second = run_stochastic_propagation(plan, mission, vehicle)

    assert first.timeline == second.timeline


def test_different_seeds_produce_different_timelines() -> None:
    mission, vehicle = _mission_vehicle()

    first = run_stochastic_propagation(_plan(samples=50, seed=1), mission, vehicle)
    second = run_stochastic_propagation(_plan(samples=50, seed=2), mission, vehicle)

    assert any(
        left.p_reserve_violation != right.p_reserve_violation
        for left, right in zip(first.timeline, second.timeline)
    )


def test_result_fields_populated() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(_plan(samples=20, seed=5), mission, vehicle)

    assert result.reserve_at_landing_wh is not None
    assert 0.0 <= result.feasibility_rate <= 1.0
    assert len(result.timeline) >= 1
    assert all(0.0 <= point.p_reserve_violation <= 1.0 for point in result.timeline)
