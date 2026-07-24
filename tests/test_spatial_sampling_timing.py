"""Timing-sensitive altitude regressions for hazard-route sampling."""

import pytest
from pyproj import Geod

from bvlos_sim.estimator import EstimationOptions, LegEstimate, estimate_mission_distance_time
from bvlos_sim.estimator.execution.spatial_sampling import SpatialSamplingError, route_leg_samples
from bvlos_sim.schemas import AltitudeReference, MissionPlan
from tests.helpers import make_mission, make_vehicle

_GEOD = Geod(ellps="WGS84")


def _single_waypoint_mission(
    *,
    start_alt_amsl_m: float,
    end_alt_amsl_m: float,
    horizontal_distance_m: float,
) -> MissionPlan:
    mission = make_mission()
    mission.planned_home.altitude_amsl_m = start_alt_amsl_m
    waypoint = mission.route[1]
    lon, lat, _ = _GEOD.fwd(
        mission.planned_home.lon,
        mission.planned_home.lat,
        90.0,
        horizontal_distance_m,
    )
    waypoint.lat = lat
    waypoint.lon = lon
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = end_alt_amsl_m
    mission.route = [waypoint]
    mission.defaults.cruise_speed_mps = 20.0
    mission.constraints.require_rth_reserve = False
    return mission


def test_zero_horizontal_vertical_leg_samples_both_altitude_endpoints() -> None:
    result = estimate_mission_distance_time(
        _single_waypoint_mission(
            start_alt_amsl_m=100.0,
            end_alt_amsl_m=10.0,
            horizontal_distance_m=0.0,
        ),
        make_vehicle(),
    )

    samples = route_leg_samples(
        result.legs,
        geod=_GEOD,
        max_segment_length_m=50.0,
    )[0]

    assert [sample.altitude_amsl_m for sample in samples] == [100.0, 10.0]
    assert samples[0].lat == pytest.approx(samples[1].lat)
    assert samples[0].lon == pytest.approx(samples[1].lon)


def test_hazard_altitude_uses_transit_time_not_spatial_fraction() -> None:
    vertical_distance_m = 100.0
    climb_rate_mps = make_vehicle().performance.climb_rate_mps
    assert climb_rate_mps is not None
    result = estimate_mission_distance_time(
        _single_waypoint_mission(
            start_alt_amsl_m=12.0,
            end_alt_amsl_m=112.0,
            horizontal_distance_m=100.2699,
        ),
        make_vehicle(),
        options=EstimationOptions(max_segment_length_m=34.0),
    )

    leg = result.legs[0]
    samples = route_leg_samples(
        [leg],
        geod=_GEOD,
        max_segment_length_m=34.0,
    )[0]
    one_third = next(
        sample for sample in samples if sample.fraction == pytest.approx(1.0 / 3.0)
    )
    expected_elapsed_s = leg.horizontal_distance_m / (3.0 * 20.0)
    expected_altitude_m = 12.0 + vertical_distance_m * (
        expected_elapsed_s / (vertical_distance_m / climb_rate_mps)
    )

    assert one_third.altitude_amsl_m == pytest.approx(expected_altitude_m)
    assert one_third.altitude_amsl_m < 20.0
    assert samples[-1].fraction == 1.0
    assert samples[-1].altitude_amsl_m == 112.0


def test_altitude_changing_leg_without_private_timing_fails_closed() -> None:
    result = estimate_mission_distance_time(
        _single_waypoint_mission(
            start_alt_amsl_m=12.0,
            end_alt_amsl_m=112.0,
            horizontal_distance_m=100.2699,
        ),
        make_vehicle(),
        options=EstimationOptions(max_segment_length_m=34.0),
    )
    restored_without_private_timing = LegEstimate.model_validate(
        result.legs[0].model_dump()
    )

    with pytest.raises(SpatialSamplingError, match="no transit timing profile"):
        route_leg_samples(
            [restored_without_private_timing],
            geod=_GEOD,
            max_segment_length_m=34.0,
        )
