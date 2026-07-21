"""Deterministic, fail-closed weather-minimums feasibility evaluation.

Enforces sustained-wind and crosswind limits against the worst samples retained
for each route leg. A configured gust, visibility, or precipitation limit is
infeasible when the active providers cannot supply the required observation.
"""

from dataclasses import dataclass
import math

from estimator.core.enums import FailureCode, FailureKind
from estimator.core.results import (
    EstimatorFailure,
    LegEstimate,
    WeatherEstimate,
    WeatherViolation,
    WindVector,
)
from estimator.environment.wind import (
    ConstantWindProvider,
    TimeVaryingWindProvider,
    WindProvider,
)
from estimator.execution.runtime import EstimationContext

_MAX_WEATHER_SAMPLE_INTERVAL_S = 60.0


@dataclass(frozen=True)
class WeatherEvaluation:
    weather: WeatherEstimate | None
    failure: EstimatorFailure | None


@dataclass(frozen=True)
class TimedWindSample:
    elapsed_time_s: float
    wind: WindVector


def _active_provider_next_change(
    provider: WindProvider,
    *,
    elapsed_time_s: float,
) -> tuple[WindProvider, float | None]:
    next_change_s: float | None = None
    active = provider
    while isinstance(active, TimeVaryingWindProvider):
        candidate = active.next_change_after(elapsed_time_s)
        if candidate is not None and (
            next_change_s is None or candidate < next_change_s
        ):
            next_change_s = candidate
        active = active.provider_for_elapsed_time(elapsed_time_s)
    return active, next_change_s


def sample_wind_interval(
    provider: WindProvider,
    *,
    lat: float,
    lon: float,
    start_altitude_amsl_m: float,
    end_altitude_amsl_m: float,
    start_elapsed_time_s: float,
    duration_s: float,
) -> tuple[TimedWindSample, ...]:
    """Sample endpoints, scheduled changes, and at most 60-second intervals."""

    interval_count = max(1, math.ceil(duration_s / _MAX_WEATHER_SAMPLE_INTERVAL_S))
    times = {
        start_elapsed_time_s + duration_s * index / interval_count
        for index in range(interval_count + 1)
    }
    end_elapsed_time_s = start_elapsed_time_s + duration_s
    cursor_s = start_elapsed_time_s
    while cursor_s < end_elapsed_time_s:
        _, next_change_s = _active_provider_next_change(
            provider,
            elapsed_time_s=cursor_s,
        )
        if next_change_s is None or next_change_s > end_elapsed_time_s:
            break
        times.add(next_change_s)
        cursor_s = next_change_s

    samples: list[TimedWindSample] = []
    for elapsed_time_s in sorted(times):
        altitude_fraction = (
            1.0
            if duration_s <= 0.0
            else (elapsed_time_s - start_elapsed_time_s) / duration_s
        )
        altitude_amsl_m = start_altitude_amsl_m + altitude_fraction * (
            end_altitude_amsl_m - start_altitude_amsl_m
        )
        samples.append(
            TimedWindSample(
                elapsed_time_s=elapsed_time_s,
                wind=provider.wind_at(
                    lat=lat,
                    lon=lon,
                    altitude_amsl_m=altitude_amsl_m,
                    elapsed_time_s=elapsed_time_s,
                ),
            )
        )
    return tuple(samples)


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


def _legs_with_weather_observations(
    context: EstimationContext,
) -> list[LegEstimate]:
    observed: list[LegEstimate] = []
    elapsed_time_s = 0.0
    for leg in context.route_legs:
        if leg.wind_speed_mps is not None:
            observed.append(leg)
        else:
            samples = sample_wind_interval(
                context.wind_provider,
                lat=(leg.start_lat + leg.end_lat) * 0.5,
                lon=(leg.start_lon + leg.end_lon) * 0.5,
                start_altitude_amsl_m=leg.start_alt_amsl_m,
                end_altitude_amsl_m=leg.end_alt_amsl_m,
                start_elapsed_time_s=elapsed_time_s,
                duration_s=leg.time_s,
            )
            worst = max(samples, key=lambda sample: context.wind_speed(sample.wind))
            observed.append(
                leg.model_copy(
                    update={
                        "wind_east_mps": worst.wind.wind_east_mps,
                        "wind_north_mps": worst.wind.wind_north_mps,
                        "wind_speed_mps": context.wind_speed(worst.wind),
                    }
                )
            )
        elapsed_time_s += leg.time_s
    return observed


def evaluate_weather_feasibility(context: EstimationContext) -> WeatherEvaluation:
    """Evaluate wind/crosswind limits after kinematic route expansion."""
    constraints = context.mission.constraints
    max_wind = constraints.max_wind_mps
    max_crosswind = constraints.max_crosswind_mps

    unavailable_fields = [
        field_name
        for field_name, value in (
            ("constraints.max_gust_mps", constraints.max_gust_mps),
            ("constraints.min_visibility_m", constraints.min_visibility_m),
            (
                "constraints.max_precipitation_mm_h",
                constraints.max_precipitation_mm_h,
            ),
        )
        if value is not None
    ]
    if unavailable_fields:
        return WeatherEvaluation(
            weather=None,
            failure=EstimatorFailure(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.WEATHER_DATA_UNAVAILABLE,
                message=(
                    "Configured weather minimums require observations that are "
                    "not available from the active weather provider."
                ),
                context={"unavailable_fields": ",".join(unavailable_fields)},
            ),
        )

    if max_wind is None and max_crosswind is None:
        return WeatherEvaluation(weather=None, failure=None)
    if not _wind_configured(context.wind_provider):
        return WeatherEvaluation(weather=None, failure=None)

    legs = _legs_with_weather_observations(context)
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
