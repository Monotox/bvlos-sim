"""Tests for sub-segment wind sampling (fidelity v2 mode)."""

import math

import pytest

from estimator import (
    EstimationOptions,
    LayeredWindProvider,
    WindLayer,
    estimate_mission_distance_time,
)
from schemas import AltitudeReference, MissionPlan
from tests.helpers import make_mission, make_vehicle


def _flat_waypoint_mission() -> MissionPlan:
    """Single waypoint leg at home altitude to isolate transit time."""
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = 52.0
    wp.lon = 4.05
    wp.altitude_reference = AltitudeReference.AMSL
    wp.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [wp]
    mission.defaults.cruise_speed_mps = 20.0
    return mission


# ---------------------------------------------------------------------------
# v1 compatibility
# ---------------------------------------------------------------------------


def test_no_max_segment_produces_same_result_as_constant_wind_v1() -> None:
    mission = _flat_waypoint_mission()
    vehicle = make_vehicle()
    opts_v1 = EstimationOptions(wind_east_mps=5.0, wind_north_mps=0.0)
    opts_v2 = EstimationOptions(
        wind_east_mps=5.0, wind_north_mps=0.0, max_segment_length_m=100.0
    )
    result_v1 = estimate_mission_distance_time(mission, vehicle, options=opts_v1)
    result_v2 = estimate_mission_distance_time(mission, vehicle, options=opts_v2)
    # Sub-segment sampling with constant wind must give the same total time.
    assert math.isclose(result_v1.total_time_s, result_v2.total_time_s, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# LayeredWindProvider integration
# ---------------------------------------------------------------------------


def test_layered_wind_tailwind_faster_than_headwind() -> None:
    mission = _flat_waypoint_mission()
    vehicle = make_vehicle()
    # Two providers with opposite winds
    tail = LayeredWindProvider([
        WindLayer(altitude_m=0.0, wind_east_mps=5.0, wind_north_mps=0.0),
    ])
    head = LayeredWindProvider([
        WindLayer(altitude_m=0.0, wind_east_mps=-5.0, wind_north_mps=0.0),
    ])
    r_tail = estimate_mission_distance_time(mission, vehicle, wind_provider=tail)
    r_head = estimate_mission_distance_time(mission, vehicle, wind_provider=head)
    assert r_tail.total_time_s < r_head.total_time_s


def test_layered_wind_sub_segment_changes_time_vs_constant_start_sample() -> None:
    """A leg climbing through a wind boundary should differ from single-sample.

    Home at 12m amsl, waypoint at 200m amsl (188m climb → ~63s).
    Horizontal leg ~5km east → ~417s at gs=12 (headwind) or ~333s mixed.
    Horizontal time dominates so wind sampling materially affects the result.
    """
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = 52.0
    wp.lon = 4.073  # ~5 km east of home
    wp.altitude_reference = AltitudeReference.AMSL
    # 200m amsl: 188m climb above home (12m), climb time ≈ 63s
    wp.altitude_m = 200.0
    mission.route = [wp]
    mission.defaults.cruise_speed_mps = 20.0
    vehicle = make_vehicle()
    # Below 100m: strong headwind; at/above 100m: calm.
    # The flight path crosses the boundary at ~47% of the leg.
    provider = LayeredWindProvider([
        WindLayer(altitude_m=0.0, wind_east_mps=-8.0, wind_north_mps=0.0),
        WindLayer(altitude_m=100.0, wind_east_mps=0.0, wind_north_mps=0.0),
    ])
    # v1: single sample at start (alt=12m, strong headwind) → gs≈12 m/s whole leg
    r_v1 = estimate_mission_distance_time(mission, vehicle, wind_provider=provider)
    # v2: sub-segments capture upper-half calm air → gs=20 m/s for later segments
    r_v2 = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(max_segment_length_m=500.0),
        wind_provider=provider,
    )
    assert r_v2.total_time_s < r_v1.total_time_s


# ---------------------------------------------------------------------------
# Sub-segment count
# ---------------------------------------------------------------------------


def test_leg_shorter_than_max_segment_skips_sub_segmentation() -> None:
    """When the leg is shorter than max_segment_length_m, the v1 code path is taken.

    The sub-segment loop is not entered; the result is identical to max_segment_length_m=None.
    """
    mission = _flat_waypoint_mission()
    vehicle = make_vehicle()
    opts_large_seg = EstimationOptions(
        wind_east_mps=5.0, wind_north_mps=0.0, max_segment_length_m=1_000_000.0
    )
    opts_no_seg = EstimationOptions(wind_east_mps=5.0, wind_north_mps=0.0)
    r_large = estimate_mission_distance_time(mission, vehicle, options=opts_large_seg)
    r_none = estimate_mission_distance_time(mission, vehicle, options=opts_no_seg)
    assert math.isclose(r_large.total_time_s, r_none.total_time_s, rel_tol=1e-9)


def test_two_runs_with_same_inputs_produce_identical_results_v2() -> None:
    mission = _flat_waypoint_mission()
    vehicle = make_vehicle()
    opts = EstimationOptions(
        wind_east_mps=3.0, wind_north_mps=1.0, max_segment_length_m=200.0
    )
    r1 = estimate_mission_distance_time(mission, vehicle, options=opts)
    r2 = estimate_mission_distance_time(mission, vehicle, options=opts)
    assert r1.total_time_s == r2.total_time_s


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_max_segment_length_zero_is_rejected() -> None:
    with pytest.raises(Exception):
        EstimationOptions(max_segment_length_m=0.0)


def test_max_segment_length_negative_is_rejected() -> None:
    with pytest.raises(Exception):
        EstimationOptions(max_segment_length_m=-100.0)


def test_min_groundspeed_zero_is_rejected() -> None:
    with pytest.raises(Exception):
        EstimationOptions(min_groundspeed_mps=0.0)


def test_min_groundspeed_negative_is_rejected() -> None:
    with pytest.raises(Exception):
        EstimationOptions(min_groundspeed_mps=-1.0)


# ---------------------------------------------------------------------------
# Altitude interpolation: time-based vs spatial-based
# ---------------------------------------------------------------------------


def test_subsegment_altitude_interpolation_uses_time_not_spatial_fraction() -> None:
    """Time-based altitude interpolation: once the climb completes, later
    sub-segments sample at the target altitude rather than a spatial fraction.

    Setup: home at 12m amsl, waypoint at 62m amsl (50m climb).
    Climb rate 3 m/s → vertical_time ≈ 17s.
    Horizontal leg ~3.4 km east → horizontal_time ≈ 170s (dominant).
    n = ceil(3400/500) = 7 sub-segments; each takes ~24s.

    The aircraft finishes climbing after ~17s — during sub-segment 0's time
    window. From sub-segment 1 onward, alt_frac = 1.0 → altitude = 62m amsl.

    Wind scenario A: strong headwind ONLY below 62m amsl, calm at/above 62m.
    Wind scenario B: strong headwind everywhere (all altitudes).

    With time-based altitude:
      - Sub-seg 0 samples below 62m → headwind.
      - Sub-segs 1–6 sample at 62m → calm.
      - Horizontal time ≈ (1 slow segment + 6 fast) → much less than B.

    If spatial interpolation were used instead, all 7 sub-segments would
    sample between 12m and 59m amsl (all below 62m) → headwind on every
    sub-segment → result ≈ scenario B. The large speed difference between
    A and B confirms that the altitude tracking is time-based.
    """
    mission = make_mission()
    wp = mission.route[1]
    wp.lat = 52.0
    wp.lon = 4.05      # ~3.4 km east of home; horizontal_time >> vertical_time
    wp.altitude_reference = AltitudeReference.AMSL
    wp.altitude_m = 62.0  # 50m above home (12m amsl); climb completes in ~17s
    mission.route = [wp]
    mission.defaults.cruise_speed_mps = 20.0
    vehicle = make_vehicle()

    headwind = -8.0  # m/s eastward (opposing the eastward leg)
    boundary_alt = 62.0  # amsl — the target altitude

    # Headwind only below target altitude; calm at/above it.
    provider_boundary = LayeredWindProvider([
        WindLayer(altitude_m=0.0, wind_east_mps=headwind, wind_north_mps=0.0),
        WindLayer(altitude_m=boundary_alt, wind_east_mps=0.0, wind_north_mps=0.0),
    ])
    # Headwind at all altitudes (worst case).
    provider_everywhere = LayeredWindProvider([
        WindLayer(altitude_m=0.0, wind_east_mps=headwind, wind_north_mps=0.0),
    ])

    opts = EstimationOptions(max_segment_length_m=500.0)
    r_boundary = estimate_mission_distance_time(mission, vehicle, options=opts, wind_provider=provider_boundary)
    r_everywhere = estimate_mission_distance_time(mission, vehicle, options=opts, wind_provider=provider_everywhere)

    # With time-based altitude: only sub-seg 0 samples in the headwind zone.
    # The remaining 6/7 sub-segments are at the calm target altitude.
    # This gives a significantly shorter time than headwind on every sub-segment.
    assert r_boundary.total_time_s < r_everywhere.total_time_s
