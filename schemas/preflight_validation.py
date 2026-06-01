"""Preflight validation report schema models.

A preflight validation report is a deterministic, machine-readable result of a
``--validate-only`` run: per-file ok/error with a stable error stage and code,
plus an overall pass flag. It lets a backend validate a command's inputs —
including referenced GeoJSON/terrain/population assets — before queuing a long
job, and parse the outcome instead of scraping plain-text "OK" lines.

The report carries no wall-clock timestamp (``generated_at`` is always ``None``)
so the same inputs always produce byte-identical output.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PREFLIGHT_VALIDATION_SCHEMA_VERSION = "preflight-validation.v1"


class PreflightError(BaseModel):
    """Structured failure detail for a single file check."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(
        min_length=1,
        description="Stable machine token, e.g. SCHEMA_VALIDATION_FAILED or ASSET_FILE_MISSING.",
    )
    message: str = Field(min_length=1, description="Human-readable one-line summary.")
    detail: dict[str, Any] | None = Field(
        default=None,
        description="Optional structured detail, e.g. a validation error summary.",
    )


class FileCheck(BaseModel):
    """Validation outcome for one input or referenced asset file."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(description="File name as referenced, not an absolute path.")
    role: str = Field(
        min_length=1,
        description="Logical role: mission, vehicle, scenario, geofence, terrain, …",
    )
    ok: bool = Field(description="True when the file loaded and validated.")
    stage: str | None = Field(
        default=None,
        description="Failure stage when not ok: schema, asset-load, or reference.",
    )
    error: PreflightError | None = Field(
        default=None, description="Failure detail; None when ok."
    )


class PreflightValidationReport(BaseModel):
    """Deterministic per-file preflight validation envelope."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["preflight-validation.v1"] = Field(
        description="Preflight validation schema version."
    )
    command: str = Field(
        min_length=1, description="Command that produced the report, e.g. estimate."
    )
    ok: bool = Field(description="Logical AND over every file check.")
    files: list[FileCheck] = Field(
        default_factory=list, description="Per-file validation outcomes."
    )
    generated_at: None = Field(
        default=None,
        description="Always null — the report is deterministic and carries no wall clock.",
    )


__all__ = [
    "PREFLIGHT_VALIDATION_SCHEMA_VERSION",
    "FileCheck",
    "PreflightError",
    "PreflightValidationReport",
]
