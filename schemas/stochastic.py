"""Stochastic propagation plan and result schemas (stochastic.v1)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from estimator.core.results import MissionEstimate
from estimator.core.uncertainty import SampledOutputStats
from schemas.uncertainty import UncertaintyParameters


class StochasticPropagationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["stochastic.v1"]
    propagation_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable identifier for this propagation run.",
    )
    mission_file: str
    vehicle_file: str
    dt_s: float = Field(default=1.0, gt=0)
    samples: int = Field(ge=1, le=10_000)
    seed: int
    wind_process_noise_std_mps: float = Field(default=0.5, ge=0.0)
    parameters: UncertaintyParameters


class PropagationTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elapsed_time_s: float
    lat_mean: float
    lon_mean: float
    energy_remaining_wh: SampledOutputStats
    p_reserve_violation: float


class EstimationErrorTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elapsed_time_s: float
    position_error_m: SampledOutputStats
    energy_error_wh: SampledOutputStats


class CrossTrackStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    elapsed_time_s: float
    cross_track_error_m: SampledOutputStats
    along_track_error_m: SampledOutputStats
    path_length_excess_m: SampledOutputStats


class StochasticPropagationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    propagation_id: str
    seed: int
    dt_s: float
    sample_count: int = Field(description="Number of samples that completed successfully.")
    failed_sample_count: int = Field(
        default=0,
        description="Samples that raised an exception and were skipped.",
    )
    spatial_infeasible_count: int = Field(
        default=0,
        description=(
            "Samples where the route was spatially infeasible "
            "(geofence conflict or landing-zone failure). "
            "Counted as infeasible in feasibility_rate."
        ),
    )
    timeline: list[PropagationTimelinePoint]
    estimation_error_timeline: list[EstimationErrorTimelinePoint] = Field(
        default_factory=list
    )
    cross_track_timeline: list[CrossTrackStats] = Field(default_factory=list)
    reserve_at_landing_wh: SampledOutputStats | None
    feasibility_rate: float
    baseline: MissionEstimate
