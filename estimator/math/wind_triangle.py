"""Pure wind-triangle math utilities."""

from math import asin, cos, degrees, radians, sin, sqrt

from pydantic import BaseModel, ConfigDict


def normalize_deg(angle_deg: float) -> float:
    """Normalize heading angle to [0, 360)."""

    return angle_deg % 360.0


def normalize_signed(angle_deg: float) -> float:
    """Normalize signed angle to [-180, 180)."""

    wrapped = (angle_deg + 180.0) % 360.0 - 180.0
    if wrapped == -180.0:
        return 180.0
    return wrapped


class WindTriangleSolution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_heading_deg: float
    crab_angle_deg: float
    groundspeed_mps: float
    wind_along_track_mps: float
    wind_cross_track_mps: float


def solve_wind_triangle(
    *,
    track_deg: float,
    tas_mps: float,
    wind_east_mps: float,
    wind_north_mps: float,
) -> WindTriangleSolution | None:
    """Solve wind-triangle for required heading and resulting groundspeed.

    Returns None when no triangle solution exists (including tas_mps == 0).
    """
    if tas_mps == 0.0:
        return None

    track_rad = radians(track_deg)
    track_e = sin(track_rad)
    track_n = cos(track_rad)

    right_e = cos(track_rad)
    right_n = -sin(track_rad)

    wind_along = wind_east_mps * track_e + wind_north_mps * track_n
    wind_cross = wind_east_mps * right_e + wind_north_mps * right_n

    required_air_cross = -wind_cross
    if abs(required_air_cross) > tas_mps:
        return None

    ratio = max(-1.0, min(1.0, required_air_cross / tas_mps))
    wca_rad = asin(ratio)
    air_along = sqrt(max(0.0, tas_mps**2 - required_air_cross**2))
    groundspeed = air_along + wind_along

    required_heading_deg = normalize_deg(track_deg + degrees(wca_rad))
    crab_angle_deg = normalize_signed(required_heading_deg - track_deg)

    return WindTriangleSolution(
        required_heading_deg=required_heading_deg,
        crab_angle_deg=crab_angle_deg,
        groundspeed_mps=groundspeed,
        wind_along_track_mps=wind_along,
        wind_cross_track_mps=wind_cross,
    )
