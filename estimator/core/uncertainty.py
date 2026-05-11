"""Monte Carlo uncertainty result models."""

from pydantic import BaseModel, ConfigDict, Field

from estimator.core.results import MissionEstimate


class SampledOutputStats(BaseModel):
    """Descriptive statistics over sampled scalar outputs."""

    model_config = ConfigDict(extra="forbid")

    count: int = Field(description="Number of samples contributing to these statistics.")
    mean: float = Field(description="Arithmetic mean.")
    std: float = Field(description="Sample standard deviation (0 when count == 1).")
    min: float = Field(description="Minimum observed value.")
    p5: float = Field(description="5th percentile.")
    p50: float = Field(description="50th percentile (median).")
    p95: float = Field(description="95th percentile.")
    max: float = Field(description="Maximum observed value.")


class MonteCarloResult(BaseModel):
    """Aggregated results from a seeded Monte Carlo uncertainty run.

    The baseline estimate is the deterministic estimate run before sampling
    with the original mission and vehicle profiles and no parameter perturbation.
    Summary statistics are computed only over completed samples.
    """

    model_config = ConfigDict(extra="forbid")

    uncertainty_id: str = Field(description="Identifier from the uncertainty plan.")
    seed: int = Field(description="RNG seed used for sampling.")
    sample_count: int = Field(description="Total number of samples requested.")
    completed_sample_count: int = Field(
        description="Samples that produced a result without error."
    )
    failed_sample_count: int = Field(
        description="Samples that raised an exception and were skipped."
    )
    feasibility_rate: float | None = Field(
        default=None,
        description=(
            "Fraction of completed samples where energy.is_feasible is True. "
            "None when no completed sample produced an energy estimate."
        ),
    )
    total_time_s: SampledOutputStats | None = Field(
        default=None,
        description="Distribution of total mission time across completed samples.",
    )
    reserve_at_landing_wh: SampledOutputStats | None = Field(
        default=None,
        description=(
            "Distribution of energy reserve at landing in Wh across completed samples "
            "that produced an energy estimate."
        ),
    )
    reserve_at_landing_percent: SampledOutputStats | None = Field(
        default=None,
        description=(
            "Distribution of energy reserve at landing as a percentage of battery "
            "capacity across completed samples that produced an energy estimate."
        ),
    )
    baseline: MissionEstimate = Field(
        description="Deterministic baseline estimate with no parameter perturbation."
    )
