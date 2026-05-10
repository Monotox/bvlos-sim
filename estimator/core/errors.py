"""Typed estimator errors."""

from estimator.core.results import (
    EnergyEstimate,
    EstimatorContextValue,
    EstimatorFailure,
    EstimatorWarning,
    GeofenceEstimate,
    LandingZoneEstimate,
    LegEstimate,
)


class EstimatorError(Exception):
    """Base estimator exception carrying structured failure details."""

    def __init__(
        self,
        failure: EstimatorFailure,
        *,
        partial_legs: list[LegEstimate] | None = None,
        energy: EnergyEstimate | None = None,
        geofence: GeofenceEstimate | None = None,
        landing_zone: LandingZoneEstimate | None = None,
        totals_are_partial: bool | None = None,
        warnings: list[EstimatorWarning] | None = None,
        metadata: dict[str, EstimatorContextValue] | None = None,
    ) -> None:
        super().__init__(failure.message)
        legs = partial_legs or []
        self.failure = failure
        self.partial_legs = legs
        self.energy = energy
        self.geofence = geofence
        self.landing_zone = landing_zone
        self.totals_are_partial = (
            len(legs) > 0 if totals_are_partial is None else totals_are_partial
        )
        self.warnings = warnings or []
        self.metadata = metadata or {}


class UnsupportedEstimatorFeatureError(EstimatorError):
    """Unsupported model/action/feature requested in mission."""


class InvalidEstimatorInputError(EstimatorError):
    """Invalid mission/vehicle/options values for estimation."""


class EstimatorInfeasibleError(EstimatorError):
    """Mission infeasible under constraints and wind model."""
