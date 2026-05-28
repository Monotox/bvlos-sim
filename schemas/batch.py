"""Batch manifest schema for multi-run estimate workflows."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_RUN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"


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
    mission: Path
    vehicle: Path


class BatchManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["batch.v1"]
    runs: list[BatchRun] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_run_ids(self) -> "BatchManifest":
        seen: set[str] = set()
        for run in self.runs:
            if run.id in seen:
                raise ValueError(
                    f"Duplicate run id '{run.id}'. Each run in a batch manifest must have a unique id."
                )
            seen.add(run.id)
        return self
