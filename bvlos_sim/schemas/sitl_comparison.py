"""Comparison report schema models for SITL scenario validation."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from bvlos_sim.schemas.sitl import SitlJsonValue

SITL_COMPARISON_SCHEMA_VERSION = "sitl-comparison.v1"


class SitlComparisonOutcome(StrEnum):
    MATCHED = "matched"
    DRIFTED = "drifted"
    MISSING = "missing"
    SKIPPED = "skipped"
    UNSUPPORTED = "unsupported"


class SitlComparisonSummary(StrEnum):
    PASSED = "passed"
    DRIFTED = "drifted"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class SitlComparisonItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(description="Logical comparison dimension identifier.")
    outcome: SitlComparisonOutcome
    expected: SitlJsonValue = Field(
        default=None, description="Expected value or summary."
    )
    observed: SitlJsonValue = Field(
        default=None, description="Observed value or summary."
    )
    tolerance: SitlJsonValue = Field(
        default=None, description="Tolerance used, if any."
    )
    notes: str | None = Field(default=None, description="Human-readable explanation.")


class SitlComparisonReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["sitl-comparison.v1"]
    comparison_id: str = Field(min_length=1, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    evidence_id: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    summary: SitlComparisonSummary
    items: list[SitlComparisonItem] = Field(default_factory=list)
    metadata: dict[str, SitlJsonValue] = Field(default_factory=dict)


__all__ = [
    "SITL_COMPARISON_SCHEMA_VERSION",
    "SitlComparisonItem",
    "SitlComparisonOutcome",
    "SitlComparisonReport",
    "SitlComparisonSummary",
]
