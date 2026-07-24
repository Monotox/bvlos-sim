"""Diagnostic stochastic propagation plan and result schemas (stochastic.v2)."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from estimator.core.results import MissionEstimate
from estimator.core.uncertainty import SampledOutputStats
from schemas.uncertainty import (
    NormalDistribution,
    UncertaintyParameters,
    UniformDistribution,
)


_MIN_DT_S = 0.001


class StochasticPropagationPlan(BaseModel):
    """Inputs for a bounded, open-loop stochastic diagnostic.

    Version 2 deliberately excludes process-wind and closed-loop flight
    dynamics.  Those models have not been validated sufficiently to support
    a spatial or operational feasibility claim.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["stochastic.v2"]
    propagation_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable identifier for this propagation run.",
    )
    mission_file: str = Field(min_length=1)
    vehicle_file: str = Field(min_length=1)
    dt_s: float = Field(
        default=1.0,
        ge=_MIN_DT_S,
        description=(
            "Propagation step. Bounded below so a tiny value cannot make the "
            "timeline consume unbounded time and memory."
        ),
    )
    samples: int = Field(ge=1, le=10_000)
    seed: int
    wind_process_noise_std_mps: Literal[0.0] = Field(
        default=0.0,
        description=(
            "Compatibility field; must be 0.0. Process-wind propagation is "
            "unsupported because no validated guidance/airspeed response model "
            "is available. Sample a constant wind component instead."
        ),
    )
    parameters: UncertaintyParameters

    @model_validator(mode="after")
    def validate_physical_parameter_support(self) -> "StochasticPropagationPlan":
        """Reject distributions that can silently produce nonphysical values."""
        for name in ("cruise_speed_mps", "cruise_power_w", "battery_capacity_wh"):
            distribution = getattr(self.parameters, name)
            if distribution is None:
                continue
            values = (
                (distribution.mean, distribution.std)
                if isinstance(distribution, NormalDistribution)
                else (distribution.low, distribution.high)
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"parameters.{name} values must be finite")
            if isinstance(distribution, NormalDistribution):
                raise ValueError(
                    f"parameters.{name} must use a bounded positive uniform "
                    "distribution in stochastic.v2; an untruncated normal has "
                    "nonphysical negative support"
                )
            if isinstance(distribution, UniformDistribution) and distribution.low <= 0:
                raise ValueError(f"parameters.{name}.low must be greater than 0")

        for name in ("wind_east_mps", "wind_north_mps"):
            distribution = getattr(self.parameters, name)
            if distribution is None:
                continue
            values = (
                (distribution.mean, distribution.std)
                if isinstance(distribution, NormalDistribution)
                else (distribution.low, distribution.high)
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError(f"parameters.{name} values must be finite")
        return self


class PropagationTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    elapsed_time_s: float
    route_position_centroid_lat_deg: float = Field(
        ge=-90.0,
        le=90.0,
        description=(
            "Spherical centroid of each sample's interpolated reference-route "
            "position; not a simulated flown-position mean."
        ),
    )
    route_position_centroid_lon_deg: float = Field(
        ge=-180.0,
        le=180.0,
        description=(
            "Longitude of the spherical reference-route centroid; not a "
            "simulated flown-position mean."
        ),
    )
    energy_remaining_wh: SampledOutputStats
    conditional_reserve_violation_rate: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Reserve-violation fraction among samples whose deterministic "
            "estimator run passed. Infeasible and failed samples do not "
            "contribute to this conditional timeline statistic."
        ),
    )
    contributing_sample_count: int = Field(
        ge=1,
        description="Number of modeled-pass samples contributing at this time.",
    )


class EstimationErrorTimelinePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    elapsed_time_s: float
    position_error_m: SampledOutputStats
    energy_error_wh: SampledOutputStats


class CrossTrackStats(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    elapsed_time_s: float
    cross_track_error_m: SampledOutputStats
    along_track_error_m: SampledOutputStats
    path_length_excess_m: SampledOutputStats


class StochasticPropagationResult(BaseModel):
    """Open-loop diagnostic output; never an operational feasibility verdict."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    propagation_id: str
    analysis_scope: Literal["diagnostic_open_loop_parameter_sweep"] = (
        "diagnostic_open_loop_parameter_sweep"
    )
    operational_feasibility_assessed: Literal[False] = False
    distributions_conditioned_on_modeled_pass: Literal[True] = True
    seed: int
    dt_s: float
    requested_sample_count: int = Field(
        ge=1,
        description="Number of samples requested by the stochastic plan.",
    )
    sample_count: int = Field(
        ge=0,
        description=(
            "Number of samples whose deterministic estimator run passed and "
            "therefore contributes to conditional distributions."
        ),
    )
    infeasible_sample_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Completed samples with a modeled infeasible outcome. Includes the "
            "spatial_infeasible_count subset and is counted in "
            "modeled_constraint_pass_rate."
        ),
    )
    failed_sample_count: int = Field(
        default=0,
        ge=0,
        description="Samples that raised an exception and were skipped.",
    )
    spatial_infeasible_count: int = Field(
        default=0,
        ge=0,
        description=(
            "Samples where the route was spatially infeasible "
            "(geofence conflict or landing-zone failure). "
            "Subset of infeasible_sample_count."
        ),
    )
    timeline: list[PropagationTimelinePoint]
    estimation_error_timeline: list[EstimationErrorTimelinePoint] = Field(
        default_factory=list
    )
    cross_track_timeline: list[CrossTrackStats] = Field(
        default_factory=list,
        description=(
            "Always empty in stochastic.v2. Closed-loop controller propagation "
            "is rejected pending a validated model."
        ),
    )
    reserve_at_mission_end_wh: SampledOutputStats | None = Field(
        description=(
            "Modeled mission-end energy distribution over modeled-pass samples "
            "only; infeasible and failed samples are excluded. This does not "
            "assert that a sample landed."
        )
    )
    modeled_constraint_pass_rate: float | None = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of evaluated samples whose deterministic estimator run "
            "passed its supplied constraints and reserve checks. Failed samples "
            "are excluded. This is diagnostic and is not a landing, control, "
            "spatial-coverage, or operational-feasibility probability."
        ),
    )
    baseline: MissionEstimate

    @model_validator(mode="after")
    def validate_accounting_and_scope(self) -> "StochasticPropagationResult":
        accounted = (
            self.sample_count + self.infeasible_sample_count + self.failed_sample_count
        )
        if accounted != self.requested_sample_count:
            raise ValueError(
                "sample_count + infeasible_sample_count + failed_sample_count "
                "must equal requested_sample_count"
            )
        if self.spatial_infeasible_count > self.infeasible_sample_count:
            raise ValueError(
                "spatial_infeasible_count must be a subset of infeasible_sample_count"
            )
        if self.cross_track_timeline:
            raise ValueError("cross_track_timeline must be empty in stochastic.v2")
        evaluated = self.sample_count + self.infeasible_sample_count
        expected_rate = self.sample_count / evaluated if evaluated else None
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
                "modeled_constraint_pass_rate must equal sample_count divided "
                "by evaluated samples"
            )
        return self
