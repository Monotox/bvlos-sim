"""Proportional cross-track / along-track path-following controller model."""

import math
from dataclasses import dataclass

from schemas.vehicle_controller import ControllerProfile

_M_PER_DEG = 111_111.0


@dataclass(slots=True)
class ControllerState:
    """Mutable per-particle controller state carried across time steps."""

    true_lat: float
    true_lon: float
    cross_track_error_m: float = 0.0
    along_track_error_m: float = 0.0
    path_length_excess_m: float = 0.0
    extra_energy_consumed_wh: float = 0.0


def _clamp(value: float, limit: float) -> float:
    return max(-limit, min(limit, value))


def _seg_heading_rad(
    seg_start_lat: float,
    seg_start_lon: float,
    seg_end_lat: float,
    seg_end_lon: float,
) -> float:
    mid_lat = (seg_start_lat + seg_end_lat) * 0.5
    cos_lat = math.cos(math.radians(mid_lat))
    dx = (seg_end_lon - seg_start_lon) * _M_PER_DEG * cos_lat
    dy = (seg_end_lat - seg_start_lat) * _M_PER_DEG
    return math.atan2(dx, dy)


def compute_cross_track_errors(
    *,
    est_lat: float,
    est_lon: float,
    nominal_lat: float,
    nominal_lon: float,
    seg_start_lat: float,
    seg_start_lon: float,
    seg_end_lat: float,
    seg_end_lon: float,
) -> tuple[float, float]:
    """Return (cross_track_error_m, along_track_error_m) for an estimated position.

    Cross-track error is positive to the right of the segment direction.
    Along-track error is positive when ahead of the supplied nominal position.
    Uses flat-earth approximation — valid for segments < ~50 km.
    """
    mid_lat = (seg_start_lat + seg_end_lat) * 0.5
    cos_lat = math.cos(math.radians(mid_lat))

    dx_seg = (seg_end_lon - seg_start_lon) * _M_PER_DEG * cos_lat
    dy_seg = (seg_end_lat - seg_start_lat) * _M_PER_DEG
    seg_len = math.hypot(dx_seg, dy_seg)

    dx_pt = (est_lon - seg_start_lon) * _M_PER_DEG * cos_lat
    dy_pt = (est_lat - seg_start_lat) * _M_PER_DEG
    dx_nominal = (nominal_lon - seg_start_lon) * _M_PER_DEG * cos_lat
    dy_nominal = (nominal_lat - seg_start_lat) * _M_PER_DEG

    if seg_len < 1e-6:
        return math.hypot(dx_pt - dx_nominal, dy_pt - dy_nominal), 0.0

    ux, uy = dx_seg / seg_len, dy_seg / seg_len
    along = (dx_pt - dx_nominal) * ux + (dy_pt - dy_nominal) * uy
    cross = dx_pt * uy - dy_pt * ux  # positive to the right of direction of travel
    return cross, along


def controller_corrections(
    *,
    cross_track_error_m: float,
    along_track_error_m: float,
    profile: ControllerProfile,
) -> tuple[float, float]:
    """Return (heading_correction_rad, speed_correction_mps) clamped to limits."""
    hdg = _clamp(
        -profile.Kp_cross_track * cross_track_error_m,
        profile.max_heading_correction_rad,
    )
    spd = _clamp(
        -profile.Kp_along_track * along_track_error_m, profile.max_speed_correction_mps
    )
    return hdg, spd


def advance_true_state(
    *,
    est_lat: float,
    est_lon: float,
    nominal_lat: float,
    nominal_lon: float,
    nominal_speed_mps: float,
    nominal_energy_step_wh: float,
    dt_s: float,
    profile: ControllerProfile,
    state: ControllerState,
    seg_start_lat: float,
    seg_start_lon: float,
    seg_end_lat: float,
    seg_end_lon: float,
) -> None:
    """Advance state.true_lat/true_lon via controller feedback.

    Accumulates path_length_excess_m and extra_energy_consumed_wh in state.
    """
    if dt_s <= 0.0:
        state.cross_track_error_m = 0.0
        state.along_track_error_m = 0.0
        return

    if (
        abs(seg_end_lat - seg_start_lat) < 1e-12
        and abs(seg_end_lon - seg_start_lon) < 1e-12
    ):
        state.cross_track_error_m = 0.0
        state.along_track_error_m = 0.0
        return

    xte, ate = compute_cross_track_errors(
        est_lat=est_lat,
        est_lon=est_lon,
        nominal_lat=nominal_lat,
        nominal_lon=nominal_lon,
        seg_start_lat=seg_start_lat,
        seg_start_lon=seg_start_lon,
        seg_end_lat=seg_end_lat,
        seg_end_lon=seg_end_lon,
    )
    state.cross_track_error_m = xte
    state.along_track_error_m = ate

    hdg_corr, spd_corr = controller_corrections(
        cross_track_error_m=xte,
        along_track_error_m=ate,
        profile=profile,
    )

    seg_heading = _seg_heading_rad(
        seg_start_lat, seg_start_lon, seg_end_lat, seg_end_lon
    )
    corrected_heading = seg_heading + hdg_corr
    corrected_speed = max(0.1, nominal_speed_mps + spd_corr)

    actual_dist_m = corrected_speed * dt_s
    nominal_dist_m = nominal_speed_mps * dt_s

    cos_c = math.cos(math.radians(state.true_lat))
    state.true_lat += (actual_dist_m * math.cos(corrected_heading)) / _M_PER_DEG
    state.true_lon += (actual_dist_m * math.sin(corrected_heading)) / (
        _M_PER_DEG * max(1e-6, cos_c)
    )

    excess_m = max(0.0, actual_dist_m - nominal_dist_m)
    state.path_length_excess_m += excess_m

    if nominal_dist_m > 1e-9 and nominal_energy_step_wh > 0.0:
        state.extra_energy_consumed_wh += (
            nominal_energy_step_wh * excess_m / nominal_dist_m
        )
