"""2D Dubins path geometry for bank-angle-constrained path planning.

Conventions:
- Coordinates (x, y) are in metres, East-North plane (x=East, y=North).
- Heading theta is in radians, clockwise from North (0=North, pi/2=East).
- Turn radius must be positive.

The path-to-point solver finds the shortest Dubins path from a pose (x, y,
theta) to a target point (x2, y2) with unconstrained exit heading. Two
candidate path types are evaluated: RS (right arc + straight) and LS (left
arc + straight). The shorter valid path is returned.

Reference:
  Dubins, L. E. (1957). On curves of minimal length with a constraint on
  average curvature. American Journal of Mathematics, 79(3), 497-516.
"""

import math
from dataclasses import dataclass

from pyproj import Geod


@dataclass(frozen=True)
class DubinsPath:
    center_x: float
    center_y: float
    radial_start_rad: float
    signed_arc_angle_rad: float
    tangent_x: float
    tangent_y: float
    target_x: float
    target_y: float
    turn_radius_m: float
    straight_length_m: float

    @property
    def arc_length_m(self) -> float:
        return self.turn_radius_m * abs(self.signed_arc_angle_rad)

    @property
    def total_length_m(self) -> float:
        return self.arc_length_m + self.straight_length_m


@dataclass(frozen=True)
class DubinsPathSegment:
    midpoint_x: float
    midpoint_y: float
    track_deg: float
    length_m: float


def _right_center(x: float, y: float, theta: float, r: float) -> tuple[float, float]:
    """Centre of the minimum-radius right turn circle at pose (x, y, theta)."""
    return x + r * math.cos(theta), y - r * math.sin(theta)


def _left_center(x: float, y: float, theta: float, r: float) -> tuple[float, float]:
    """Centre of the minimum-radius left turn circle at pose (x, y, theta)."""
    return x - r * math.cos(theta), y + r * math.sin(theta)


def _rs_path_length(
    x1: float,
    y1: float,
    theta1: float,
    x2: float,
    y2: float,
    r: float,
) -> float | None:
    """RS (right arc + straight) Dubins path length to point (x2, y2).

    Returns None when the target lies inside the right turn circle (no
    forward straight segment is possible in that configuration).
    """
    path = _rs_path(x1, y1, theta1, x2, y2, r)
    return None if path is None else path.total_length_m


def _rs_path(
    x1: float,
    y1: float,
    theta1: float,
    x2: float,
    y2: float,
    r: float,
) -> DubinsPath | None:
    cx, cy = _right_center(x1, y1, theta1, r)
    dx, dy = x2 - cx, y2 - cy
    d = math.hypot(dx, dy)
    if d < r:
        return None

    phi = math.acos(r / d)
    alpha_exit = math.atan2(dy, dx) + phi
    alpha_start = math.atan2(y1 - cy, x1 - cx)
    arc_angle = (alpha_start - alpha_exit) % math.tau
    straight = math.sqrt(d * d - r * r)
    tangent_x = cx + r * math.cos(alpha_exit)
    tangent_y = cy + r * math.sin(alpha_exit)
    return DubinsPath(
        center_x=cx,
        center_y=cy,
        radial_start_rad=alpha_start,
        signed_arc_angle_rad=-arc_angle,
        tangent_x=tangent_x,
        tangent_y=tangent_y,
        target_x=x2,
        target_y=y2,
        turn_radius_m=r,
        straight_length_m=straight,
    )


def _ls_path_length(
    x1: float,
    y1: float,
    theta1: float,
    x2: float,
    y2: float,
    r: float,
) -> float | None:
    """LS (left arc + straight) Dubins path length to point (x2, y2).

    Returns None when the target lies inside the left turn circle.
    """
    path = _ls_path(x1, y1, theta1, x2, y2, r)
    return None if path is None else path.total_length_m


def _ls_path(
    x1: float,
    y1: float,
    theta1: float,
    x2: float,
    y2: float,
    r: float,
) -> DubinsPath | None:
    cx, cy = _left_center(x1, y1, theta1, r)
    dx, dy = x2 - cx, y2 - cy
    d = math.hypot(dx, dy)
    if d < r:
        return None

    phi = math.acos(r / d)
    alpha_exit = math.atan2(dy, dx) - phi
    alpha_start = math.atan2(y1 - cy, x1 - cx)
    arc_angle = (alpha_exit - alpha_start) % math.tau
    straight = math.sqrt(d * d - r * r)
    tangent_x = cx + r * math.cos(alpha_exit)
    tangent_y = cy + r * math.sin(alpha_exit)
    return DubinsPath(
        center_x=cx,
        center_y=cy,
        radial_start_rad=alpha_start,
        signed_arc_angle_rad=arc_angle,
        tangent_x=tangent_x,
        tangent_y=tangent_y,
        target_x=x2,
        target_y=y2,
        turn_radius_m=r,
        straight_length_m=straight,
    )


def dubins_path_to_point(
    x: float,
    y: float,
    heading_rad: float,
    target_x: float,
    target_y: float,
    turn_radius_m: float,
) -> DubinsPath | None:
    """Return the shortest materializable arc-plus-straight path to a point."""

    if turn_radius_m <= 0.0:
        return None
    candidates = [
        path
        for path in (
            _rs_path(x, y, heading_rad, target_x, target_y, turn_radius_m),
            _ls_path(x, y, heading_rad, target_x, target_y, turn_radius_m),
        )
        if path is not None
    ]
    return min(candidates, key=lambda path: path.total_length_m, default=None)


def dubins_path_to_point_m(
    x: float,
    y: float,
    heading_rad: float,
    target_x: float,
    target_y: float,
    turn_radius_m: float,
) -> float:
    """Shortest Dubins path length from pose (x, y, heading) to a target point.

    The exit heading at the target is unconstrained. RS (right arc + straight)
    and LS (left arc + straight) path types are evaluated; the shorter valid
    path is returned.

    Coordinates are in metres in the East-North plane (x=East, y=North).
    Heading is in radians, clockwise from North.

    Falls back to straight-line Euclidean distance when neither path type is
    geometrically available (target inside both turn circles), which does not
    occur in practice for divert distances far exceeding the turn radius.
    """
    if turn_radius_m <= 0.0:
        return math.hypot(target_x - x, target_y - y)

    path = dubins_path_to_point(
        x,
        y,
        heading_rad,
        target_x,
        target_y,
        turn_radius_m,
    )
    if path is None:
        return math.hypot(target_x - x, target_y - y)
    return path.total_length_m


def sample_dubins_path(
    path: DubinsPath,
    *,
    max_segment_length_m: float,
) -> tuple[DubinsPathSegment, ...]:
    """Sample a materialized Dubins path into track-aligned midpoint segments."""

    segments: list[DubinsPathSegment] = []
    if path.arc_length_m > 0.0:
        arc_segment_count = max(
            1,
            math.ceil(path.arc_length_m / max_segment_length_m),
        )
        arc_segment_length_m = path.arc_length_m / arc_segment_count
        for index in range(arc_segment_count):
            radial_angle = path.radial_start_rad + path.signed_arc_angle_rad * (
                (index + 0.5) / arc_segment_count
            )
            midpoint_x = path.center_x + path.turn_radius_m * math.cos(radial_angle)
            midpoint_y = path.center_y + path.turn_radius_m * math.sin(radial_angle)
            if path.signed_arc_angle_rad < 0.0:
                tangent_standard_rad = radial_angle - math.pi / 2.0
            else:
                tangent_standard_rad = radial_angle + math.pi / 2.0
            track_deg = math.degrees(math.pi / 2.0 - tangent_standard_rad) % 360.0
            segments.append(
                DubinsPathSegment(
                    midpoint_x=midpoint_x,
                    midpoint_y=midpoint_y,
                    track_deg=track_deg,
                    length_m=arc_segment_length_m,
                )
            )

    if path.straight_length_m > 0.0:
        straight_segment_count = max(
            1,
            math.ceil(path.straight_length_m / max_segment_length_m),
        )
        segment_dx = path.target_x - path.tangent_x
        segment_dy = path.target_y - path.tangent_y
        straight_track_deg = math.degrees(math.atan2(segment_dx, segment_dy)) % 360.0
        for index in range(straight_segment_count):
            fraction = (index + 0.5) / straight_segment_count
            segments.append(
                DubinsPathSegment(
                    midpoint_x=path.tangent_x + segment_dx * fraction,
                    midpoint_y=path.tangent_y + segment_dy * fraction,
                    track_deg=straight_track_deg,
                    length_m=path.straight_length_m / straight_segment_count,
                )
            )
    return tuple(segments)


def geodesic_dubins_path_to_point_m(
    geod: Geod,
    *,
    start_lat: float,
    start_lon: float,
    heading_deg: float,
    target_lat: float,
    target_lon: float,
    turn_radius_m: float,
) -> float:
    """Return a local-tangent-plane Dubins distance between geodetic points."""

    forward_azimuth_deg, _, distance_m = geod.inv(
        start_lon,
        start_lat,
        target_lon,
        target_lat,
    )
    bearing_rad = math.radians(forward_azimuth_deg)
    target_east_m = distance_m * math.sin(bearing_rad)
    target_north_m = distance_m * math.cos(bearing_rad)
    return dubins_path_to_point_m(
        0.0,
        0.0,
        math.radians(heading_deg),
        target_east_m,
        target_north_m,
        turn_radius_m,
    )
