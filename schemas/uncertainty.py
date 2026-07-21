"""Diagnostic uncertainty-plan schema for Monte Carlo sampling (v2)."""

import math
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NormalDistribution(BaseModel):
    """Sample from a normal (Gaussian) distribution."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    kind: Literal["normal"]
    mean: float = Field(description="Distribution mean.")
    std: float = Field(gt=0, description="Standard deviation (must be > 0).")


class UniformDistribution(BaseModel):
    """Sample uniformly from [low, high)."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    kind: Literal["uniform"]
    low: float = Field(description="Lower bound (inclusive).")
    high: float = Field(description="Upper bound (exclusive).")

    @model_validator(mode="after")
    def validate_range(self) -> "UniformDistribution":
        if self.high <= self.low:
            raise ValueError("high must be greater than low")
        return self


UncertaintyDistribution = Annotated[
    NormalDistribution | UniformDistribution,
    Field(discriminator="kind"),
]


class UncertaintyParameters(BaseModel):
    """Per-parameter uncertainty distributions.

    At least one parameter must be specified. Unset parameters are held at
    their deterministic values for every sample.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    wind_east_mps: UncertaintyDistribution | None = Field(
        default=None,
        description=(
            "East wind component distribution in m/s. A sampled value overrides only "
            "the east component; the deterministic provider still supplies north wind."
        ),
    )
    wind_north_mps: UncertaintyDistribution | None = Field(
        default=None,
        description=(
            "North wind component distribution in m/s. A sampled value overrides only "
            "the north component; the deterministic provider still supplies east wind."
        ),
    )
    cruise_speed_mps: UncertaintyDistribution | None = Field(
        default=None,
        description=(
            "Cruise speed distribution in m/s. Sampled values override "
            "mission.defaults.cruise_speed_mps for that sample."
        ),
    )
    cruise_power_w: UncertaintyDistribution | None = Field(
        default=None,
        description=(
            "Cruise power distribution in W. Sampled values override "
            "vehicle.energy.cruise_power_w for that sample."
        ),
    )
    battery_capacity_wh: UncertaintyDistribution | None = Field(
        default=None,
        description=(
            "Battery capacity distribution in Wh. Sampled values override "
            "vehicle.energy.battery_capacity_wh for that sample."
        ),
    )

    @model_validator(mode="after")
    def validate_at_least_one(self) -> "UncertaintyParameters":
        fields = (
            self.wind_east_mps,
            self.wind_north_mps,
            self.cruise_speed_mps,
            self.cruise_power_w,
            self.battery_capacity_wh,
        )
        if not any(f is not None for f in fields):
            raise ValueError("at least one uncertainty parameter must be specified")
        return self


class UncertaintyPlan(BaseModel):
    """Top-level configuration for a diagnostic Monte Carlo parameter sweep.

    References existing mission and vehicle files. All other deterministic
    assets (terrain, wind-grid, geofences, landing zones) are loaded from
    the mission file's asset references by the CLI.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["uncertainty.v2"] = Field(
        description="Schema version identifier."
    )
    uncertainty_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable identifier for this uncertainty run.",
    )
    mission_file: str = Field(
        min_length=1,
        description="Path to the mission YAML file (relative to this file).",
    )
    vehicle_file: str = Field(
        min_length=1,
        description="Path to the vehicle YAML file (relative to this file).",
    )
    samples: int = Field(
        ge=1,
        le=10_000,
        description="Number of Monte Carlo samples to draw.",
    )
    seed: int = Field(description="RNG seed for reproducible sampling.")
    parameters: UncertaintyParameters = Field(
        description="Per-parameter uncertainty distributions."
    )

    @model_validator(mode="after")
    def validate_physical_parameter_support(self) -> "UncertaintyPlan":
        """Require bounded positive support for positive physical quantities."""
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
                    "distribution in uncertainty.v2; an untruncated normal has "
                    "nonphysical negative support"
                )
            if distribution.low <= 0:
                raise ValueError(f"parameters.{name}.low must be greater than 0")
        return self
