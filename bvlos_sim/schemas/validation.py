"""Predicted-vs-observed validation report schema models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bvlos_sim.schemas.flight_log import FlightTraceMissionRef

VALIDATION_REPORT_SCHEMA_VERSION = "validation-report.v2"


class MetricComparison(BaseModel):
    """One predicted-vs-observed scalar comparison.

    ``abs_error`` and ``pct_error`` are populated only when both predicted and
    observed values are present; ``pct_error`` additionally requires a non-zero
    observed value. ``pct_error`` is expressed relative to the observed value.
    """

    model_config = ConfigDict(extra="forbid")

    predicted: float | None = Field(
        default=None, description="Predicted (estimator) value."
    )
    observed: float | None = Field(
        default=None, description="Observed (flight-trace) value."
    )
    abs_error: float | None = Field(
        default=None, description="abs(predicted - observed), if both are present."
    )
    pct_error: float | None = Field(
        default=None,
        description="100 * abs_error / abs(observed), if observed is present and non-zero.",
    )

    @classmethod
    def build(cls, predicted: float | None, observed: float | None) -> MetricComparison:
        """Construct a comparison, deriving error fields where both values exist."""
        abs_error: float | None = None
        pct_error: float | None = None
        if predicted is not None and observed is not None:
            abs_error = abs(predicted - observed)
            if observed != 0.0:
                pct_error = 100.0 * abs_error / abs(observed)
        return cls(
            predicted=predicted,
            observed=observed,
            abs_error=abs_error,
            pct_error=pct_error,
        )


class MissionValidationMetrics(BaseModel):
    """Mission-level predicted-vs-observed comparisons."""

    model_config = ConfigDict(extra="forbid")

    time_s: MetricComparison = Field(description="Total flight time (s).")
    horizontal_distance_m: MetricComparison = Field(
        description="Total horizontal ground distance (m)."
    )
    mean_groundspeed_mps: MetricComparison = Field(
        description="Mean groundspeed (m/s): time-weighted over legs, sample-mean over records."
    )
    reserve_percent: MetricComparison = Field(
        description="Reserve at landing (%): estimator reserve vs observed battery-remaining."
    )


class PhaseValidation(BaseModel):
    """Predicted-vs-observed comparison for one estimator leg phase."""

    model_config = ConfigDict(extra="forbid")

    phase: str = Field(
        min_length=1,
        description="Estimator leg-phase value (the bridge between legs and trace segments).",
    )
    time_s: MetricComparison = Field(description="Total time in this phase (s).")
    mean_groundspeed_mps: MetricComparison = Field(
        description="Mean groundspeed in this phase (m/s)."
    )
    predicted_leg_count: int = Field(
        ge=0, description="Estimator legs assigned to this phase."
    )
    observed_segment_count: int = Field(
        ge=0, description="Trace segments mapped to this phase."
    )


class ValidationAcceptance(BaseModel):
    """Explicit release-gate thresholds and their evaluated outcome."""

    model_config = ConfigDict(extra="forbid")

    thresholds_pct: dict[str, float] = Field(
        description="Maximum accepted absolute percentage error by metric."
    )
    errors_pct: dict[str, float | None] = Field(
        description="Observed absolute percentage error by gated metric."
    )
    passed: bool = Field(
        description="True only when every gated metric is available and within threshold."
    )
    failures: list[str] = Field(
        default_factory=list,
        description="Unavailable or out-of-threshold metric diagnostics.",
    )


class ValidationReport(BaseModel):
    """Versioned predicted-vs-observed validation report.

    Deterministic: the same estimate, trace, and segmentation always produce the
    same report. Distances use the same WGS-84 geodesic model as the estimator.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["validation-report.v2"] = Field(
        description="Validation report schema version."
    )
    validation_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable validation report identifier.",
    )
    tool_version: str = Field(
        min_length=1, description="bvlos-sim version that produced the report."
    )
    trace_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="trace_id of the validated NormalizedFlightTrace.",
    )
    mission_ref: FlightTraceMissionRef | None = Field(
        default=None,
        description="Paired mission/vehicle reference carried from the trace.",
    )
    observed_record_count: int = Field(
        ge=0,
        description="Number of trace records the observed metrics were computed from.",
    )
    mission_metrics: MissionValidationMetrics = Field(
        description="Mission-level predicted-vs-observed comparisons."
    )
    phase_validations: list[PhaseValidation] = Field(
        default_factory=list,
        description="Per-estimator-phase comparisons, sorted by phase name.",
    )
    acceptance: ValidationAcceptance = Field(
        description="Explicit validation acceptance gate and thresholds."
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Data-availability caveats and observed phases with no estimator counterpart.",
    )


__all__ = [
    "VALIDATION_REPORT_SCHEMA_VERSION",
    "MetricComparison",
    "MissionValidationMetrics",
    "PhaseValidation",
    "ValidationAcceptance",
    "ValidationReport",
]
