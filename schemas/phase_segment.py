"""Flight phase segmentation schema models."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

PHASE_SEGMENT_SCHEMA_VERSION = "phase-segments.v1"


class TracePhase(StrEnum):
    """Flight phase labels used in segmented traces.

    Maps to estimator LegPhase values where a direct equivalent exists.
    CLIMB, DESCENT, DIVERT, and UNKNOWN have no estimator counterpart.
    """

    TAKEOFF = "takeoff"
    CLIMB = "climb"
    TRANSIT = "transit"
    LOITER = "loiter"
    DESCENT = "descent"
    LANDING = "landing"
    RTL = "rtl"
    DIVERT = "divert"
    UNKNOWN = "unknown"


class PhaseSegment(BaseModel):
    """One contiguous run of records assigned to the same flight phase."""

    model_config = ConfigDict(extra="forbid")

    phase: TracePhase = Field(description="Assigned flight phase for this segment.")
    start_index: int = Field(
        ge=0,
        description="Inclusive start index into NormalizedFlightTrace.records.",
    )
    end_index: int = Field(
        ge=0,
        description="Inclusive end index into NormalizedFlightTrace.records.",
    )
    start_time_s: float = Field(
        ge=0.0,
        description="Timestamp of the first record in this segment.",
    )
    end_time_s: float = Field(
        ge=0.0,
        description="Timestamp of the last record in this segment.",
    )
    record_count: int = Field(ge=1, description="Number of records in this segment.")
    estimator_leg_phase: str | None = Field(
        default=None,
        description="Nearest estimator LegPhase string value, if a mapping exists.",
    )

    @model_validator(mode="after")
    def _indices_ordered(self) -> PhaseSegment:
        if self.end_index < self.start_index:
            raise ValueError(
                f"end_index ({self.end_index}) must be >= start_index ({self.start_index})"
            )
        if self.end_time_s < self.start_time_s:
            raise ValueError(
                f"end_time_s ({self.end_time_s}) must be >= start_time_s ({self.start_time_s})"
            )
        return self


class SegmentationMetadata(BaseModel):
    """Metadata describing how the segmentation was produced."""

    model_config = ConfigDict(extra="forbid")

    method: str = Field(
        min_length=1,
        description="Segmentation algorithm identifier.",
    )
    source_fields_used: list[str] = Field(
        default_factory=list,
        description="Trace fields present in at least one record and available to the segmenter.",
    )
    unknown_record_count: int = Field(
        ge=0,
        description="Number of records assigned to the UNKNOWN phase.",
    )


class PhaseSegmentResult(BaseModel):
    """Versioned deterministic segmentation of a normalized flight trace."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["phase-segments.v1"] = Field(
        description="Phase segment schema version.",
    )
    trace_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="trace_id of the NormalizedFlightTrace that was segmented.",
    )
    segments: list[PhaseSegment] = Field(
        default_factory=list,
        description="Contiguous phase segments in chronological order.",
    )
    metadata: SegmentationMetadata = Field(
        description="Segmentation method and data-availability metadata.",
    )


__all__ = [
    "PHASE_SEGMENT_SCHEMA_VERSION",
    "PhaseSegment",
    "PhaseSegmentResult",
    "SegmentationMetadata",
    "TracePhase",
]
