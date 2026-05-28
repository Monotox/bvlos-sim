"""Sample statistics, distribution sampling, and feasibility rate helpers."""

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
    return sample_dist(rng, dist)


def sample_positive_optional(
    rng: random.Random,
    dist: UncertaintyDistribution | None,
) -> float | None:
    sampled = sample_optional(rng, dist)
    if sampled is None:
        return None
    return max(0.1, sampled)


def compute_stats(values: list[float]) -> SampledOutputStats | None:
    n = len(values)
    if n == 0:
        return None
    if n == 1:
        v = values[0]
        return SampledOutputStats(
            count=1, mean=v, std=0.0, min=v, p5=v, p50=v, p95=v, max=v
        )
    quantiles = _stats_module.quantiles(values, n=20)
    return SampledOutputStats(
        count=n,
        mean=_stats_module.mean(values),
        std=_stats_module.stdev(values),
        min=min(values),
        p5=quantiles[0],
        p50=_stats_module.median(values),
        p95=quantiles[18],
        max=max(values),
    )


def reserve_violation_rate(
    values: list[float],
    *,
    reserve_threshold_wh: float | None,
) -> float:
    n = len(values)
    if reserve_threshold_wh is None or n == 0:
        return 0.0
    violation_count = sum(value < reserve_threshold_wh for value in values)
    return violation_count / n


def feasibility_rate(
    values: list[float],
    *,
    reserve_threshold_wh: float | None,
    spatial_infeasible_count: int = 0,
) -> float:
    total = len(values) + spatial_infeasible_count
    if total == 0:
        return 0.0
    if reserve_threshold_wh is None:
        return 0.0
    feasible_count = sum(value >= reserve_threshold_wh for value in values)
    return feasible_count / total
