import json
from pathlib import Path

import pytest

from adapters.landing_zone_geojson import LandingZoneLoadError, load_landing_zones
from adapters.markdown import render_envelope_markdown
from estimator import (
    EstimateStatus,
    FailureCode,
    FailureKind,
    LandingZone,
    try_estimate_mission_distance_time,
)
from tests.helpers import make_mission, make_vehicle


def _point_zone(zone_id: str, *, lat: float, lon: float) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
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
    assert result.landing_zone.checked_state_count == len(result.legs)
    assert result.landing_zone.states[0].reachable_zone_id == "wp1_lz"
    assert result.landing_zone.states[0].divert_energy_wh == 0.0


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
    state = result.landing_zone.states[0]
    assert state.reachable_zone_id == "distant_lz"
    assert state.reserve_after_divert_wh < result.landing_zone.reserve_threshold_wh


def test_polygon_landing_zone_contains_route_state_with_zero_divert_energy() -> None:
    zone = LandingZone.model_validate(
        {
            "id": "area_lz",
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
    assert result.landing_zone.states[0].reachable_zone_distance_m == 0.0


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
                        "properties": {"surface": "grass"},
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
