import json
from pathlib import Path

import pytest

from adapters.geofence_geojson import GeofenceLoadError
from adapters.geofence_geojson import load_geofences
from estimator import EstimateStatus
from estimator import FailureCode
from estimator import FailureKind
from estimator import GeofenceKind
from estimator import GeofenceZone
from estimator import try_estimate_mission_distance_time
from tests.helpers import make_mission
from tests.helpers import make_vehicle


def _zone(
    *,
    zone_id: str,
    kind: GeofenceKind,
    exterior: list[tuple[float, float]],
    holes: list[list[tuple[float, float]]] | None = None,
) -> GeofenceZone:
    return GeofenceZone.model_validate(
        {
            "id": zone_id,
            "kind": kind,
            "geometry": {
                "polygons": [
                    {
                        "exterior": [
                            {"lat": lat, "lon": lon} for lat, lon in exterior
                        ],
                        "holes": [
                            [{"lat": lat, "lon": lon} for lat, lon in hole]
                            for hole in holes or []
                        ],
                    }
                ]
            },
        }
    )


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
    assert result.legs
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
