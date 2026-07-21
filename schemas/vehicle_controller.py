"""Autopilot tracking controller profile schema."""

import math

from pydantic import BaseModel, ConfigDict, Field

from schemas.numeric import FiniteFloat


class ControllerProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    Kp_cross_track: FiniteFloat = Field(
        default=0.15,
        ge=0.0,
        description="Heading correction per metre of cross-track error (rad/m).",
    )
    Kp_along_track: FiniteFloat = Field(
        default=0.05,
        ge=0.0,
        description="Speed correction per metre of along-track error (m/s per m).",
    )
    max_heading_correction_rad: FiniteFloat = Field(
        default=math.radians(30),
        ge=0.0,
        description="Maximum heading correction magnitude in radians.",
    )
    max_speed_correction_mps: FiniteFloat = Field(
        default=2.0,
        ge=0.0,
        description="Maximum speed correction magnitude in m/s.",
    )


__all__ = ["ControllerProfile"]
