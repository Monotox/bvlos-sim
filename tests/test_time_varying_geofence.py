"""Tests for time-varying geofence activation windows."""

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml
from typer.testing import CliRunner

from adapters.assets.geofence_geojson import load_geofences
from adapters.cli import CliExitCode, app
from estimator import (
    EstimateStatus,
    FailureCode,
    GeofenceKind,
    GeofenceRecurrence,
    GeofenceZone,
    WarningCode,
    try_estimate_mission_distance_time,
)
from schemas import MissionPlan
from tests.helpers import (
    make_mission,
    make_mission_payload,
    make_vehicle,
    make_vehicle_payload,
)

_runner = CliRunner()
_DEPARTURE_TIME = datetime(2026, 6, 1, 14, 0, 0, tzinfo=UTC)
_ACTIVE_FROM = datetime(2026, 6, 1, 20, 0, 0, tzinfo=UTC)


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _zone(
    *,
    active_from: datetime | None = None,
    active_until: datetime | None = None,
    recurrence: GeofenceRecurrence | None = None,
) -> GeofenceZone:
    payload = {
        "id": "event_tfr",
        "kind": GeofenceKind.FORBIDDEN,
        "geometry": {
            "polygons": [
                {
                    "exterior": [
                        {"lat": 51.999, "lon": 4.001},
                        {"lat": 52.003, "lon": 4.001},
                        {"lat": 52.003, "lon": 4.003},
                        {"lat": 51.999, "lon": 4.003},
                        {"lat": 51.999, "lon": 4.001},
                    ]
                }
            ]
        },
    }
    if active_from is not None:
        payload["active_from"] = active_from
    if active_until is not None:
        payload["active_until"] = active_until
    if recurrence is not None:
        payload["recurrence"] = recurrence
    return GeofenceZone.model_validate(payload)


def _mission_departing_at(departure_time: datetime) -> MissionPlan:
    mission = make_mission()
    mission.departure_time = departure_time
    return mission


def _mission_crossing_zone_after_2000() -> MissionPlan:
    payload = make_mission_payload()
    payload["departure_time"] = "2026-06-01T14:00:00Z"
    payload["route"] = [
        payload["route"][0],
        {
            "id": "wait_for_tfr",
            "action": "loiter_time",
            "lat": 52.0,
            "lon": 4.0,
            "altitude_m": 80.0,
            "loiter_time_s": 21600.0,
        },
        payload["route"][1],
    ]
    return MissionPlan.model_validate(payload)


def _large_battery_vehicle():
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 20000.0
    return vehicle


def test_time_windowed_geofence_inactive_before_active_from_is_feasible() -> None:
    result = try_estimate_mission_distance_time(
        _mission_departing_at(_DEPARTURE_TIME),
        make_vehicle(),
        geofences=[_zone(active_from=_ACTIVE_FROM)],
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.geofence is not None
    assert result.geofence.is_feasible is True


def test_time_windowed_geofence_active_after_active_from_is_infeasible() -> None:
    result = try_estimate_mission_distance_time(
        _mission_crossing_zone_after_2000(),
        _large_battery_vehicle(),
        geofences=[_zone(active_from=_ACTIVE_FROM)],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE


def test_time_windowed_geofence_missing_departure_time_warns_and_is_active() -> None:
    result = try_estimate_mission_distance_time(
        make_mission(),
        make_vehicle(),
        geofences=[_zone(active_from=_ACTIVE_FROM)],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE
    assert WarningCode.DEPARTURE_TIME_MISSING in {
        warning.code for warning in result.warnings
    }


def test_geofence_without_time_window_remains_always_active() -> None:
    result = try_estimate_mission_distance_time(
        _mission_departing_at(_DEPARTURE_TIME),
        make_vehicle(),
        geofences=[_zone()],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE


def test_geojson_loader_parses_time_window_properties(tmp_path: Path) -> None:
    geofence_path = tmp_path / "geofences.geojson"
    _write_json(
        geofence_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "daily_tfr",
                    "properties": {
                        "kind": "forbidden",
                        "active_from": "2026-06-01T20:00:00Z",
                        "active_until": "2026-06-01T22:00:00Z",
                        "recurrence": "daily",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [4.001, 51.999],
                                [4.003, 51.999],
                                [4.003, 52.003],
                                [4.001, 52.003],
                                [4.001, 51.999],
                            ]
                        ],
                    },
                }
            ],
        },
    )

    zones, _document = load_geofences(geofence_path)

    assert zones[0].active_from == _ACTIVE_FROM
    assert zones[0].active_until == datetime(2026, 6, 1, 22, 0, 0, tzinfo=UTC)
    assert zones[0].recurrence == GeofenceRecurrence.DAILY


def test_daily_recurring_geofence_applies_on_later_dates() -> None:
    result = try_estimate_mission_distance_time(
        _mission_departing_at(datetime(2026, 6, 2, 20, 0, 0, tzinfo=UTC)),
        make_vehicle(),
        geofences=[
            _zone(
                active_from=_ACTIVE_FROM,
                active_until=datetime(2026, 6, 1, 22, 0, 0, tzinfo=UTC),
                recurrence=GeofenceRecurrence.DAILY,
            )
        ],
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE


def test_checklist_shows_departure_time_when_set(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["departure_time"] = "2026-06-01T14:00:00Z"
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = _runner.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "checklist",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Departure time" in result.output
    assert "2026-06-01T14:00:00Z" in result.output
