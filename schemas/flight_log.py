"""Normalized flight trace schema models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FLIGHT_TRACE_SCHEMA_VERSION = "flight-trace.v1"


class FlightTraceRecord(BaseModel):
    """One timestamped sample in a normalized flight trace."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    timestamp_s: float = Field(
        ge=0.0,
        description="Elapsed flight time in seconds from trace start.",
    )
    lat_deg: float = Field(
        ge=-90.0,
        le=90.0,
        description="WGS-84 latitude in decimal degrees.",
    )
    lon_deg: float = Field(
        ge=-180.0,
        le=180.0,
        description="WGS-84 longitude in decimal degrees.",
    )
    alt_amsl_m: float | None = Field(
        default=None, description="Altitude AMSL in metres, if available."
    )
    groundspeed_mps: float | None = Field(
        default=None, ge=0.0, description="Groundspeed in m/s, if available."
    )
    heading_deg: float | None = Field(
        default=None,
        ge=0.0,
        le=360.0,
        description="Ground course in true degrees clockwise from north, if available.",
    )
    battery_voltage_v: float | None = Field(
        default=None, description="Battery voltage in volts, if available."
    )
    battery_current_a: float | None = Field(
        default=None, description="Battery current draw in amps, if available."
    )
    battery_remaining_pct: float | None = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Battery remaining percent (0–100), if available.",
    )
    flight_mode: str | None = Field(
        default=None, description="Autopilot flight mode name, if available."
    )
    wind_east_mps: float | None = Field(
        default=None,
        description="Estimated wind east component in m/s (EN frame), if available.",
    )
    wind_north_mps: float | None = Field(
        default=None,
        description="Estimated wind north component in m/s (EN frame), if available.",
    )
    mission_item_index: int | None = Field(
        default=None, ge=0, description="Active mission item index, if available."
    )


class FlightTraceProvenance(BaseModel):
    """Provenance metadata linking a trace to its raw source."""

    model_config = ConfigDict(extra="forbid")

    source_format: str = Field(
        min_length=1, description="Source log format identifier."
    )
    raw_log_sha256: str = Field(
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 digest of the raw log file.",
    )
    raw_log_filename: str = Field(
        min_length=1, description="Basename of the original log file."
    )
    tool_version: str = Field(
        min_length=1, description="bvlos-sim version used for ingestion."
    )
    parsing_assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions applied during log parsing.",
    )
    missing_fields: list[str] = Field(
        default_factory=list,
        description="Normalized fields absent from this log.",
    )


class FlightTraceMissionRef(BaseModel):
    """Optional reference to a planned mission paired with this trace."""

    model_config = ConfigDict(extra="forbid")

    mission_file: str = Field(
        min_length=1, description="Path or filename of the paired mission YAML."
    )
    mission_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 of the paired mission file, if available.",
    )
    vehicle_file: str | None = Field(
        default=None, description="Path or filename of the paired vehicle YAML."
    )
    vehicle_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-fA-F0-9]{64}$",
        description="SHA-256 of the paired vehicle file, if available.",
    )


class NormalizedFlightTrace(BaseModel):
    """Versioned normalized flight trace artifact."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["flight-trace.v1"] = Field(
        description="Flight trace schema version."
    )
    trace_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable trace identifier.",
    )
    provenance: FlightTraceProvenance = Field(
        description="Provenance linking this trace to its raw source."
    )
    mission_ref: FlightTraceMissionRef | None = Field(
        default=None, description="Optional paired mission reference."
    )
    records: list[FlightTraceRecord] = Field(
        default_factory=list,
        description="Normalized trace records in chronological order.",
    )

    @model_validator(mode="after")
    def validate_record_chronology(self) -> "NormalizedFlightTrace":
        for previous, following in zip(self.records, self.records[1:], strict=False):
            if following.timestamp_s <= previous.timestamp_s:
                raise ValueError(
                    "flight trace record timestamps must be strictly increasing"
                )
        return self


__all__ = [
    "FLIGHT_TRACE_SCHEMA_VERSION",
    "FlightTraceMissionRef",
    "FlightTraceProvenance",
    "FlightTraceRecord",
    "NormalizedFlightTrace",
]
