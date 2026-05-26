"""Public estimator options."""

from pydantic import BaseModel, ConfigDict, Field

from estimator.core.enums import FidelityMode


class EstimationOptions(BaseModel):
    """Runtime estimator options.

    When mission-level persisted estimation settings exist, runtime options take
    precedence over mission values.
    """

    model_config = ConfigDict(extra="forbid")

    wind_east_mps: float = 0.0
    wind_north_mps: float = 0.0
    min_groundspeed_mps: float | None = Field(default=None, gt=0)
    max_segment_length_m: float | None = Field(default=None, gt=0)
    fidelity: FidelityMode | None = None


__all__ = [
    "EstimationOptions",
    "FidelityMode",
]
