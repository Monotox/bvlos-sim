"""Public estimator options."""

from pydantic import BaseModel, ConfigDict, Field

from bvlos_sim.estimator.core.enums import FidelityMode


class EstimationOptions(BaseModel):
    """Runtime estimator options.

    Every non-null runtime field takes precedence over the corresponding
    mission-level persisted setting. Unset fields inherit the mission setting
    (or the library default when no mission setting exists).
    """

    model_config = ConfigDict(extra="forbid")

    wind_east_mps: float | None = None
    wind_north_mps: float | None = None
    min_groundspeed_mps: float | None = Field(default=None, gt=0)
    max_segment_length_m: float | None = Field(default=None, gt=0)
    fidelity: FidelityMode | None = None


__all__ = [
    "EstimationOptions",
    "FidelityMode",
]
