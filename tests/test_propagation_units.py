"""Unit tests for the propagation/ subpackage helper modules."""

import random

import pytest

from estimator.execution.propagation.curves import (
    EnergyDrainCurve,
    EnergyLegDrain,
    PositionInterpolator,
    timeline_steps,
)
from estimator.execution.propagation.stats import (
    compute_stats,
    feasibility_rate,
    reserve_violation_rate,
    sample_dist,
    sample_optional,
    sample_positive_optional,
)
from schemas.uncertainty import NormalDistribution, UniformDistribution


# ---------------------------------------------------------------------------
# stats.py
# ---------------------------------------------------------------------------


def test_compute_stats_empty_returns_none() -> None:
    assert compute_stats([]) is None


def test_compute_stats_single_value() -> None:
    s = compute_stats([42.0])
    assert s is not None
    assert s.count == 1
    assert s.mean == 42.0
    assert s.std == 0.0
    assert s.min == s.max == s.p5 == s.p50 == s.p95 == 42.0


def test_compute_stats_multiple_values() -> None:
    values = list(range(1, 101))  # 1..100
    s = compute_stats([float(v) for v in values])
    assert s is not None
    assert s.count == 100
    assert s.min == 1.0
    assert s.max == 100.0
    assert 50.0 <= s.p50 <= 51.0
    assert s.p5 < s.p50 < s.p95


def test_reserve_violation_rate_none_threshold_returns_zero() -> None:
    assert reserve_violation_rate([1.0, 2.0, 3.0], reserve_threshold_wh=None) == 0.0


def test_reserve_violation_rate_empty_returns_zero() -> None:
    assert reserve_violation_rate([], reserve_threshold_wh=100.0) == 0.0


def test_reserve_violation_rate_all_below() -> None:
    assert reserve_violation_rate([1.0, 2.0, 3.0], reserve_threshold_wh=10.0) == 1.0


def test_reserve_violation_rate_partial() -> None:
    rate = reserve_violation_rate([5.0, 15.0, 25.0], reserve_threshold_wh=10.0)
    assert abs(rate - 1 / 3) < 1e-9


def test_feasibility_rate_empty_returns_zero() -> None:
    assert feasibility_rate([], reserve_threshold_wh=100.0) == 0.0


def test_feasibility_rate_none_threshold_returns_zero() -> None:
    assert feasibility_rate([100.0, 200.0], reserve_threshold_wh=None) == 0.0


def test_feasibility_rate_all_feasible() -> None:
    assert feasibility_rate([50.0, 60.0, 70.0], reserve_threshold_wh=10.0) == 1.0


def test_feasibility_rate_with_spatial_infeasible() -> None:
    # 2 feasible, 0 failed energy, 2 spatial infeasible → 2/4 = 0.5
    rate = feasibility_rate([50.0, 60.0], reserve_threshold_wh=10.0, spatial_infeasible_count=2)
    assert abs(rate - 0.5) < 1e-9


def test_sample_dist_normal_seeded() -> None:
    rng = random.Random(42)
    dist = NormalDistribution(kind="normal", mean=10.0, std=1.0)
    v = sample_dist(rng, dist)
    assert isinstance(v, float)


def test_sample_dist_uniform_seeded() -> None:
    rng = random.Random(42)
    dist = UniformDistribution(kind="uniform", low=5.0, high=15.0)
    v = sample_dist(rng, dist)
    assert 5.0 <= v < 15.0


def test_sample_optional_none_dist_returns_none() -> None:
    rng = random.Random(0)
    assert sample_optional(rng, None) is None


def test_sample_positive_optional_clamps_to_minimum() -> None:
    # A normal distribution that could go very negative — should be clamped to 0.1
    rng = random.Random(0)
    dist = NormalDistribution(kind="normal", mean=-1000.0, std=0.001)
    result = sample_positive_optional(rng, dist)
    assert result == 0.1


# ---------------------------------------------------------------------------
# curves.py — EnergyDrainCurve
# ---------------------------------------------------------------------------


def _two_leg_curve() -> EnergyDrainCurve:
    return EnergyDrainCurve(
        legs=(
            EnergyLegDrain(duration_s=60.0, energy_wh=10.0),
            EnergyLegDrain(duration_s=120.0, energy_wh=20.0),
        )
    )


def test_energy_drain_curve_total_duration() -> None:
    curve = _two_leg_curve()
    assert curve.total_duration_s == 180.0


def test_energy_drain_curve_at_start() -> None:
    assert _two_leg_curve().energy_consumed_at(0.0) == 0.0


def test_energy_drain_curve_at_end_of_first_leg() -> None:
    assert _two_leg_curve().energy_consumed_at(60.0) == 10.0


def test_energy_drain_curve_midway_through_first_leg() -> None:
    consumed = _two_leg_curve().energy_consumed_at(30.0)
    assert abs(consumed - 5.0) < 1e-9


def test_energy_drain_curve_at_total_duration() -> None:
    curve = _two_leg_curve()
    assert abs(curve.energy_consumed_at(180.0) - 30.0) < 1e-9


def test_energy_drain_curve_past_end_clamps() -> None:
    curve = _two_leg_curve()
    assert abs(curve.energy_consumed_at(999.0) - 30.0) < 1e-9


def test_energy_drain_curve_zero_duration_leg_returns_full_energy() -> None:
    curve = EnergyDrainCurve(
        legs=(EnergyLegDrain(duration_s=0.0, energy_wh=5.0),)
    )
    assert curve.energy_consumed_at(0.0) == 5.0


# ---------------------------------------------------------------------------
# curves.py — PositionInterpolator
# ---------------------------------------------------------------------------


def _make_leg(
    start_lat: float, start_lon: float, end_lat: float, end_lon: float, time_s: float
) -> object:
    from estimator.core.results import LegEstimate
    from estimator.core.enums import LegPhase
    return LegEstimate(
        leg_index=0,
        route_item_index=0,
        route_item_id="wp1",
        action="waypoint",
        phase=LegPhase.TRANSIT,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt_amsl_m=100.0,
        end_lat=end_lat,
        end_lon=end_lon,
        end_alt_amsl_m=100.0,
        horizontal_distance_m=1000.0,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=1000.0,
        time_s=time_s,
    )


def test_position_interpolator_no_legs_returns_fallback() -> None:
    pos = PositionInterpolator(legs=[], fallback_lat=52.0, fallback_lon=4.0)
    assert pos.at(0.0) == (52.0, 4.0)
    assert pos.at(999.0) == (52.0, 4.0)


def test_position_interpolator_at_start() -> None:
    leg = _make_leg(52.0, 4.0, 52.1, 4.1, time_s=100.0)
    pos = PositionInterpolator(legs=[leg], fallback_lat=0.0, fallback_lon=0.0)
    lat, lon = pos.at(0.0)
    assert abs(lat - 52.0) < 1e-9
    assert abs(lon - 4.0) < 1e-9


def test_position_interpolator_at_midpoint() -> None:
    leg = _make_leg(52.0, 4.0, 52.2, 4.2, time_s=100.0)
    pos = PositionInterpolator(legs=[leg], fallback_lat=0.0, fallback_lon=0.0)
    lat, lon = pos.at(50.0)
    assert abs(lat - 52.1) < 1e-9
    assert abs(lon - 4.1) < 1e-9


def test_position_interpolator_past_end_returns_last_position() -> None:
    leg = _make_leg(52.0, 4.0, 52.2, 4.2, time_s=100.0)
    pos = PositionInterpolator(legs=[leg], fallback_lat=0.0, fallback_lon=0.0)
    lat, lon = pos.at(999.0)
    assert abs(lat - 52.2) < 1e-9
    assert abs(lon - 4.2) < 1e-9


# ---------------------------------------------------------------------------
# curves.py — timeline_steps
# ---------------------------------------------------------------------------


def test_timeline_steps_zero_or_negative_returns_single_zero() -> None:
    assert timeline_steps(0.0, 1.0) == [0.0]
    assert timeline_steps(-1.0, 1.0) == [0.0]


def test_timeline_steps_exact_multiple() -> None:
    steps = timeline_steps(3.0, 1.0)
    assert steps == [0.0, 1.0, 2.0, 3.0]


def test_timeline_steps_non_multiple_appends_t_max() -> None:
    steps = timeline_steps(2.5, 1.0)
    assert steps[-1] == pytest.approx(2.5)
    assert len(steps) == 4  # 0, 1, 2, 2.5


def test_timeline_steps_are_non_decreasing() -> None:
    steps = timeline_steps(10.3, 1.5)
    assert all(steps[i] <= steps[i + 1] for i in range(len(steps) - 1))
