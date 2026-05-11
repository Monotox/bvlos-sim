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

_TWO_PI = 2.0 * math.pi


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
    cx, cy = _right_center(x1, y1, theta1, r)
    dx, dy = x2 - cx, y2 - cy
    d = math.hypot(dx, dy)
    if d < r:
        return None

    phi = math.acos(r / d)
    alpha_exit = math.atan2(dy, dx) + phi
    alpha_start = math.atan2(y1 - cy, x1 - cx)
    arc_angle = (alpha_start - alpha_exit) % _TWO_PI
    straight = math.sqrt(d * d - r * r)
    return r * arc_angle + straight


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
    cx, cy = _left_center(x1, y1, theta1, r)
    dx, dy = x2 - cx, y2 - cy
    d = math.hypot(dx, dy)
    if d < r:
        return None

    phi = math.acos(r / d)
    alpha_exit = math.atan2(dy, dx) - phi
    alpha_start = math.atan2(y1 - cy, x1 - cx)
    arc_angle = (alpha_exit - alpha_start) % _TWO_PI
    straight = math.sqrt(d * d - r * r)
    return r * arc_angle + straight


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

    rs = _rs_path_length(x, y, heading_rad, target_x, target_y, turn_radius_m)
    ls = _ls_path_length(x, y, heading_rad, target_x, target_y, turn_radius_m)

    candidates = [v for v in (rs, ls) if v is not None]
    if not candidates:
        return math.hypot(target_x - x, target_y - y)
    return min(candidates)
