"""Vehicle performance schema models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PerformanceProfile(BaseModel):
    """Flight performance values used by route and feasibility models."""

    model_config = ConfigDict(extra="forbid")

    cruise_speed_mps: float = Field(
        gt=0,
        description=(
            "Nominal forward cruise speed. Source: QGC cruiseSpeed, autopilot "
            "parameters, or manufacturer/spec sheet."
        ),
    )
    hover_speed_mps: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Nominal multicopter forward speed. Source: QGC hoverSpeed or "
            "manufacturer/spec sheet. Required for multirotor and VTOL profiles."
        ),
    )
    max_speed_mps: float = Field(
        gt=0,
        description="Maximum commanded/allowed speed. Source: manufacturer/spec sheet.",
    )
    climb_rate_mps: float = Field(
        gt=0,
        description="Nominal climb rate used for time and energy estimates.",
    )
    descent_rate_mps: float = Field(
        gt=0,
        description="Nominal descent rate used for time and energy estimates.",
    )
    turn_radius_m: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Minimum practical turn radius for fixed-wing path planning. Required "
            "for fixed-wing and VTOL profiles."
        ),
    )
    max_wind_mps: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Maximum operational wind speed in m/s. When set, the estimator emits "
            "a MAX_WIND_EXCEEDED advisory warning on any leg where measured wind "
            "exceeds this limit. The estimator does not abort the route."
        ),
    )
    max_crab_angle_deg: float | None = Field(
        default=None,
        gt=0,
        lt=90,
        description=(
            "Optional maximum allowed crab angle in degrees. Estimator applies "
            "its own numeric validation and defaults when omitted."
        ),
    )
    max_station_keep_wind_mps: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Optional maximum wind speed for station-keep feasibility checks "
            "during loiter dwell."
        ),
    )

    @model_validator(mode="after")
    def validate_speed_relationships(self) -> "PerformanceProfile":
        speed_limits = (
            (self.cruise_speed_mps, "cruise_speed_mps"),
            (self.hover_speed_mps, "hover_speed_mps"),
        )
        for compared_speed, field_name in speed_limits:
            if compared_speed is not None and self.max_speed_mps < compared_speed:
                raise ValueError(
                    f"max_speed_mps must be greater than or equal to {field_name}"
                )
        return self


__all__ = ["PerformanceProfile"]
