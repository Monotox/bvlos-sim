"""Pure turn-arc geometry for fixed-wing/VTOL waypoint transitions.

A vehicle flying from track α₁ to track α₂ follows a circular arc of radius R.
The arc subtends the absolute heading change |normalize_signed(α₂ − α₁)|.

Arc length = R · |Δθ_rad|

All angles are in degrees; returned arc_length_m is in metres.
"""

from dataclasses import dataclass
from math import radians, tan

from estimator.math.wind_triangle import normalize_signed


@dataclass(frozen=True)
class TurnArcGeometry:
    turn_angle_deg: float
    arc_length_m: float
    tangent_offset_m: float


def compute_turn_arc_geometry(
    *,
    incoming_track_deg: float,
    outgoing_track_deg: float,
    radius_m: float,
) -> TurnArcGeometry:
    """Compute the arc length for a constant-radius turn between two tracks."""
    turn_angle_deg = abs(normalize_signed(outgoing_track_deg - incoming_track_deg))
    turn_angle_rad = radians(turn_angle_deg)
    arc_length_m = radius_m * turn_angle_rad
    tangent_offset_m = radius_m * tan(turn_angle_rad / 2.0)
    return TurnArcGeometry(
        turn_angle_deg=turn_angle_deg,
        arc_length_m=arc_length_m,
        tangent_offset_m=tangent_offset_m,
    )
