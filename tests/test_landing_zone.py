import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pyproj import Geod

from adapters.landing_zone_geojson import LandingZoneLoadError, load_landing_zones
from adapters.markdown import render_envelope_markdown
from estimator import (
    ConstantWindProvider,
    EstimateStatus,
    FailureCode,
    FailureKind,
    LandingZone,
    try_estimate_mission_distance_time,
)
from schemas import AltitudeReference
from tests.helpers import make_mission, make_vehicle
from schemas.mission import MissionAction, RouteItem


def _point_zone(
    zone_id: str,
    *,
    lat: float,
    lon: float,
    altitude_amsl_m: float = 12.0,
) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
            "altitude_amsl_m": altitude_amsl_m,
            "geometry": {
                "points": [
                    {
                        "lat": lat,
                        "lon": lon,
                    }
                ]
            },
        }
    )


@pytest.mark.parametrize("altitude", [True, "12", float("inf"), float("nan")])
def test_landing_zone_surface_altitude_must_be_finite_numeric(
    altitude: object,
) -> None:
    with pytest.raises(ValidationError, match="altitude_amsl_m"):
        LandingZone.model_validate(
            {
                "id": "invalid-altitude",
                "altitude_amsl_m": altitude,
                "geometry": {"points": [{"lat": 52.0, "lon": 4.0}]},
            }
        )


def test_nearby_landing_zone_returns_complete_reachability_result() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("wp1_lz", lat=52.001, lon=4.002)

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.landing_zone is not None
    assert result.landing_zone.is_feasible is True
    assert result.landing_zone.checked_zone_count == 1
    assert result.landing_zone.checked_state_count > len(result.legs)
    endpoint = result.landing_zone.states[-1]
    assert endpoint.reachable_zone_id == "wp1_lz"
    assert endpoint.divert_energy_wh is not None
    assert endpoint.divert_energy_wh > 0.0


def test_no_landing_zone_within_max_distance_is_infeasible() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    mission.constraints.min_distance_to_landing_zone_m = 250.0
    zone = _point_zone("far_lz", lat=52.05, lon=4.05)

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.NO_REACHABLE_LANDING_ZONE
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.landing_zone is not None
    assert result.landing_zone.is_feasible is False
    assert result.landing_zone.states[0].nearest_zone_id == "far_lz"


def test_landing_zone_behind_aircraft_uses_dubins_reachability_distance() -> None:
    mission = make_mission()
    mission.constraints.require_rth_reserve = False
    mission.constraints.min_distance_to_landing_zone_m = 200.0
    geod = Geod(ellps="WGS84")
    waypoint_lon, waypoint_lat, _ = geod.fwd(
        mission.planned_home.lon,
        mission.planned_home.lat,
        0.0,
        1_000.0,
    )
    zone_lon, zone_lat, _ = geod.fwd(
        waypoint_lon,
        waypoint_lat,
        180.0,
        100.0,
    )
    mission.route = [
        RouteItem(
            id="north",
            action=MissionAction.WAYPOINT,
            lat=waypoint_lat,
            lon=waypoint_lon,
            altitude_m=120.0,
        )
    ]
    vehicle = make_vehicle()
    vehicle.performance.turn_radius_m = 100.0

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        landing_zones=[_point_zone("behind", lat=zone_lat, lon=zone_lon)],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.NO_REACHABLE_LANDING_ZONE
    assert result.landing_zone is not None
    state = result.landing_zone.states[-1]
    assert state.nearest_zone_distance_m == pytest.approx(571.2389, rel=0.01)
    assert state.nearest_zone_distance_m > 200.0


def test_reachable_landing_zone_below_reserve_is_infeasible() -> None:
    mission = make_mission()
    mission.route = [mission.route[0]]
    mission.constraints.min_distance_to_landing_zone_m = 10_000.0
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 50.0
    zone = _point_zone("distant_lz", lat=52.045, lon=4.0)

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        landing_zones=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.LANDING_ZONE_REACHABLE_BUT_BELOW_RESERVE
    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert result.landing_zone is not None
    state = next(state for state in result.landing_zone.states if not state.reserve_ok)
    assert state.reachable_zone_id == "distant_lz"
    assert state.reserve_after_divert_wh < result.landing_zone.reserve_threshold_wh


def test_landing_zone_divert_fails_when_headwind_blocks_path() -> None:
    mission = make_mission()
    mission.route = [mission.route[0]]
    mission.constraints.require_rth_reserve = False
    mission.constraints.max_wind_mps = None
    mission.constraints.min_distance_to_landing_zone_m = 2_000.0
    zone_lon, zone_lat, _ = Geod(ellps="WGS84").fwd(
        mission.planned_home.lon,
        mission.planned_home.lat,
        90.0,
        500.0,
    )
    vehicle = make_vehicle()
    vehicle.performance.turn_radius_m = None
    vehicle.performance.max_crab_angle_deg = 89.0

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        wind_provider=ConstantWindProvider(-18.0, 0.0),
        landing_zones=[_point_zone("east", lat=zone_lat, lon=zone_lon)],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.GROUNDSPEED_NON_POSITIVE


def test_landing_zone_distance_is_checked_between_long_leg_endpoints() -> None:
    mission = make_mission()
    mission.constraints.require_rth_reserve = False
    mission.constraints.min_distance_to_landing_zone_m = 200.0
    end_lon, end_lat, _ = Geod(ellps="WGS84").fwd(
        mission.planned_home.lon,
        mission.planned_home.lat,
        90.0,
        1_000.0,
    )
    waypoint = mission.route[1]
    waypoint.lat = end_lat
    waypoint.lon = end_lon
    waypoint.altitude_reference = AltitudeReference.AMSL
    waypoint.altitude_m = mission.planned_home.altitude_amsl_m
    mission.route = [waypoint]
    zone = LandingZone.model_validate(
        {
            "id": "endpoint_pair",
            "altitude_amsl_m": mission.planned_home.altitude_amsl_m,
            "geometry": {
                "points": [
                    {
                        "lat": mission.planned_home.lat,
                        "lon": mission.planned_home.lon,
                    },
                    {"lat": end_lat, "lon": end_lon},
                ]
            },
        }
    )
    vehicle = make_vehicle()
    vehicle.performance.turn_radius_m = None

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        landing_zones=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.NO_REACHABLE_LANDING_ZONE
    assert result.landing_zone is not None
    assert result.landing_zone.checked_state_count > 2
    assert any(
        state.code == FailureCode.NO_REACHABLE_LANDING_ZONE
        for state in result.landing_zone.states
    )


def test_missing_landing_surface_altitude_fails_closed_without_terrain() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = LandingZone.model_validate(
        {
            "id": "unknown_height",
            "geometry": {
                "points": [{"lat": 52.001, "lon": 4.002}],
            },
        }
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_COVERAGE_MISSING


def test_polygon_landing_zone_contains_route_state_with_zero_horizontal_divert() -> (
    None
):
    zone = LandingZone.model_validate(
        {
            "id": "area_lz",
            "altitude_amsl_m": 12.0,
            "geometry": {
                "polygons": [
                    {
                        "exterior": [
                            {"lat": 52.0005, "lon": 4.0015},
                            {"lat": 52.0015, "lon": 4.0015},
                            {"lat": 52.0015, "lon": 4.0025},
                            {"lat": 52.0005, "lon": 4.0025},
                            {"lat": 52.0005, "lon": 4.0015},
                        ]
                    }
                ]
            },
        }
    )
    mission = make_mission()
    mission.route = [mission.route[1]]

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.landing_zone is not None
    endpoint = result.landing_zone.states[-1]
    assert endpoint.reachable_zone_distance_m == 0.0
    assert endpoint.divert_energy_wh is not None
    assert endpoint.divert_energy_wh > 0.0


def test_geojson_landing_zone_importer_supports_point_and_polygon(
    tmp_path: Path,
) -> None:
    path = tmp_path / "landing_zones.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "point_lz",
                        "properties": {
                            "surface": "grass",
                            "altitude_amsl_m": 12.0,
                        },
                        "geometry": {
                            "type": "Point",
                            "coordinates": [4.002, 52.001],
                        },
                    },
                    {
                        "type": "Feature",
                        "id": "area_lz",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [4.0015, 52.0005],
                                    [4.0025, 52.0005],
                                    [4.0025, 52.0015],
                                    [4.0015, 52.0015],
                                    [4.0015, 52.0005],
                                ]
                            ],
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    zones, document = load_landing_zones(path)

    assert document.format == "geojson"
    assert zones[0].id == "point_lz"
    assert zones[0].altitude_amsl_m == 12.0
    assert zones[0].metadata["surface"] == "grass"
    assert zones[0].geometry.points[0].lon == 4.002
    assert zones[0].geometry.points[0].lat == 52.001
    assert zones[1].geometry.polygons[0].exterior[0].lon == 4.0015


def test_geojson_landing_zone_importer_rejects_unsupported_geometry_type(
    tmp_path: Path,
) -> None:
    path = tmp_path / "landing_zones.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[4.0, 52.0], [4.1, 52.1]],
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(LandingZoneLoadError) as exc_info:
        load_landing_zones(path)

    error = exc_info.value
    assert error.failure.kind == FailureKind.UNSUPPORTED
    assert error.failure.code == FailureCode.UNSUPPORTED_LANDING_ZONE_GEOMETRY


def test_geojson_landing_zone_importer_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "landing_zones.geojson"
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(LandingZoneLoadError) as exc_info:
        load_landing_zones(path)

    assert exc_info.value.failure.code == FailureCode.INVALID_GEOMETRY


def test_geojson_landing_zone_importer_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "landing_zones.geojson"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(LandingZoneLoadError) as exc_info:
        load_landing_zones(path)

    assert exc_info.value.failure.code == FailureCode.INVALID_GEOMETRY


def test_markdown_render_does_not_crash_when_max_allowed_distance_is_none() -> None:
    """Regression: _fmt(None) caused TypeError when max_allowed_distance_m was unset."""
    from pathlib import Path as _Path

    from adapters.envelope import EnvelopeInputs, build_estimator_envelope
    from adapters.io import InputDocument

    mission = make_mission()
    mission.constraints.min_distance_to_landing_zone_m = None
    zone = _point_zone("lz", lat=52.001, lon=4.001)
    vehicle = make_vehicle()

    result = try_estimate_mission_distance_time(mission, vehicle, landing_zones=[zone])
    assert result.landing_zone is not None
    assert result.landing_zone.max_allowed_distance_m is None

    fake_doc = InputDocument(path=_Path("/fake/m.yaml"), format="yaml", sha256="0" * 64)
    envelope = build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(mission=fake_doc, vehicle=fake_doc),
    )
    md = render_envelope_markdown(envelope)
    assert "Max allowed distance m: `none`" in md
