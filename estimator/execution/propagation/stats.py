"""Sample statistics, distribution sampling, and feasibility rate helpers."""

import math
import random
import statistics as _stats_module

from estimator.core.uncertainty import SampledOutputStats
from schemas.uncertainty import NormalDistribution, UncertaintyDistribution


def sample_dist(rng: random.Random, dist: UncertaintyDistribution) -> float:
    if isinstance(dist, NormalDistribution):
        return rng.gauss(dist.mean, dist.std)
    return rng.uniform(dist.low, dist.high)


def sample_optional(
    rng: random.Random,
    dist: UncertaintyDistribution | None,
) -> float | None:
    if dist is None:
        return None
    sampled = sample_dist(rng, dist)
    if not math.isfinite(sampled):
        raise ValueError("sampled uncertainty value must be finite")
    return sampled


def sample_positive_optional(
    rng: random.Random,
    dist: UncertaintyDistribution | None,
) -> float | None:
    sampled = sample_optional(rng, dist)
    if sampled is None:
        return None
    if sampled <= 0.0:
        raise ValueError("sampled physical parameter must be greater than 0")
    return sampled


def compute_stats(values: list[float]) -> SampledOutputStats | None:
    n = len(values)
    if n == 0:
        return None
    if not all(math.isfinite(value) for value in values):
        raise ValueError("sample statistics require finite values")
    if n == 1:
        v = values[0]
        return SampledOutputStats(
            count=1, mean=v, std=0.0, min=v, p5=v, p50=v, p95=v, max=v
        )
    return SampledOutputStats(
        count=n,
        mean=_stats_module.mean(values),
        std=_stats_module.stdev(values),
        min=min(values),
        p5=_empirical_quantile(values, 0.05),
        p50=_empirical_quantile(values, 0.50),
        p95=_empirical_quantile(values, 0.95),
        max=max(values),
    )


def _empirical_quantile(values: list[float], probability: float) -> float:
    """Return a linearly interpolated sample quantile bounded by observations."""
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + (
        (ordered[upper_index] - ordered[lower_index]) * fraction
    )


def conditional_reserve_violation_rate(
    values: list[float],
    *,
    reserve_threshold_wh: float | None = None,
    reserve_thresholds_wh: list[float | None] | None = None,
) -> float:
    n = len(values)
    if n == 0:
        return 0.0
    thresholds = _resolve_thresholds(
        values,
        reserve_threshold_wh=reserve_threshold_wh,
        reserve_thresholds_wh=reserve_thresholds_wh,
    )
    if thresholds is None:
        return 0.0
    violation_count = sum(
        threshold is not None and value < threshold
        for value, threshold in zip(values, thresholds, strict=True)
    )
    return violation_count / n


def modeled_constraint_pass_rate(
    passed_sample_count: int,
    *,
    infeasible_sample_count: int = 0,
) -> float | None:
    """Return the pass fraction among evaluated deterministic samples.

    ``infeasible_sample_count`` already includes its spatial subset. Failed
    samples are intentionally absent because they were not evaluated.
    """
    if passed_sample_count < 0 or infeasible_sample_count < 0:
        raise ValueError("sample outcome counts must be non-negative")
    total = passed_sample_count + infeasible_sample_count
    if total == 0:
        return None
    return passed_sample_count / total


def _resolve_thresholds(
    values: list[float],
    *,
    reserve_threshold_wh: float | None,
    reserve_thresholds_wh: list[float | None] | None,
) -> list[float | None] | None:
    if reserve_thresholds_wh is not None:
        if len(reserve_thresholds_wh) != len(values):
            raise ValueError("reserve thresholds must match the number of values")
        return reserve_thresholds_wh
    if reserve_threshold_wh is None:
        return None
    return [reserve_threshold_wh] * len(values)
