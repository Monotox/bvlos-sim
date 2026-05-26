"""Tests for engine-level advisory warnings: max_wind, failsafe thresholds, and route structure."""

from estimator import EstimationOptions, GeofenceZone, LandingZone, WarningCode, estimate_mission_distance_time
from schemas.mission import MissionPlan
from tests.helpers import make_mission, make_vehicle


def test_max_wind_warning_emitted_when_leg_wind_exceeds_limit() -> None:
    vehicle = make_vehicle()
    vehicle.performance.max_wind_mps = 2.0
    mission = make_mission()

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(wind_east_mps=5.0, wind_north_mps=0.0),
    )

    codes = {w.code for w in result.warnings}
    assert WarningCode.MAX_WIND_EXCEEDED in codes


def test_max_wind_warning_not_emitted_below_limit() -> None:
    vehicle = make_vehicle()
    vehicle.performance.max_wind_mps = 10.0
    mission = make_mission()

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(wind_east_mps=3.0, wind_north_mps=0.0),
    )

    codes = {w.code for w in result.warnings}
    assert WarningCode.MAX_WIND_EXCEEDED not in codes


def test_max_wind_warning_not_emitted_when_max_wind_not_set() -> None:
    vehicle = make_vehicle()
    vehicle.performance.max_wind_mps = None
    mission = make_mission()

    result = estimate_mission_distance_time(
        mission,
        vehicle,
        options=EstimationOptions(wind_east_mps=8.0, wind_north_mps=0.0),
    )

    codes = {w.code for w in result.warnings}
    assert WarningCode.MAX_WIND_EXCEEDED not in codes


def test_failsafe_abort_warning_emitted_when_reserve_below_abort_percent() -> None:
    # Default mission leaves ~95.4% reserve; set abort threshold above that.
    vehicle = make_vehicle()
    vehicle.failsafe = vehicle.failsafe.model_copy(
        update={"low_battery_abort_percent": 97, "low_battery_warn_percent": 50}
    )
    mission = make_mission()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD in codes


def test_failsafe_warn_warning_emitted_when_reserve_between_warn_and_abort() -> None:
    # Default mission leaves ~95.4% reserve; warn=97% fires, abort=94% does not.
    vehicle = make_vehicle()
    vehicle.failsafe = vehicle.failsafe.model_copy(
        update={"low_battery_abort_percent": 94, "low_battery_warn_percent": 97}
    )
    mission = make_mission()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD in codes
    assert WarningCode.RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD not in codes


def test_no_failsafe_warning_when_reserve_above_thresholds() -> None:
    vehicle = make_vehicle()
    mission = make_mission()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD not in codes
    assert WarningCode.RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD not in codes


def test_no_failsafe_warning_when_failsafe_not_set() -> None:
    vehicle = make_vehicle()
    vehicle.failsafe = None
    mission = make_mission()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD not in codes
    assert WarningCode.RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD not in codes


def test_route_actions_after_rtl_warning_emitted() -> None:
    mission = make_mission()
    # Move RTL to index 1 (between takeoff and waypoint) so waypoint follows it.
    route = list(mission.route)
    # takeoff, RTL, waypoint
    route = [route[0], route[3], route[1]]
    mission = MissionPlan.model_validate(
        {
            **mission.model_dump(),
            "route": [r.model_dump() for r in route],
        }
    )
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.ROUTE_ACTIONS_AFTER_RTL in codes


def test_divert_energy_tas_only_warning_emitted_when_landing_zones_configured() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = LandingZone.model_validate(
        {
            "id": "lz",
            "geometry": {"points": [{"lat": 52.001, "lon": 4.001}], "polygons": []},
        }
    )

    result = estimate_mission_distance_time(mission, vehicle, landing_zones=[zone])

    codes = {w.code for w in result.warnings}
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY in codes


def test_divert_energy_tas_only_warning_not_emitted_without_landing_zones() -> None:
    mission = make_mission()
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY not in codes


def test_geofence_2d_only_warning_emitted_when_geofences_configured() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = GeofenceZone.model_validate(
        {
            "id": "fence",
            "kind": "forbidden",
            "geometry": {
                "polygons": [
                    {
                        "exterior": [
                            {"lat": 51.9, "lon": 4.1},
                            {"lat": 51.9, "lon": 4.2},
                            {"lat": 52.1, "lon": 4.2},
                            {"lat": 52.1, "lon": 4.1},
                            {"lat": 51.9, "lon": 4.1},
                        ]
                    }
                ]
            },
        }
    )

    result = estimate_mission_distance_time(mission, vehicle, geofences=[zone])

    codes = {w.code for w in result.warnings}
    assert WarningCode.GEOFENCE_EVALUATED_2D_ONLY in codes


def test_geofence_2d_only_warning_not_emitted_without_geofences() -> None:
    mission = make_mission()
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.GEOFENCE_EVALUATED_2D_ONLY not in codes


def test_loiter_radius_ignored_warning_emitted() -> None:
    mission = make_mission()
    route = list(mission.route)
    loiter = route[2].model_copy(update={"loiter_radius_m": 50.0})
    route[2] = loiter
    mission = MissionPlan.model_validate(
        {
            **mission.model_dump(),
            "route": [r.model_dump() for r in route],
        }
    )
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    codes = {w.code for w in result.warnings}
    assert WarningCode.LOITER_RADIUS_IGNORED in codes
