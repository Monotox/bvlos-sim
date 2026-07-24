"""Batch manifest schema for multi-run estimate, scenario, and propagate jobs."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_RUN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"

RunType = Literal["estimate", "scenario", "propagate"]

# run_type -> (required run fields, forbidden run fields).
_RUN_TYPE_FIELDS: dict[RunType, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "estimate": (("mission", "vehicle"), ("scenario", "plan")),
    "scenario": (("scenario",), ("mission", "vehicle", "plan")),
    "propagate": (("plan",), ("mission", "vehicle", "scenario")),
}


class BatchRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        pattern=_RUN_ID_PATTERN,
        description=(
            "Stable run identifier. Used as the output filename stem when "
            "--output-dir is set. Must contain only letters, digits, hyphens, "
            "and underscores."
        ),
    )
    mission: Path | None = Field(
        default=None, description="Mission file (estimate runs)."
    )
    vehicle: Path | None = Field(
        default=None, description="Vehicle profile file (estimate runs)."
    )
    scenario: Path | None = Field(
        default=None, description="Scenario file (scenario runs)."
    )
    plan: Path | None = Field(
        default=None, description="Stochastic plan file (propagate runs)."
    )


class BatchManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["batch.v1"]
    run_type: RunType = Field(
        default="estimate",
        description=(
            "Job type for every run in the manifest: estimate (default), "
            "scenario, or propagate. Absent means estimate, so existing "
            "manifests stay valid."
        ),
    )
    runs: list[BatchRun] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "BatchManifest":
        required, forbidden = _RUN_TYPE_FIELDS[self.run_type]
        seen: set[str] = set()
        for run in self.runs:
            if run.id in seen:
                raise ValueError(
                    f"Duplicate run id '{run.id}'. Each run in a batch manifest "
                    "must have a unique id."
                )
            seen.add(run.id)
            missing = [name for name in required if getattr(run, name) is None]
            if missing:
                raise ValueError(
                    f"Run '{run.id}' is a {self.run_type} run and must set "
                    f"{', '.join(missing)}."
                )
            present_forbidden = [
                name for name in forbidden if getattr(run, name) is not None
            ]
            if present_forbidden:
                raise ValueError(
                    f"Run '{run.id}' is a {self.run_type} run and must not set "
                    f"{', '.join(present_forbidden)}."
                )
        return self
