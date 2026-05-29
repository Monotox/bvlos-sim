"""Failure-to-exception translation helpers for execution."""

from estimator.core.enums import FailureKind
from estimator.core.errors import (
    EstimatorError,
    EstimatorInfeasibleError,
    InvalidEstimatorInputError,
    UnsupportedEstimatorFeatureError,
)
from estimator.core.results import (
    EnergyEstimate,
    EstimatorContextValue,
    EstimatorFailure,
    EstimatorWarning,
    GeofenceEstimate,
    LandingZoneEstimate,
    LegEstimate,
    LinkEstimate,
    ObstacleEstimate,
    ResourceEstimate,
    WeatherEstimate,
)

_FAILURE_ERROR_TYPES = {
    FailureKind.UNSUPPORTED: UnsupportedEstimatorFeatureError,
    FailureKind.INVALID_INPUT: InvalidEstimatorInputError,
    FailureKind.INFEASIBLE: EstimatorInfeasibleError,
}


def error_from_failure(
    failure: EstimatorFailure,
    *,
    partial_legs: list[LegEstimate],
    energy: EnergyEstimate | None = None,
    resource: ResourceEstimate | None = None,
    link: LinkEstimate | None = None,
    geofence: GeofenceEstimate | None = None,
    landing_zone: LandingZoneEstimate | None = None,
    obstacle: ObstacleEstimate | None = None,
    weather: WeatherEstimate | None = None,
    totals_are_partial: bool | None = None,
    warnings: list[EstimatorWarning],
    metadata: dict[str, EstimatorContextValue],
) -> EstimatorError:
    error_type = _FAILURE_ERROR_TYPES.get(failure.kind, EstimatorError)
    return error_type(
        failure,
        partial_legs=partial_legs,
        energy=energy,
        resource=resource,
        link=link,
        geofence=geofence,
        landing_zone=landing_zone,
        obstacle=obstacle,
        weather=weather,
        totals_are_partial=totals_are_partial,
        warnings=warnings,
        metadata=metadata,
    )
