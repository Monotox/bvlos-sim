"""Monte Carlo uncertainty result models."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bvlos_sim.estimator.core.results import MissionEstimate


class SampledOutputStats(BaseModel):
    """Descriptive statistics over sampled scalar outputs."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    count: int = Field(
        ge=1, description="Number of samples contributing to these statistics."
    )
    mean: float = Field(description="Arithmetic mean.")
    std: float = Field(
        ge=0.0,
        description="Sample standard deviation (0 when count == 1).",
    )
    min: float = Field(description="Minimum observed value.")
    p5: float = Field(description="5th percentile.")
    p50: float = Field(description="50th percentile (median).")
    p95: float = Field(description="95th percentile.")
    max: float = Field(description="Maximum observed value.")

    @model_validator(mode="after")
    def validate_ordering(self) -> "SampledOutputStats":
        if not self.min <= self.p5 <= self.p50 <= self.p95 <= self.max:
            raise ValueError("sample percentiles must be ordered within min/max")
        if not self.min <= self.mean <= self.max:
            raise ValueError("sample mean must be within min/max")
        if self.count == 1 and not math.isclose(self.std, 0.0, abs_tol=1e-12):
            raise ValueError("sample standard deviation must be 0 when count is 1")
        return self


class MonteCarloResult(BaseModel):
    """Aggregated results from a seeded diagnostic parameter sweep.

    The baseline estimate is the deterministic estimate run before sampling
    with the original mission and vehicle profiles and no parameter perturbation.
    Summary statistics are conditioned on modeled-pass samples only.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    uncertainty_id: str = Field(description="Identifier from the uncertainty plan.")
    analysis_scope: Literal["diagnostic_parameter_sweep"] = "diagnostic_parameter_sweep"
    operational_feasibility_assessed: Literal[False] = False
    distributions_conditioned_on_modeled_pass: Literal[True] = True
    seed: int = Field(description="RNG seed used for sampling.")
    sample_count: int = Field(
        ge=1,
        description="Total number of samples requested.",
    )
    modeled_pass_sample_count: int = Field(
        ge=0,
        description=(
            "Samples whose deterministic estimator run returned SUCCESS and "
            "a complete energy result."
        ),
    )
    infeasible_sample_count: int = Field(
        ge=0,
        description="Samples whose deterministic estimator run was infeasible.",
    )
    failed_sample_count: int = Field(
        ge=0,
        description="Samples whose deterministic estimator run returned ERROR.",
    )
    modeled_constraint_pass_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of evaluated samples with a modeled-pass result. Failed "
            "samples are excluded. This diagnostic is not an operational, "
            "control, spatial-coverage, or landing probability."
        ),
    )
    total_time_s: SampledOutputStats | None = Field(
        default=None,
        description="Mission-time distribution over modeled-pass samples only.",
    )
    reserve_at_mission_end_wh: SampledOutputStats | None = Field(
        default=None,
        description=(
            "Modeled mission-end energy in Wh over modeled-pass samples only. "
            "This does not assert that a sample landed."
        ),
    )
    reserve_at_mission_end_percent: SampledOutputStats | None = Field(
        default=None,
        description=(
            "Modeled mission-end energy percentage over modeled-pass samples only."
        ),
    )
    baseline: MissionEstimate = Field(
        description="Deterministic baseline estimate with no parameter perturbation."
    )

    @model_validator(mode="after")
    def validate_accounting_and_conditioning(self) -> "MonteCarloResult":
        accounted = (
            self.modeled_pass_sample_count
            + self.infeasible_sample_count
            + self.failed_sample_count
        )
        if accounted != self.sample_count:
            raise ValueError(
                "modeled_pass_sample_count + infeasible_sample_count + "
                "failed_sample_count must equal sample_count"
            )
        evaluated = self.modeled_pass_sample_count + self.infeasible_sample_count
        expected_rate = (
            self.modeled_pass_sample_count / evaluated if evaluated else None
        )
        if expected_rate is None:
            if self.modeled_constraint_pass_rate is not None:
                raise ValueError(
                    "modeled_constraint_pass_rate must be None when no samples "
                    "were evaluated"
                )
        elif self.modeled_constraint_pass_rate is None or not math.isclose(
            self.modeled_constraint_pass_rate,
            expected_rate,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError(
                "modeled_constraint_pass_rate must equal modeled passes divided "
                "by evaluated samples"
            )
        for name in (
            "total_time_s",
            "reserve_at_mission_end_wh",
            "reserve_at_mission_end_percent",
        ):
            stats = getattr(self, name)
            if stats is not None and stats.count != self.modeled_pass_sample_count:
                raise ValueError(f"{name}.count must equal modeled_pass_sample_count")
        return self
