"""Vehicle energy and failsafe schema models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EnergyModel(BaseModel):
    """Deterministic phase-power energy model used by estimator feasibility."""

    model_config = ConfigDict(extra="forbid")

    battery_capacity_wh: float = Field(
        gt=0,
        description="Battery capacity in watt-hours before landing reserve is held back.",
    )
    reserve_percent_default: float = Field(
        ge=0,
        le=100,
        description=(
            "Default minimum landing reserve used when a mission does not override it."
        ),
    )
    cruise_power_w: float = Field(
        gt=0,
        description="Nominal power draw during cruise.",
    )
    hover_power_w: float | None = Field(
        default=None,
        gt=0,
        description="Nominal power draw while hovering. Required for multirotor and VTOL.",
    )
    climb_power_w: float | None = Field(
        default=None,
        gt=0,
        description="Nominal power draw during climb. Falls back to cruise_power_w if omitted.",
    )
    descent_power_w: float | None = Field(
        default=None,
        gt=0,
        description="Nominal power draw during descent. Falls back to cruise_power_w if omitted.",
    )


class FailsafeProfile(BaseModel):
    """Failsafe thresholds used for advisory warnings.

    The estimator emits RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD or
    RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD warnings when the predicted
    landing reserve falls below the corresponding threshold. These are
    advisory only — the estimator does not abort the route.
    """

    model_config = ConfigDict(extra="forbid")

    low_battery_warn_percent: float = Field(
        default=30,
        ge=0,
        le=100,
        description="Warn threshold. Source: PX4/ArduPilot battery failsafe concepts.",
    )
    low_battery_abort_percent: float = Field(
        default=25,
        ge=0,
        le=100,
        description="Abort/RTL threshold used by the validator.",
    )
    emergency_land_percent: float = Field(
        default=10,
        ge=0,
        le=100,
        description="Emergency landing threshold used by the validator.",
    )

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "FailsafeProfile":
        if not (
            self.low_battery_warn_percent
            >= self.low_battery_abort_percent
            >= self.emergency_land_percent
        ):
            raise ValueError(
                "battery thresholds must be ordered as warn >= abort >= emergency land"
            )
        return self


__all__ = [
    "EnergyModel",
    "FailsafeProfile",
]
