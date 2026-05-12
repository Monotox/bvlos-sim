"""Vehicle SITL schema models."""

from pydantic import BaseModel, ConfigDict, Field

from schemas.vehicle_enums import AutopilotStack


class SitlProfile(BaseModel):
    """Optional SITL backend settings used by adapter layers.

    These fields are always ignored by the deterministic estimator. The SITL
    evidence contract may copy them into simulator metadata.
    """

    model_config = ConfigDict(extra="forbid")

    backend: AutopilotStack = Field(
        description="SITL backend to launch or connect to.",
    )
    frame: str = Field(
        min_length=1,
        description="Autopilot frame/model name, for example 'quadplane' or 'x500'.",
    )
    model: str | None = Field(
        default=None,
        description="Optional simulator model name used by the backend.",
    )


__all__ = ["SitlProfile"]
