"""Deterministic weather-minimums feasibility evaluation.

Enforces operator-defined wind limits against the per-leg wind already sampled
during route execution. Sustained wind and crosswind are enforced as
feasibility gates; gust enforcement requires gust data the per-leg wind model
does not carry, so it emits a non-blocking advisory.
"""

from dataclasses import dataclass

from estimator.core.enums import FailureCode, FailureKind, WarningCode
from estimator.core.results import (
    EstimatorFailure,
    EstimatorWarning,
    LegEstimate,
    WeatherEstimate,
    WeatherViolation,
)
from estimator.environment.wind import ConstantWindProvider, WindProvider
from estimator.execution.runtime import EstimationContext


@dataclass(frozen=True)
class WeatherEvaluation:
    weather: WeatherEstimate | None
    failure: EstimatorFailure | None


def _wind_configured(provider: WindProvider | None) -> bool:
    if provider is None:
        return False
    if isinstance(provider, ConstantWindProvider):
        return provider.wind_east_mps != 0.0 or provider.wind_north_mps != 0.0
    return True


def _leg_crosswind_mps(leg: LegEstimate) -> float | None:
    if leg.wind_cross_track_mps is None:
        return None
    return abs(leg.wind_cross_track_mps)


def _violation(
    *,
    code: FailureCode,
    message: str,
    leg: LegEstimate,
    observed_mps: float,
    limit_mps: float,
) -> WeatherViolation:
    return WeatherViolation(
        code=code,
        message=message,
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
        observed_mps=observed_mps,
        limit_mps=limit_mps,
    )


def _failure_from_violation(violation: WeatherViolation) -> EstimatorFailure:
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=violation.code,
        message=violation.message,
        leg_index=violation.leg_index,
        route_item_index=violation.route_item_index,
        route_item_id=violation.route_item_id,
        context={
            "observed_mps": violation.observed_mps,
            "limit_mps": violation.limit_mps,
        },
    )


def evaluate_weather_feasibility(context: EstimationContext) -> WeatherEvaluation:
    """Evaluate wind/crosswind limits after kinematic route expansion."""
    constraints = context.mission.constraints
    max_wind = constraints.max_wind_mps
    max_crosswind = constraints.max_crosswind_mps

    if constraints.max_gust_mps is not None:
        context.warnings.append(
            EstimatorWarning(
                code=WarningCode.GUST_DATA_UNAVAILABLE,
                message=(
                    "constraints.max_gust_mps is set but the wind model carries no "
                    "gust data; the gust limit was not enforced."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        )

    if max_wind is None and max_crosswind is None:
        return WeatherEvaluation(weather=None, failure=None)
    if not _wind_configured(context.wind_provider):
        return WeatherEvaluation(weather=None, failure=None)

    legs = [leg for leg in context.route_legs if leg.wind_speed_mps is not None]
    if not legs:
        return WeatherEvaluation(weather=None, failure=None)

    worst_wind_speed: float | None = None
    worst_leg: LegEstimate | None = None
    worst_crosswind: float | None = None
    wind_violations: list[WeatherViolation] = []
    crosswind_violations: list[WeatherViolation] = []

    for leg in legs:
        wind_speed = leg.wind_speed_mps
        assert wind_speed is not None
        if worst_wind_speed is None or wind_speed > worst_wind_speed:
            worst_wind_speed = wind_speed
            worst_leg = leg

        crosswind = _leg_crosswind_mps(leg)
        if crosswind is not None and (
            worst_crosswind is None or crosswind > worst_crosswind
        ):
            worst_crosswind = crosswind

        if max_wind is not None and wind_speed > max_wind:
            wind_violations.append(
                _violation(
                    code=FailureCode.WIND_LIMIT_EXCEEDED,
                    message=(
                        f"Sustained wind {wind_speed:.1f} m/s exceeds the mission "
                        f"limit of {max_wind:.1f} m/s."
                    ),
                    leg=leg,
                    observed_mps=wind_speed,
                    limit_mps=max_wind,
                )
            )
        if (
            max_crosswind is not None
            and crosswind is not None
            and crosswind > max_crosswind
        ):
            crosswind_violations.append(
                _violation(
                    code=FailureCode.CROSSWIND_LIMIT_EXCEEDED,
                    message=(
                        f"Crosswind {crosswind:.1f} m/s exceeds the mission limit "
                        f"of {max_crosswind:.1f} m/s."
                    ),
                    leg=leg,
                    observed_mps=crosswind,
                    limit_mps=max_crosswind,
                )
            )

    violations = wind_violations + crosswind_violations
    weather = WeatherEstimate(
        is_feasible=not violations,
        checked_leg_count=len(legs),
        max_wind_mps=max_wind,
        max_crosswind_mps=max_crosswind,
        max_gust_mps=constraints.max_gust_mps,
        worst_wind_speed_mps=worst_wind_speed,
        worst_crosswind_mps=worst_crosswind,
        worst_leg_index=worst_leg.leg_index if worst_leg is not None else None,
        worst_route_item_id=worst_leg.route_item_id if worst_leg is not None else None,
        violations=violations,
    )
    failure = _failure_from_violation(violations[0]) if violations else None
    return WeatherEvaluation(weather=weather, failure=failure)


__all__ = [
    "WeatherEvaluation",
    "evaluate_weather_feasibility",
]
