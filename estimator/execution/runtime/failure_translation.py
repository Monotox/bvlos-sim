"""Failure-to-exception translation helpers for execution."""

from estimator.core.errors import EstimatorError
from estimator.core.errors import EstimatorInfeasibleError
from estimator.core.errors import InvalidEstimatorInputError
from estimator.core.errors import UnsupportedEstimatorFeatureError
from estimator.core.enums import FailureKind
from estimator.core.results import EstimatorContextValue
from estimator.core.results import EnergyEstimate
from estimator.core.results import EstimatorFailure
from estimator.core.results import EstimatorWarning
from estimator.core.results import GeofenceEstimate
from estimator.core.results import LandingZoneEstimate
from estimator.core.results import LegEstimate

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
    geofence: GeofenceEstimate | None = None,
    landing_zone: LandingZoneEstimate | None = None,
    totals_are_partial: bool | None = None,
    warnings: list[EstimatorWarning],
    metadata: dict[str, EstimatorContextValue],
) -> EstimatorError:
    error_type = _FAILURE_ERROR_TYPES.get(failure.kind, EstimatorError)
    return error_type(
        failure,
        partial_legs=partial_legs,
        energy=energy,
        geofence=geofence,
        landing_zone=landing_zone,
        totals_are_partial=totals_are_partial,
        warnings=warnings,
        metadata=metadata,
    )
