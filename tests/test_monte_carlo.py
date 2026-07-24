"""Tests for Monte Carlo uncertainty modeling (Ticket 037)."""

import pytest
from pydantic import ValidationError

from bvlos_sim.estimator import run_monte_carlo
from bvlos_sim.estimator.core.enums import EstimateStatus
from bvlos_sim.estimator.core.results import WindVector
from bvlos_sim.estimator.execution.monte_carlo import _build_sample_wind_provider, _stats
from bvlos_sim.schemas.uncertainty import (
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
        schema_version="uncertainty.v2",
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
        schema_version="uncertainty.v2",
        uncertainty_id="test-power",
        mission_file="mission.yaml",
        vehicle_file="vehicle.yaml",
        samples=samples,
        seed=seed,
        parameters=UncertaintyParameters(
            cruise_power_w=UniformDistribution(kind="uniform", low=405.0, high=495.0),
        ),
    )


def _speed_plan(*, seed: int = 42, samples: int = 20) -> UncertaintyPlan:
    return UncertaintyPlan(
        schema_version="uncertainty.v2",
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
                "schema_version": "uncertainty.v2",
                "uncertainty_id": "x",
                "mission_file": "m.yaml",
                "vehicle_file": "v.yaml",
                "samples": 10,
                "seed": 1,
                "parameters": {
                    "wind_east_mps": {"kind": "normal", "mean": 0.0, "std": 1.0}
                },
                "extra_field": True,
            }
        )


def test_uncertainty_plan_rejects_zero_samples() -> None:
    with pytest.raises(ValidationError):
        UncertaintyPlan(
            schema_version="uncertainty.v2",
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


def test_two_sample_percentiles_are_bounded_empirical_quantiles() -> None:
    s = _stats([0.0, 10.0])
    assert s is not None
    assert s.p5 == pytest.approx(0.5)
    assert s.p95 == pytest.approx(9.5)
    assert s.min <= s.p5 <= s.p95 <= s.max


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


def test_monte_carlo_returns_modeled_pass_samples_and_stats() -> None:
    result = run_monte_carlo(_wind_plan(samples=10), make_mission(), make_vehicle())
    assert result.modeled_pass_sample_count == 10
    assert result.infeasible_sample_count == 0
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
    assert (
        result.modeled_pass_sample_count
        + result.infeasible_sample_count
        + result.failed_sample_count
        == 10
    )


def test_monte_carlo_modeled_pass_samples_all_succeed() -> None:
    result = run_monte_carlo(_wind_plan(samples=20), make_mission(), make_vehicle())
    assert result.failed_sample_count == 0
    assert result.modeled_pass_sample_count == 20
    assert result.infeasible_sample_count == 0


def test_monte_carlo_baseline_is_deterministic() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    r1 = run_monte_carlo(_wind_plan(seed=1), mission, vehicle)
    r2 = run_monte_carlo(_wind_plan(seed=999), mission, vehicle)
    assert r1.baseline.total_time_s == pytest.approx(r2.baseline.total_time_s)


def test_monte_carlo_baseline_matches_direct_estimate() -> None:
    from bvlos_sim.estimator import try_estimate_mission_distance_time

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
    assert result.reserve_at_mission_end_wh is not None
    assert result.reserve_at_mission_end_percent is not None
    assert result.reserve_at_mission_end_wh.count == 15


def test_monte_carlo_modeled_pass_rate_between_zero_and_one() -> None:
    result = run_monte_carlo(_power_plan(samples=20), make_mission(), make_vehicle())
    assert result.modeled_constraint_pass_rate is not None
    assert 0.0 <= result.modeled_constraint_pass_rate <= 1.0


def test_monte_carlo_counts_infeasible_separately_from_modeled_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bvlos_sim.estimator import try_estimate_mission_distance_time

    mission = make_mission()
    vehicle = make_vehicle()
    baseline = try_estimate_mission_distance_time(mission, vehicle)
    infeasible = baseline.model_copy(
        update={"status": EstimateStatus.INFEASIBLE, "energy": None}
    )
    results = iter([baseline, infeasible, baseline])

    monkeypatch.setattr(
        "bvlos_sim.estimator.execution.monte_carlo.try_estimate_mission_distance_time",
        lambda *_args, **_kwargs: next(results),
    )

    result = run_monte_carlo(_wind_plan(samples=2), mission, vehicle)

    assert result.modeled_pass_sample_count == 1
    assert result.infeasible_sample_count == 1
    assert result.failed_sample_count == 0
    assert result.modeled_constraint_pass_rate == pytest.approx(0.5)
    assert result.total_time_s is not None
    assert result.total_time_s.count == 1


def test_monte_carlo_does_not_count_error_or_incomplete_success_as_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bvlos_sim.estimator import try_estimate_mission_distance_time

    mission = make_mission()
    vehicle = make_vehicle()
    baseline = try_estimate_mission_distance_time(mission, vehicle)
    error = baseline.model_copy(update={"status": EstimateStatus.ERROR, "energy": None})
    incomplete = baseline.model_copy(update={"energy": None})
    results = iter([baseline, error, incomplete])
    monkeypatch.setattr(
        "bvlos_sim.estimator.execution.monte_carlo.try_estimate_mission_distance_time",
        lambda *_args, **_kwargs: next(results),
    )

    result = run_monte_carlo(_wind_plan(samples=2), mission, vehicle)

    assert result.modeled_pass_sample_count == 0
    assert result.infeasible_sample_count == 0
    assert result.failed_sample_count == 2
    assert result.modeled_constraint_pass_rate is None
    assert result.total_time_s is None
    assert result.reserve_at_mission_end_wh is None


def test_sampled_wind_preserves_unsampled_base_component() -> None:
    class DynamicWindProvider:
        provider_id = "dynamic-test"

        def wind_at(
            self,
            lat: float,
            lon: float,
            altitude_amsl_m: float,
            elapsed_time_s: float,
        ) -> WindVector:
            return WindVector(
                wind_east_mps=lat + elapsed_time_s,
                wind_north_mps=altitude_amsl_m - lon,
            )

    provider = _build_sample_wind_provider(3.0, None, DynamicWindProvider())
    assert provider is not None

    wind = provider.wind_at(
        lat=52.0,
        lon=4.0,
        altitude_amsl_m=100.0,
        elapsed_time_s=7.0,
    )

    assert wind.wind_east_mps == pytest.approx(3.0)
    assert wind.wind_north_mps == pytest.approx(96.0)


def test_monte_carlo_wind_sampling_varies_time() -> None:
    result = run_monte_carlo(_wind_plan(samples=30), make_mission(), make_vehicle())
    assert result.total_time_s is not None
    assert result.total_time_s.std > 0.0


def test_monte_carlo_power_sampling_varies_reserve() -> None:
    result = run_monte_carlo(_power_plan(samples=30), make_mission(), make_vehicle())
    assert result.reserve_at_mission_end_wh is not None
    assert result.reserve_at_mission_end_wh.std > 0.0


def test_monte_carlo_speed_sampling_uniform() -> None:
    result = run_monte_carlo(_speed_plan(samples=30), make_mission(), make_vehicle())
    assert result.total_time_s is not None
    assert result.total_time_s.std > 0.0


def test_monte_carlo_battery_sampling_varies_reserve() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    plan = UncertaintyPlan(
        schema_version="uncertainty.v2",
        uncertainty_id="test-battery",
        mission_file="m.yaml",
        vehicle_file="v.yaml",
        samples=20,
        seed=42,
        parameters=UncertaintyParameters(
            battery_capacity_wh=UniformDistribution(
                kind="uniform", low=850.0, high=950.0
            ),
        ),
    )
    result = run_monte_carlo(plan, mission, vehicle)
    assert result.reserve_at_mission_end_wh is not None
    assert result.reserve_at_mission_end_wh.std > 0.0


def test_monte_carlo_stats_min_le_p5_le_p50_le_p95_le_max() -> None:
    result = run_monte_carlo(_wind_plan(samples=50), make_mission(), make_vehicle())
    s = result.total_time_s
    assert s is not None
    assert s.min <= s.p5
    assert s.p5 <= s.p50
    assert s.p50 <= s.p95
    assert s.p95 <= s.max


def test_monte_carlo_non_estimator_error_propagates() -> None:
    """Non-EstimatorError exceptions must not be silently swallowed."""
    from bvlos_sim.estimator.execution.monte_carlo import run_monte_carlo as _run

    class BrokenWindProvider:
        def wind_at(self, **_kwargs: object) -> object:
            raise RuntimeError("unexpected hardware failure")

    with pytest.raises(RuntimeError, match="unexpected hardware failure"):
        _run(
            _wind_plan(samples=5),
            make_mission(),
            make_vehicle(),
            wind_provider=BrokenWindProvider(),  # type: ignore[arg-type]
        )


def test_monte_carlo_vehicle_without_energy_model_raises_value_error() -> None:
    """A vehicle with no energy model cannot produce a feasible baseline — fail fast."""
    vehicle = make_vehicle()
    vehicle.energy = None
    plan = UncertaintyPlan(
        schema_version="uncertainty.v2",
        uncertainty_id="test-no-energy",
        mission_file="m.yaml",
        vehicle_file="v.yaml",
        samples=5,
        seed=1,
        parameters=UncertaintyParameters(
            cruise_power_w=UniformDistribution(kind="uniform", low=440.0, high=460.0),
        ),
    )

    with pytest.raises(ValueError, match="feasible baseline"):
        run_monte_carlo(plan, make_mission(), vehicle)


def test_monte_carlo_infeasible_baseline_raises_value_error() -> None:
    """An INFEASIBLE baseline (e.g. battery too small) must also be rejected."""
    vehicle = make_vehicle()
    # Tiny battery ensures energy infeasibility on the test mission.
    vehicle.energy = vehicle.energy.model_copy(update={"battery_capacity_wh": 1.0})
    plan = UncertaintyPlan(
        schema_version="uncertainty.v2",
        uncertainty_id="test-infeasible-baseline",
        mission_file="m.yaml",
        vehicle_file="v.yaml",
        samples=5,
        seed=1,
        parameters=UncertaintyParameters(
            wind_east_mps=NormalDistribution(kind="normal", mean=0.0, std=1.0),
        ),
    )

    with pytest.raises(ValueError, match="feasible baseline"):
        run_monte_carlo(plan, make_mission(), vehicle)


def test_uncertainty_plan_rejects_unbounded_normal_for_positive_parameter() -> None:
    with pytest.raises(ValidationError, match="bounded positive uniform"):
        UncertaintyPlan(
            schema_version="uncertainty.v2",
            uncertainty_id="test-unbounded-speed",
            mission_file="m.yaml",
            vehicle_file="v.yaml",
            samples=20,
            seed=0,
            parameters=UncertaintyParameters(
                cruise_speed_mps=NormalDistribution(kind="normal", mean=20.0, std=2.0),
            ),
        )


def test_uncertainty_plan_rejects_nonpositive_uniform_support() -> None:
    with pytest.raises(ValidationError, match="low must be greater than 0"):
        UncertaintyPlan(
            schema_version="uncertainty.v2",
            uncertainty_id="test-nonpositive-speed",
            mission_file="m.yaml",
            vehicle_file="v.yaml",
            samples=20,
            seed=0,
            parameters=UncertaintyParameters(
                cruise_speed_mps=UniformDistribution(
                    kind="uniform", low=0.0, high=20.0
                ),
            ),
        )
