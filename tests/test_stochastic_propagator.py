"""Tests for stochastic state propagation (Ticket 047, 065)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from bvlos_sim.adapters.io import load_mission, load_vehicle
from bvlos_sim.estimator import LandingZone
from bvlos_sim.estimator.core.enums import EstimateStatus
from bvlos_sim.estimator.execution.propagator import run_stochastic_propagation
from bvlos_sim.estimator.execution.propagation.curves import PositionInterpolator
from bvlos_sim.estimator.execution.propagation.timeline import _geographic_mean
from bvlos_sim.schemas.stochastic import StochasticPropagationPlan
from bvlos_sim.schemas.uncertainty import (
    NormalDistribution,
    UncertaintyParameters,
    UniformDistribution,
)

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
    wind_process_noise_std_mps: float = 0.0,
    parameters: UncertaintyParameters | None = None,
) -> StochasticPropagationPlan:
    return StochasticPropagationPlan(
        schema_version="stochastic.v2",
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
                battery_capacity_wh=UniformDistribution(
                    kind="uniform", low=180.0, high=340.0
                )
            )
        ),
    )


def test_single_sample_zero_noise_matches_deterministic_baseline() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(
        samples=1,
        seed=0,
        parameters=UncertaintyParameters(
            wind_east_mps=NormalDistribution(kind="normal", mean=0.0, std=0.001),
        ),
    )

    result = run_stochastic_propagation(plan, mission, vehicle)

    assert result.baseline.energy is not None
    baseline_reserve = result.baseline.energy.reserve_at_landing_wh
    final_reserve = result.timeline[-1].energy_remaining_wh.mean
    assert abs(final_reserve - baseline_reserve) / baseline_reserve < 0.01


def test_conditional_reserve_violation_is_non_decreasing() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(
        _plan(samples=50, seed=7, dt_s=5.0), mission, vehicle
    )

    probabilities = [
        point.conditional_reserve_violation_rate for point in result.timeline
    ]

    assert all(
        current <= following
        for current, following in zip(probabilities, probabilities[1:])
    )


def test_modeled_pass_rate_uses_all_evaluated_samples() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(_plan(samples=30, seed=3), mission, vehicle)

    evaluated = result.sample_count + result.infeasible_sample_count
    assert result.modeled_constraint_pass_rate == pytest.approx(
        result.sample_count / evaluated
    )


def test_same_seed_produces_identical_results() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(samples=30, seed=11)

    first = run_stochastic_propagation(plan, mission, vehicle)
    second = run_stochastic_propagation(plan, mission, vehicle)

    assert first.timeline == second.timeline


def test_each_sample_uses_its_own_route_timing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bvlos_sim.estimator import try_estimate_mission_distance_time

    mission, vehicle = _mission_vehicle()
    baseline = try_estimate_mission_distance_time(mission, vehicle)
    fast_legs = [
        leg.model_copy(update={"time_s": leg.time_s * 0.5}) for leg in baseline.legs
    ]
    slow_legs = [
        leg.model_copy(update={"time_s": leg.time_s * 1.5}) for leg in baseline.legs
    ]
    fast = baseline.model_copy(
        update={"legs": fast_legs, "total_time_s": baseline.total_time_s * 0.5}
    )
    slow = baseline.model_copy(
        update={"legs": slow_legs, "total_time_s": baseline.total_time_s * 1.5}
    )
    results = iter([baseline, fast, slow])
    monkeypatch.setattr(
        "bvlos_sim.estimator.execution.propagation.sampling.try_estimate_mission_distance_time",
        lambda *_args, **_kwargs: next(results),
    )
    sample_time_s = baseline.total_time_s * 0.75

    result = run_stochastic_propagation(
        _plan(samples=2, seed=1, dt_s=sample_time_s), mission, vehicle
    )

    expected = _geographic_mean(
        [
            PositionInterpolator(fast_legs, 0.0, 0.0).at(sample_time_s),
            PositionInterpolator(slow_legs, 0.0, 0.0).at(sample_time_s),
        ]
    )
    point = result.timeline[1]
    assert point.route_position_centroid_lat_deg == pytest.approx(expected[0])
    assert point.route_position_centroid_lon_deg == pytest.approx(expected[1])


def test_process_wind_noise_is_rejected() -> None:
    with pytest.raises(ValidationError, match="wind_process_noise_std_mps"):
        _plan(samples=20, seed=19, wind_process_noise_std_mps=1.5)


def test_unbounded_normal_is_rejected_for_positive_physical_parameter() -> None:
    with pytest.raises(ValidationError, match="bounded positive uniform"):
        _plan(
            samples=20,
            seed=19,
            parameters=UncertaintyParameters(
                battery_capacity_wh=NormalDistribution(
                    kind="normal", mean=260.0, std=80.0
                )
            ),
        )


def test_different_seeds_produce_different_timelines() -> None:
    mission, vehicle = _mission_vehicle()

    first = run_stochastic_propagation(_plan(samples=50, seed=1), mission, vehicle)
    second = run_stochastic_propagation(_plan(samples=50, seed=2), mission, vehicle)

    assert any(
        left.energy_remaining_wh.mean != right.energy_remaining_wh.mean
        for left, right in zip(first.timeline, second.timeline)
    )


def test_result_fields_populated() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(_plan(samples=20, seed=5), mission, vehicle)

    assert result.reserve_at_mission_end_wh is not None
    assert result.analysis_scope == "diagnostic_open_loop_parameter_sweep"
    assert result.operational_feasibility_assessed is False
    assert result.modeled_constraint_pass_rate is not None
    assert 0.0 <= result.modeled_constraint_pass_rate <= 1.0
    assert len(result.timeline) >= 1
    assert all(
        0.0 <= point.conditional_reserve_violation_rate <= 1.0
        for point in result.timeline
    )


def test_success_infeasible_and_failed_counts_equal_requested() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(samples=10, seed=7)
    result = run_stochastic_propagation(plan, mission, vehicle)

    assert (
        result.sample_count
        + result.infeasible_sample_count
        + result.failed_sample_count
        == plan.samples
    )


def test_failed_sample_count_is_zero_for_healthy_plan() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(_plan(samples=10, seed=42), mission, vehicle)

    assert result.failed_sample_count == 0
    assert result.sample_count == 10


def test_nonspatial_infeasible_samples_count_against_feasibility() -> None:
    mission, vehicle = _mission_vehicle()
    plan = _plan(
        samples=6,
        seed=2,
        wind_process_noise_std_mps=0.0,
        parameters=UncertaintyParameters(
            wind_east_mps=NormalDistribution(kind="normal", mean=100.0, std=0.001),
        ),
    )

    result = run_stochastic_propagation(plan, mission, vehicle)

    assert result.sample_count == 0
    assert result.infeasible_sample_count == 6
    assert result.spatial_infeasible_count == 0
    assert result.failed_sample_count == 0
    assert result.modeled_constraint_pass_rate == 0.0


def test_error_samples_remain_failed_and_outside_completed_denominator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bvlos_sim.estimator import try_estimate_mission_distance_time

    mission, vehicle = _mission_vehicle()
    baseline = try_estimate_mission_distance_time(mission, vehicle)
    error = baseline.model_copy(update={"status": EstimateStatus.ERROR, "energy": None})
    results = iter([baseline, error, error, error, error])
    monkeypatch.setattr(
        "bvlos_sim.estimator.execution.propagation.sampling.try_estimate_mission_distance_time",
        lambda *_args, **_kwargs: next(results),
    )
    plan = _plan(samples=4, seed=2, wind_process_noise_std_mps=0.0)

    result = run_stochastic_propagation(plan, mission, vehicle)

    assert result.sample_count == 0
    assert result.infeasible_sample_count == 0
    assert result.failed_sample_count == 4
    assert result.modeled_constraint_pass_rate is None


def test_infeasible_baseline_raises_value_error() -> None:
    mission, vehicle = _mission_vehicle()
    # Remove energy model so baseline estimation fails before energy evaluation.
    vehicle_no_energy = vehicle.model_copy(update={"energy": None})

    with pytest.raises(ValueError, match="feasible baseline"):
        run_stochastic_propagation(_plan(samples=5, seed=1), mission, vehicle_no_energy)


# --- Geofence/LZ outcomes in the modeled constraint pass rate ---


def _far_landing_zone() -> LandingZone:
    """A landing zone ~5 km north of home; 100 Wh samples can't afford the divert reserve."""
    return LandingZone.model_validate(
        {
            "id": "far_lz",
            "altitude_amsl_m": 12.0,
            "geometry": {"points": [{"lat": 52.045, "lon": 4.0}]},
        }
    )


def _plan_low_battery(*, samples: int, seed: int) -> StochasticPropagationPlan:
    """Plan that samples battery at 100 Wh.

    Route energy ≈ 41.5 Wh; at RTL state remaining ≈ 58.5 Wh, reserve = 25 Wh,
    so divert budget ≈ 33.5 Wh < divert to far LZ (~34.8 Wh) → LZ infeasible.
    """
    return StochasticPropagationPlan(
        schema_version="stochastic.v2",
        propagation_id="test-spatial-infeasible",
        mission_file=str(MISSION_PATH),
        vehicle_file=str(VEHICLE_PATH),
        dt_s=2.0,
        samples=samples,
        seed=seed,
        wind_process_noise_std_mps=0.0,
        parameters=UncertaintyParameters(
            battery_capacity_wh=UniformDistribution(
                kind="uniform", low=99.9, high=100.1
            ),
        ),
    )


def _mission_with_lax_distance_constraint():
    """Mission with min_distance_to_landing_zone_m = 7000 so the far LZ passes distance check."""
    mission, _ = load_mission(MISSION_PATH)
    new_constraints = mission.constraints.model_copy(
        update={"min_distance_to_landing_zone_m": 7000.0}
    )
    return mission.model_copy(update={"constraints": new_constraints})


def test_spatial_infeasible_count_is_zero_without_landing_zones() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(_plan(samples=10, seed=42), mission, vehicle)

    assert result.spatial_infeasible_count == 0


def test_sampled_battery_uses_its_own_reserve_threshold() -> None:
    mission, vehicle = _mission_vehicle()
    result = run_stochastic_propagation(
        _plan_low_battery(samples=6, seed=7),
        mission,
        vehicle,
    )

    assert result.sample_count == 6
    assert result.modeled_constraint_pass_rate == pytest.approx(1.0)
    assert result.timeline[-1].conditional_reserve_violation_rate == pytest.approx(0.0)


def test_lz_infeasible_on_low_battery_sample_increments_spatial_count() -> None:
    """Samples with 50 Wh battery cannot afford the divert — counted as spatial infeasible."""
    mission = _mission_with_lax_distance_constraint()
    _, vehicle = _mission_vehicle()
    lz = _far_landing_zone()
    plan = _plan_low_battery(samples=6, seed=7)

    result = run_stochastic_propagation(plan, mission, vehicle, landing_zones=[lz])

    assert result.spatial_infeasible_count == 6
    assert result.infeasible_sample_count == 6
    assert result.sample_count == 0
    assert result.modeled_constraint_pass_rate == 0.0


def test_three_way_accounting_holds_with_spatial_infeasible() -> None:
    """Successful + infeasible + failed equals every requested sample."""
    mission = _mission_with_lax_distance_constraint()
    _, vehicle = _mission_vehicle()
    lz = _far_landing_zone()
    plan = _plan_low_battery(samples=5, seed=3)

    result = run_stochastic_propagation(plan, mission, vehicle, landing_zones=[lz])

    assert (
        result.sample_count
        + result.infeasible_sample_count
        + result.failed_sample_count
        == plan.samples
    )
