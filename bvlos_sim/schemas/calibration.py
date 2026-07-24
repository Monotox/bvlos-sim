"""Calibration profile schema models.

A calibration profile is a versioned, deterministic artifact that *layers on top
of* a base vehicle profile: it references the base ``vehicle_id`` and carries a
narrow set of fitted performance parameters derived from observed flight data. It
never replaces the base vehicle profile — the apply path copies the base vehicle
and overrides only the matching fields.

Fitted in v1: ``cruise_speed_mps``, ``climb_rate_mps``, ``descent_rate_mps``, and
station-keep wind authority (``max_station_keep_wind_mps``). Phase energy
coefficients are explicitly deferred until the energy model grows a fitting
surface (Ticket 083 out of scope); they are not part of this schema.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CALIBRATION_PROFILE_SCHEMA_VERSION = "calibration-profile.v1"


class CalibratedParameterName(StrEnum):
    """Vehicle parameters the v1 fitter can calibrate.

    Each value is the exact ``PerformanceProfile`` field name it overrides, so the
    apply path needs no name translation.
    """

    CRUISE_SPEED_MPS = "cruise_speed_mps"
    CLIMB_RATE_MPS = "climb_rate_mps"
    DESCENT_RATE_MPS = "descent_rate_mps"
    MAX_STATION_KEEP_WIND_MPS = "max_station_keep_wind_mps"


class CalibratedParameter(BaseModel):
    """One fitted parameter record.

    ``fitted_value`` is the value applied to the base vehicle. ``confidence_low``
    and ``confidence_high`` bound the fitted value (the observed spread of the
    samples it was derived from); ``spread`` is the population standard deviation
    of those samples. ``sample_count`` is the number of observations behind the
    fit, and ``applicable_conditions`` records the envelope the value was observed
    under so a consumer can judge whether it transfers.
    """

    model_config = ConfigDict(extra="forbid")

    parameter: CalibratedParameterName = Field(
        description="Calibrated parameter, named for the vehicle field it overrides."
    )
    fitted_value: float = Field(
        description="Value fitted from observed data, in the parameter's unit."
    )
    unit: str = Field(min_length=1, description="Physical unit of the fitted value.")
    sample_count: int = Field(
        ge=1, description="Number of observed samples behind the fit."
    )
    confidence_low: float = Field(
        description="Lower bound of the observed sample range."
    )
    confidence_high: float = Field(
        description="Upper bound of the observed sample range."
    )
    spread: float = Field(
        ge=0.0,
        description="Population standard deviation of the observed samples.",
    )
    calibration_dataset_version: str = Field(
        min_length=1,
        description=(
            "Content-addressed identifier of the complete traces and segmentations "
            "this fit was derived from."
        ),
    )
    applicable_conditions: list[str] = Field(
        default_factory=list,
        description="Observed conditions the fitted value applies to.",
    )
    derivation: str = Field(
        min_length=1,
        description="How the value was derived from the observed data.",
    )

    @model_validator(mode="after")
    def _confidence_ordered(self) -> CalibratedParameter:
        if self.confidence_high < self.confidence_low:
            raise ValueError(
                f"confidence_high ({self.confidence_high}) must be >= "
                f"confidence_low ({self.confidence_low})"
            )
        return self


class CalibrationProvenance(BaseModel):
    """Traceability linking fitted values back to their sources."""

    model_config = ConfigDict(extra="forbid")

    tool_version: str = Field(
        min_length=1, description="bvlos-sim version that produced the profile."
    )
    calibration_dataset_version: str = Field(
        min_length=1,
        description=(
            "Content-addressed identifier covering trace records/provenance and "
            "segmentation records/settings."
        ),
    )
    source_trace_ids: list[str] = Field(
        default_factory=list,
        description="trace_ids of the NormalizedFlightTraces the fit consumed, sorted.",
    )
    validation_report_ids: list[str] = Field(
        default_factory=list,
        description="validation_ids of any linked predicted-vs-observed reports, sorted.",
    )


class CalibrationProfile(BaseModel):
    """Versioned, deterministic calibration artifact layered on a base vehicle.

    The same base vehicle and the same collection of traces/segmentations always
    produce the same profile. The artifact references ``base_vehicle_id`` and
    overrides only the listed parameters when applied; every other vehicle field is
    inherited unchanged.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["calibration-profile.v1"] = Field(
        description="Calibration profile schema version."
    )
    calibration_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable calibration profile identifier.",
    )
    base_vehicle_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="vehicle_id of the base profile this calibration layers on.",
    )
    provenance: CalibrationProvenance = Field(
        description="Traceability for the fitted values."
    )
    parameters: list[CalibratedParameter] = Field(
        default_factory=list,
        description="Fitted parameter records, sorted by parameter name.",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Parameters that could not be fit and other data-availability caveats.",
    )


__all__ = [
    "CALIBRATION_PROFILE_SCHEMA_VERSION",
    "CalibratedParameter",
    "CalibratedParameterName",
    "CalibrationProfile",
    "CalibrationProvenance",
]
