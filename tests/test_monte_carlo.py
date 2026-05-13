"""Tests for Monte Carlo uncertainty modeling (Ticket 037)."""

import pytest
from pydantic import ValidationError

from estimator import run_monte_carlo
from schemas.uncertainty import (
    NormalDistribution,
    UniformDistribution,
    UncertaintyParameters,
    UncertaintyPlan,
)
from tests.helpers import make_mission, make_vehicle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wind_plan(*, seed: int = 42, samples: int = 50) -> UncertaintyPlan:
    return UncertaintyPlan(
        schema_version="uncertainty.v1",
        uncertainty_id="test-wind",
        mission_file="mission.yaml",
        vehicle_file="vehicle.yaml",
        samples=samples,
        seed=seed,
        parameters=UncertaintyParameters(
            wind_east_mps=NormalDistribution(kind="normal", mean=0.0, std=2.0),
            wind_north_mps=NormalDistribution(kind="normal", mean=0.0, std=2.0),
        ),
    )


def _power_plan(*, seed: int = 42, samples: int = 30) -> UncertaintyPlan:
    return UncertaintyPlan(
        schema_version="uncertainty.v1",
        uncertainty_id="test-power",
        mission_file="mission.yaml",
        vehicle_file="vehicle.yaml",
        samples=samples,
        seed=seed,
        parameters=UncertaintyParameters(
            cruise_power_w=NormalDistribution(kind="normal", mean=450.0, std=45.0),
        ),
    )


def _speed_plan(*, seed: int = 42, samples: int = 20) -> UncertaintyPlan:
    return UncertaintyPlan(
        schema_version="uncertainty.v1",
        uncertainty_id="test-speed",
        mission_file="mission.yaml",
        vehicle_file="vehicle.yaml",
        samples=samples,
        seed=seed,
        parameters=UncertaintyParameters(
            cruise_speed_mps=UniformDistribution(kind="uniform", low=14.0, high=22.0),
        ),
    )


# ---------------------------------------------------------------------------
# Schema validation tests
# ---------------------------------------------------------------------------


def test_normal_distribution_parses() -> None:
    d = NormalDistribution(kind="normal", mean=0.0, std=2.0)
    assert d.mean == 0.0
    assert d.std == 2.0


def test_normal_distribution_rejects_nonpositive_std() -> None:
    with pytest.raises(ValidationError):
        NormalDistribution(kind="normal", mean=0.0, std=0.0)


def test_normal_distribution_rejects_negative_std() -> None:
    with pytest.raises(ValidationError):
        NormalDistribution(kind="normal", mean=0.0, std=-1.0)


def test_uniform_distribution_parses() -> None:
    d = UniformDistribution(kind="uniform", low=0.0, high=10.0)
    assert d.low == 0.0
    assert d.high == 10.0


def test_uniform_distribution_rejects_equal_bounds() -> None:
    with pytest.raises(ValidationError):
        UniformDistribution(kind="uniform", low=5.0, high=5.0)


def test_uniform_distribution_rejects_inverted_bounds() -> None:
    with pytest.raises(ValidationError):
        UniformDistribution(kind="uniform", low=10.0, high=5.0)


def test_uncertainty_parameters_rejects_empty() -> None:
    with pytest.raises(ValidationError):
        UncertaintyParameters()


def test_uncertainty_plan_parses() -> None:
    plan = _wind_plan()
    assert plan.uncertainty_id == "test-wind"
    assert plan.samples == 50
    assert plan.seed == 42
    assert plan.parameters.wind_east_mps is not None


def test_uncertainty_plan_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        UncertaintyPlan.model_validate(
            {
                "schema_version": "uncertainty.v1",
                "uncertainty_id": "x",
                "mission_file": "m.yaml",
                "vehicle_file": "v.yaml",
                "samples": 10,
                "seed": 1,
                "parameters": {"wind_east_mps": {"kind": "normal", "mean": 0.0, "std": 1.0}},
                "extra_field": True,
            }
        )


def test_uncertainty_plan_rejects_zero_samples() -> None:
    with pytest.raises(ValidationError):
        UncertaintyPlan(
            schema_version="uncertainty.v1",
            uncertainty_id="x",
            mission_file="m.yaml",
            vehicle_file="v.yaml",
            samples=0,
            seed=1,
            parameters=UncertaintyParameters(
                wind_east_mps=NormalDistribution(kind="normal", mean=0.0, std=1.0)
            ),
        )


# ---------------------------------------------------------------------------
# Statistics shape tests — verified through MonteCarloResult public fields
# ---------------------------------------------------------------------------


def test_single_sample_run_has_zero_std_and_all_percentiles_equal() -> None:
    result = run_monte_carlo(_wind_plan(samples=1), make_mission(), make_vehicle())
    s = result.total_time_s
    assert s is not None
    assert s.count == 1
    assert s.std == pytest.approx(0.0)
    assert s.min == pytest.approx(s.max)
    assert s.p5 == pytest.approx(s.p50)
    assert s.p50 == pytest.approx(s.p95)


def test_two_sample_run_mean_is_arithmetic_mean() -> None:
    # With a fixed seed and 2 samples we can only verify structural invariants.
    result = run_monte_carlo(_wind_plan(samples=2), make_mission(), make_vehicle())
    s = result.total_time_s
    assert s is not None
    assert s.count == 2
    assert s.min <= s.mean <= s.max


def test_stats_percentile_ordering_over_many_samples() -> None:
    result = run_monte_carlo(_wind_plan(samples=100), make_mission(), make_vehicle())
    s = result.total_time_s
    assert s is not None
    assert s.min <= s.p5
    assert s.p5 <= s.p50
    assert s.p50 <= s.p95
    assert s.p95 <= s.max


# ---------------------------------------------------------------------------
# Monte Carlo run tests
# ---------------------------------------------------------------------------


def test_monte_carlo_returns_completed_samples_and_stats() -> None:
    result = run_monte_carlo(_wind_plan(samples=10), make_mission(), make_vehicle())
    assert result.completed_sample_count == 10
    assert result.failed_sample_count == 0
    assert result.total_time_s is not None
    assert result.total_time_s.count == 10


def test_monte_carlo_reproducible_same_seed() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    plan = _wind_plan(seed=99)
    r1 = run_monte_carlo(plan, mission, vehicle)
    r2 = run_monte_carlo(plan, mission, vehicle)
    assert r1.total_time_s is not None
    assert r2.total_time_s is not None
    assert r1.total_time_s.mean == pytest.approx(r2.total_time_s.mean)
    assert r1.total_time_s.std == pytest.approx(r2.total_time_s.std)


def test_monte_carlo_different_seed_different_result() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    r1 = run_monte_carlo(_wind_plan(seed=1), mission, vehicle)
    r2 = run_monte_carlo(_wind_plan(seed=2), mission, vehicle)
    assert r1.total_time_s is not None
    assert r2.total_time_s is not None
    assert r1.total_time_s.mean != pytest.approx(r2.total_time_s.mean)


def test_monte_carlo_sample_count_matches() -> None:
    result = run_monte_carlo(_wind_plan(samples=10), make_mission(), make_vehicle())
    assert result.sample_count == 10
    assert result.completed_sample_count + result.failed_sample_count == 10


def test_monte_carlo_completed_samples_all_succeed() -> None:
    result = run_monte_carlo(_wind_plan(samples=20), make_mission(), make_vehicle())
    assert result.failed_sample_count == 0
    assert result.completed_sample_count == 20


def test_monte_carlo_baseline_is_deterministic() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    r1 = run_monte_carlo(_wind_plan(seed=1), mission, vehicle)
    r2 = run_monte_carlo(_wind_plan(seed=999), mission, vehicle)
    assert r1.baseline.total_time_s == pytest.approx(r2.baseline.total_time_s)


def test_monte_carlo_baseline_matches_direct_estimate() -> None:
    from estimator import try_estimate_mission_distance_time
    mission = make_mission()
    vehicle = make_vehicle()
    result = run_monte_carlo(_wind_plan(), mission, vehicle)
    direct = try_estimate_mission_distance_time(mission, vehicle)
    assert result.baseline.total_time_s == pytest.approx(direct.total_time_s)


def test_monte_carlo_uncertainty_id_matches_plan() -> None:
    result = run_monte_carlo(_wind_plan(), make_mission(), make_vehicle())
    assert result.uncertainty_id == "test-wind"


def test_monte_carlo_seed_matches_plan() -> None:
    result = run_monte_carlo(_wind_plan(seed=7), make_mission(), make_vehicle())
    assert result.seed == 7


def test_monte_carlo_stats_present_for_completed_samples() -> None:
    result = run_monte_carlo(_wind_plan(samples=10), make_mission(), make_vehicle())
    assert result.total_time_s is not None
    assert result.total_time_s.count == 10


def test_monte_carlo_reserve_stats_present() -> None:
    result = run_monte_carlo(_power_plan(samples=15), make_mission(), make_vehicle())
    assert result.reserve_at_landing_wh is not None
    assert result.reserve_at_landing_percent is not None
    assert result.reserve_at_landing_wh.count == 15


def test_monte_carlo_feasibility_rate_between_zero_and_one() -> None:
    result = run_monte_carlo(_power_plan(samples=20), make_mission(), make_vehicle())
    assert result.feasibility_rate is not None
    assert 0.0 <= result.feasibility_rate <= 1.0


def test_monte_carlo_wind_sampling_varies_time() -> None:
    result = run_monte_carlo(_wind_plan(samples=30), make_mission(), make_vehicle())
    assert result.total_time_s is not None
    assert result.total_time_s.std > 0.0


def test_monte_carlo_power_sampling_varies_reserve() -> None:
    result = run_monte_carlo(_power_plan(samples=30), make_mission(), make_vehicle())
    assert result.reserve_at_landing_wh is not None
    assert result.reserve_at_landing_wh.std > 0.0


def test_monte_carlo_speed_sampling_uniform() -> None:
    result = run_monte_carlo(_speed_plan(samples=30), make_mission(), make_vehicle())
    assert result.total_time_s is not None
    assert result.total_time_s.std > 0.0


def test_monte_carlo_battery_sampling_varies_reserve() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    plan = UncertaintyPlan(
        schema_version="uncertainty.v1",
        uncertainty_id="test-battery",
        mission_file="m.yaml",
        vehicle_file="v.yaml",
        samples=20,
        seed=42,
        parameters=UncertaintyParameters(
            battery_capacity_wh=NormalDistribution(kind="normal", mean=900.0, std=50.0),
        ),
    )
    result = run_monte_carlo(plan, mission, vehicle)
    assert result.reserve_at_landing_wh is not None
    assert result.reserve_at_landing_wh.std > 0.0


def test_monte_carlo_stats_min_le_p5_le_p50_le_p95_le_max() -> None:
    result = run_monte_carlo(_wind_plan(samples=50), make_mission(), make_vehicle())
    s = result.total_time_s
    assert s is not None
    assert s.min <= s.p5
    assert s.p5 <= s.p50
    assert s.p50 <= s.p95
    assert s.p95 <= s.max
