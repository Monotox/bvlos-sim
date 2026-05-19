"""Batch manifest schema for multi-run estimate workflows."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class BatchRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    mission: Path
    vehicle: Path


class BatchManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal["batch.v1"]
    runs: list[BatchRun] = Field(min_length=1)
