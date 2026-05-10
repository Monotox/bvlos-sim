"""Aggregation helpers for mission leg totals."""

from dataclasses import dataclass

from estimator.core.results import LegEstimate


@dataclass(frozen=True)
class MissionTotals:
    horizontal_distance_m: float
    vertical_distance_m: float
    path_distance_m: float
    time_s: float


def sum_totals(legs: list[LegEstimate]) -> MissionTotals:
    return MissionTotals(
        horizontal_distance_m=sum(leg.horizontal_distance_m for leg in legs),
        vertical_distance_m=sum(leg.vertical_distance_m for leg in legs),
        path_distance_m=sum(leg.path_distance_m for leg in legs),
        time_s=sum(leg.time_s for leg in legs),
    )
