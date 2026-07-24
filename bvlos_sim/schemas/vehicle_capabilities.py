"""Vehicle capability schema models."""

from pydantic import BaseModel, ConfigDict, Field


class VehicleCapabilities(BaseModel):
    """Explicit estimator capabilities for action feasibility checks."""

    model_config = ConfigDict(extra="forbid")

    hover: bool = Field(
        description="Whether station-keep and vertical-hover behaviors are supported."
    )
    forward_flight: bool = Field(
        description="Whether forward-flight wind-triangle transit is supported."
    )


__all__ = ["VehicleCapabilities"]
