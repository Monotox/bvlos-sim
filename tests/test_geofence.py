import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pyproj import Geod

from bvlos_sim.adapters.geofence_geojson import GeofenceLoadError, load_geofences
from bvlos_sim.estimator import (
    EstimationOptions,
    EstimateStatus,
    FailureCode,
    FailureKind,
    GeofenceKind,
    GeofenceZone,
    LegPhase,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from tests.helpers import make_mission, make_vehicle
from bvlos_sim.schemas.mission import MissionAction, RouteItem


def _zone(
    *,
    zone_id: str,
    kind: GeofenceKind,
    exterior: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]] | None = None,
    floor_m: float | None = None,
    ceiling_m: float | None = None,
) -> GeofenceZone:
    payload = {
        "id": zone_id,
        "kind": kind,
        "geometry": {
            "polygons": [
                {
                    "exterior": [{"lat": lat, "lon": lon} for lat, lon in exterior],
                    "holes": [
                        [{"lat": lat, "lon": lon} for lat, lon in hole]
                        for hole in holes or []
                    ],
                }
            ]
        },
    }
    if floor_m is not None:
        payload["floor_m"] = floor_m
    if ceiling_m is not None:
        payload["ceiling_m"] = ceiling_m
    return GeofenceZone.model_validate(payload)


def _route_crossing_zone() -> list[tuple[float, float]]:
    return [
        (51.999, 4.001),
        (52.003, 4.001),
        (52.003, 4.003),
        (51.999, 4.003),
        (51.999, 4.001),
    ]


def _mission_single_waypoint():
    mission = make_mission()
    mission.route = [mission.route[1]]
    return mission


def test_forbidden_zone_intersecting_materialized_turn_arc_is_detected() -> None:
    mission = make_mission()
    mission.constraints.require_rth_reserve = False
    mission.route = [
        RouteItem(
            id="north",
            action=MissionAction.WAYPOINT,
            lat=52.01,
            lon=4.0,
            altitude_m=120.0,
        ),
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=52.01,
            lon=4.02,
            altitude_m=120.0,
        ),
    ]
    options = EstimationOptions(fidelity="v2")
    baseline = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=options,
    )
    arc = next(leg for leg in baseline.legs if leg.phase == LegPhase.TURN_ARC)
    assert arc.path_coordinates is not None
    arc_lon, arc_lat = arc.path_coordinates[len(arc.path_coordinates) // 2]
    delta = 0.000002
    zone = _zone(
        zone_id="arc_only",
        kind=GeofenceKind.FORBIDDEN,
        exterior=[
            (arc_lat - delta, arc_lon - delta),
            (arc_lat + delta, arc_lon - delta),
            (arc_lat + delta, arc_lon + delta),
            (arc_lat - delta, arc_lon + delta),
            (arc_lat - delta, arc_lon - delta),
        ],
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        options=options,
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE
    assert result.failure.leg_index == arc.leg_index


def test_route_entering_forbidden_zone_returns_complete_infeasible_result() -> None:
    zone = _zone(
        zone_id="no_fly",
        kind=GeofenceKind.FORBIDDEN,
        exterior=[
            (51.999, 4.001),
            (52.003, 4.001),
            (52.003, 4.003),
            (51.999, 4.003),
            (51.999, 4.001),
        ],
    )

    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.geofence is not None
    assert result.geofence.is_feasible is False
    assert result.geofence.conflicts[0].zone_id == "no_fly"


def test_forbidden_zone_boundary_touch_counts_as_conflict() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _zone(
        zone_id="touching_zone",
        kind=GeofenceKind.FORBIDDEN,
        exterior=[
            (52.001, 4.001),
            (52.003, 4.001),
            (52.003, 4.003),
            (52.001, 4.003),
            (52.001, 4.001),
        ],
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE


def test_forbidden_zone_below_leg_altitude_is_not_conflict() -> None:
    zone = _zone(
        zone_id="low_no_fly",
        kind=GeofenceKind.FORBIDDEN,
        exterior=_route_crossing_zone(),
        floor_m=0.0,
        ceiling_m=10.0,
    )

    result = try_estimate_mission_distance_time(
        _mission_single_waypoint(),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.geofence is not None
    assert result.geofence.conflicts == []


def test_forbidden_zone_above_leg_altitude_is_not_conflict() -> None:
    zone = _zone(
        zone_id="high_no_fly",
        kind=GeofenceKind.FORBIDDEN,
        exterior=_route_crossing_zone(),
        floor_m=200.0,
        ceiling_m=300.0,
    )

    result = try_estimate_mission_distance_time(
        _mission_single_waypoint(),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.geofence is not None
    assert result.geofence.conflicts == []


def test_forbidden_zone_overlapping_leg_altitude_is_conflict() -> None:
    zone = _zone(
        zone_id="mid_no_fly",
        kind=GeofenceKind.FORBIDDEN,
        exterior=_route_crossing_zone(),
        floor_m=100.0,
        ceiling_m=150.0,
    )

    result = try_estimate_mission_distance_time(
        _mission_single_waypoint(),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE
    assert result.geofence is not None
    assert result.geofence.conflicts[0].zone_id == "mid_no_fly"


def test_required_zone_without_altitude_containment_is_violation() -> None:
    zone = _zone(
        zone_id="operations_corridor",
        kind=GeofenceKind.REQUIRED,
        exterior=[
            (51.999, 3.999),
            (52.002, 3.999),
            (52.002, 4.003),
            (51.999, 4.003),
            (51.999, 3.999),
        ],
        floor_m=100.0,
        ceiling_m=150.0,
    )

    result = try_estimate_mission_distance_time(
        _mission_single_waypoint(),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_EXITS_REQUIRED_ZONE
    assert result.geofence is not None
    assert result.geofence.conflicts[0].zone_id == "operations_corridor"


def test_geofence_zone_rejects_ceiling_not_above_floor() -> None:
    with pytest.raises(ValidationError):
        _zone(
            zone_id="invalid_altitude_band",
            kind=GeofenceKind.FORBIDDEN,
            exterior=_route_crossing_zone(),
            floor_m=100.0,
            ceiling_m=100.0,
        )


def test_route_exiting_required_zone_returns_complete_infeasible_result() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _zone(
        zone_id="operations_area",
        kind=GeofenceKind.REQUIRED,
        exterior=[
            (51.999, 3.999),
            (52.0005, 3.999),
            (52.0005, 4.0005),
            (51.999, 4.0005),
            (51.999, 3.999),
        ],
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_EXITS_REQUIRED_ZONE
    assert result.geofence is not None
    assert result.geofence.conflicts[0].zone_kind == GeofenceKind.REQUIRED


def test_required_zone_boundary_touch_is_allowed() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _zone(
        zone_id="operations_area",
        kind=GeofenceKind.REQUIRED,
        exterior=[
            (51.999, 3.999),
            (52.001, 3.999),
            (52.001, 4.002),
            (51.999, 4.002),
            (51.999, 3.999),
        ],
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.geofence is not None
    assert result.geofence.is_feasible is True
    assert result.geofence.conflicts == []


def test_forbidden_polygon_hole_is_not_treated_as_forbidden_area() -> None:
    mission = make_mission()
    mission.route = [mission.route[0]]
    zone = _zone(
        zone_id="donut_no_fly",
        kind=GeofenceKind.FORBIDDEN,
        exterior=[
            (51.999, 3.999),
            (52.001, 3.999),
            (52.001, 4.001),
            (51.999, 4.001),
            (51.999, 3.999),
        ],
        holes=[
            [
                (51.9995, 3.9995),
                (52.0005, 3.9995),
                (52.0005, 4.0005),
                (51.9995, 4.0005),
                (51.9995, 3.9995),
            ]
        ],
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.geofence is not None
    assert result.geofence.conflicts == []


def test_invalid_core_polygon_returns_invalid_geometry_after_kinematics() -> None:
    zone = _zone(
        zone_id="bowtie",
        kind=GeofenceKind.FORBIDDEN,
        exterior=[
            (52.0, 4.0),
            (52.002, 4.002),
            (52.0, 4.002),
            (52.002, 4.0),
            (52.0, 4.0),
        ],
    )

    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.INVALID_GEOMETRY
    assert len(result.legs) > 0  # kinematics completed before geometry check
    assert result.geofence is None


def test_geojson_importer_uses_lon_lat_order_and_supports_multipolygons(
    tmp_path: Path,
) -> None:
    path = tmp_path / "geofences.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "required_area",
                        "properties": {"kind": "required"},
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [
                                    [
                                        [4.0, 52.0],
                                        [4.01, 52.0],
                                        [4.01, 52.01],
                                        [4.0, 52.01],
                                        [4.0, 52.0],
                                    ]
                                ],
                                [
                                    [
                                        [4.02, 52.02],
                                        [4.03, 52.02],
                                        [4.03, 52.03],
                                        [4.02, 52.03],
                                        [4.02, 52.02],
                                    ]
                                ],
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    zones, document = load_geofences(path)

    assert document.format == "geojson"
    assert zones[0].kind == GeofenceKind.REQUIRED
    assert len(zones[0].geometry.polygons) == 2
    assert zones[0].geometry.polygons[0].exterior[0].lon == 4.0
    assert zones[0].geometry.polygons[0].exterior[0].lat == 52.0


def test_geojson_importer_preserves_altitude_bounds(tmp_path: Path) -> None:
    path = tmp_path / "geofences.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "id": "altitude_bound_zone",
                "properties": {
                    "kind": "forbidden",
                    "floor_m": 120.0,
                    "ceiling_m": 180.0,
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [4.0, 52.0],
                            [4.01, 52.0],
                            [4.01, 52.01],
                            [4.0, 52.01],
                            [4.0, 52.0],
                        ]
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    zones, _document = load_geofences(path)

    assert zones[0].floor_m == 120.0
    assert zones[0].ceiling_m == 180.0


def test_geojson_importer_rejects_unsupported_geometry_type(tmp_path: Path) -> None:
    path = tmp_path / "geofences.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "Feature",
                "properties": {"kind": "forbidden"},
                "geometry": {
                    "type": "Point",
                    "coordinates": [4.0, 52.0],
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(GeofenceLoadError) as exc_info:
        load_geofences(path)

    error = exc_info.value
    assert error.failure.kind == FailureKind.UNSUPPORTED
    assert error.failure.code == FailureCode.UNSUPPORTED_GEOMETRY_TYPE


def test_geojson_importer_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "geofences.geojson"
    path.write_text("{bad json", encoding="utf-8")

    with pytest.raises(GeofenceLoadError) as exc_info:
        load_geofences(path)

    assert exc_info.value.failure.code == FailureCode.INVALID_GEOMETRY


def test_geojson_importer_rejects_non_object_root(tmp_path: Path) -> None:
    path = tmp_path / "geofences.geojson"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(GeofenceLoadError) as exc_info:
        load_geofences(path)

    assert exc_info.value.failure.code == FailureCode.INVALID_GEOMETRY


# ---------------------------------------------------------------------------
# Flown-path geometry: geodesic bow and antimeridian
# ---------------------------------------------------------------------------


def _long_eastbound_mission(*, lat: float, lon: float, end_lat: float, end_lon: float):
    mission = make_mission()
    mission.planned_home.lat = lat
    mission.planned_home.lon = lon
    mission.planned_home.altitude_amsl_m = 0.0
    mission.constraints.require_rth_reserve = False
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=end_lat,
            lon=end_lon,
            altitude_m=120.0,
        )
    ]
    return mission


def _box(*, lat_lo: float, lat_hi: float, lon_lo: float, lon_hi: float):
    return [
        (lat_lo, lon_lo),
        (lat_lo, lon_hi),
        (lat_hi, lon_hi),
        (lat_hi, lon_lo),
        (lat_lo, lon_lo),
    ]


def test_forbidden_zone_on_the_geodesic_but_off_the_chord_is_detected() -> None:
    """The check must follow the flown path, not a planar endpoint chord.

    A 40 km leg at 60 N bows about 54 m poleward of the straight line between
    its endpoints in degree space. A zone sitting in that gap is flown through
    while a two-point LineString misses it entirely - a silent GO.
    """

    geod = Geod(ellps="WGS84")
    start_lat, start_lon = 60.0, 10.0
    end_lon, end_lat, _ = geod.fwd(start_lon, start_lat, 90.0, 40_000.0)
    (mid_lon, mid_lat), = geod.npts(start_lon, start_lat, end_lon, end_lat, 1)
    bow_deg = mid_lat - (start_lat + end_lat) / 2.0
    assert bow_deg > 0.0

    zone = _zone(
        zone_id="BOW",
        kind=GeofenceKind.FORBIDDEN,
        exterior=_box(
            lat_lo=mid_lat - 0.4 * bow_deg,
            lat_hi=mid_lat + 0.4 * bow_deg,
            lon_lo=mid_lon - 0.005,
            lon_hi=mid_lon + 0.005,
        ),
    )

    result = try_estimate_mission_distance_time(
        _long_eastbound_mission(
            lat=start_lat, lon=start_lon, end_lat=end_lat, end_lon=end_lon
        ),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.geofence is not None and result.geofence.is_feasible is False
    assert result.geofence.conflicts[0].code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE


def test_leg_leaving_a_narrow_required_corridor_is_detected() -> None:
    """Required coverage is tested against the flown path, not the chord."""

    geod = Geod(ellps="WGS84")
    start_lat, start_lon = 60.0, 10.0
    end_lon, end_lat, _ = geod.fwd(start_lon, start_lat, 90.0, 40_000.0)
    band_deg = 30.0 / 111_320.0  # +-30 m, narrower than the ~54 m bow

    corridor = _zone(
        zone_id="CORRIDOR",
        kind=GeofenceKind.REQUIRED,
        exterior=[
            (start_lat - band_deg, start_lon - 0.01),
            (end_lat - band_deg, end_lon + 0.01),
            (end_lat + band_deg, end_lon + 0.01),
            (start_lat + band_deg, start_lon - 0.01),
            (start_lat - band_deg, start_lon - 0.01),
        ],
    )

    result = try_estimate_mission_distance_time(
        _long_eastbound_mission(
            lat=start_lat, lon=start_lon, end_lat=end_lat, end_lon=end_lon
        ),
        make_vehicle(),
        geofences=[corridor],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.geofence is not None and result.geofence.is_feasible is False
    assert result.geofence.conflicts[0].code == FailureCode.ROUTE_EXITS_REQUIRED_ZONE


def test_antimeridian_leg_flags_a_zone_on_its_path() -> None:
    geod = Geod(ellps="WGS84")
    start_lat, start_lon = -17.7, 179.98
    zone_lon, zone_lat, _ = geod.fwd(start_lon, start_lat, 90.0, 500.0)
    half = 0.002

    zone = _zone(
        zone_id="NEAR",
        kind=GeofenceKind.FORBIDDEN,
        exterior=_box(
            lat_lo=zone_lat - half,
            lat_hi=zone_lat + half,
            lon_lo=zone_lon - half,
            lon_hi=zone_lon + half,
        ),
    )

    result = try_estimate_mission_distance_time(
        _long_eastbound_mission(
            lat=start_lat, lon=start_lon, end_lat=-17.7, end_lon=-179.98
        ),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.geofence is not None and result.geofence.is_feasible is False


def test_antimeridian_leg_ignores_a_zone_on_the_far_side_of_the_globe() -> None:
    """The wrong-way wrap used to raise a conflict 16 000 km off the route."""

    half = 0.002
    zone = _zone(
        zone_id="FAR",
        kind=GeofenceKind.FORBIDDEN,
        exterior=_box(
            lat_lo=-17.7 - half,
            lat_hi=-17.7 + half,
            lon_lo=-half,
            lon_hi=half,
        ),
    )

    result = try_estimate_mission_distance_time(
        _long_eastbound_mission(
            lat=-17.7, lon=179.98, end_lat=-17.7, end_lon=-179.98
        ),
        make_vehicle(),
        geofences=[zone],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.geofence is not None and result.geofence.is_feasible is True
    assert result.geofence.conflicts == []


def _clear_zone(*, zone_id: str, floor_m: float | None, ceiling_m: float | None):
    """A zone far from the demo route, so only the warning behavior is exercised."""
    return _zone(
        zone_id=zone_id,
        kind=GeofenceKind.FORBIDDEN,
        exterior=_box(lat_lo=51.0, lat_hi=51.001, lon_lo=3.0, lon_hi=3.001),
        floor_m=floor_m,
        ceiling_m=ceiling_m,
    )


def _warning_codes(result) -> set[str]:
    return {str(warning.code) for warning in result.warnings}


def test_zone_without_altitude_bounds_warns_that_evaluation_is_2d() -> None:
    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        geofences=[_clear_zone(zone_id="unbounded", floor_m=None, ceiling_m=None)],
    )

    assert "GEOFENCE_EVALUATED_2D_ONLY" in _warning_codes(result)


@pytest.mark.parametrize(
    ("floor_m", "ceiling_m"),
    [(0.0, 300.0), (0.0, None), (None, 300.0)],
)
def test_zone_declaring_an_altitude_bound_does_not_warn(
    floor_m: float | None, ceiling_m: float | None
) -> None:
    """A bounded zone is constrained by altitude, so the 2D caveat is untrue.

    Emitting it unconditionally made every geofence mission NO-GO until the
    operator waived a warning that did not apply.
    """
    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        geofences=[
            _clear_zone(zone_id="bounded", floor_m=floor_m, ceiling_m=ceiling_m)
        ],
    )

    assert "GEOFENCE_EVALUATED_2D_ONLY" not in _warning_codes(result)


def test_one_unbounded_zone_among_bounded_zones_still_warns() -> None:
    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        geofences=[
            _clear_zone(zone_id="bounded", floor_m=0.0, ceiling_m=300.0),
            _clear_zone(zone_id="unbounded", floor_m=None, ceiling_m=None),
        ],
    )

    warning = next(
        w for w in result.warnings if str(w.code) == "GEOFENCE_EVALUATED_2D_ONLY"
    )
    assert "1 zone(s)" in warning.message
    assert "(unbounded)" in warning.message
