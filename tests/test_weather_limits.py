import yaml
from pathlib import Path

from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from estimator import (
    EstimateStatus,
    FailureCode,
    WarningCode,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.environment.wind import ConstantWindProvider
from schemas.mission import MissionPlan
from tests.helpers import make_mission_payload, make_vehicle, make_vehicle_payload

_RUNNER = CliRunner()


def _transit_mission(
    *,
    max_wind_mps: float | None = None,
    max_crosswind_mps: float | None = None,
    max_gust_mps: float | None = None,
    waypoint_lat: float = 52.0,
    waypoint_lon: float = 4.02,
) -> MissionPlan:
    """A takeoff -> waypoint -> rtl mission (no loiter, no station-keep)."""
    payload = make_mission_payload()
    payload["route"] = [
        {"id": "takeoff", "action": "vtol_takeoff", "altitude_m": 80.0},
        {
            "id": "wp1",
            "action": "waypoint",
            "lat": waypoint_lat,
            "lon": waypoint_lon,
            "altitude_m": 120.0,
        },
        {"id": "rtl", "action": "rtl"},
    ]
    constraints: dict = {"min_landing_reserve_percent": 25.0}
    if max_wind_mps is not None:
        constraints["max_wind_mps"] = max_wind_mps
    if max_crosswind_mps is not None:
        constraints["max_crosswind_mps"] = max_crosswind_mps
    if max_gust_mps is not None:
        constraints["max_gust_mps"] = max_gust_mps
    payload["constraints"] = constraints
    return MissionPlan.model_validate(payload)


def test_all_weather_failure_codes_are_exported() -> None:
    assert FailureCode.WIND_LIMIT_EXCEEDED
    assert FailureCode.GUST_LIMIT_EXCEEDED
    assert FailureCode.CROSSWIND_LIMIT_EXCEEDED


def test_sustained_wind_over_limit_is_infeasible() -> None:
    result = try_estimate_mission_distance_time(
        _transit_mission(max_wind_mps=5.0),
        make_vehicle(),
        wind_provider=ConstantWindProvider(10.0, 0.0),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.WIND_LIMIT_EXCEEDED
    assert result.weather is not None
    assert not result.weather.is_feasible
    assert result.weather.violations[0].observed_mps > 5.0


def test_wind_under_limit_is_feasible_with_weather_block() -> None:
    result = estimate_mission_distance_time(
        _transit_mission(max_wind_mps=10.0),
        make_vehicle(),
        wind_provider=ConstantWindProvider(5.0, 0.0),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.weather is not None
    assert result.weather.is_feasible
    assert result.weather.worst_wind_speed_mps == 5.0


def test_no_wind_provider_does_not_enforce_limits() -> None:
    result = estimate_mission_distance_time(
        _transit_mission(max_wind_mps=1.0),
        make_vehicle(),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.weather is None


def test_crosswind_over_limit_is_infeasible_for_known_heading() -> None:
    # Eastbound leg with a pure northerly wind: the whole wind vector is
    # crosswind, so an 8 m/s north wind yields ~8 m/s crosswind.
    result = try_estimate_mission_distance_time(
        _transit_mission(max_crosswind_mps=5.0, waypoint_lat=52.0, waypoint_lon=4.02),
        make_vehicle(),
        wind_provider=ConstantWindProvider(0.0, 8.0),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.CROSSWIND_LIMIT_EXCEEDED
    assert result.weather is not None
    assert result.weather.worst_crosswind_mps is not None
    assert result.weather.worst_crosswind_mps > 5.0


def test_gust_limit_without_gust_data_emits_advisory() -> None:
    result = estimate_mission_distance_time(
        _transit_mission(max_wind_mps=10.0, max_gust_mps=12.0),
        make_vehicle(),
        wind_provider=ConstantWindProvider(5.0, 0.0),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert WarningCode.GUST_DATA_UNAVAILABLE in {w.code for w in result.warnings}


def test_sustained_wind_at_limit_is_feasible() -> None:
    result = estimate_mission_distance_time(
        _transit_mission(max_wind_mps=10.0),
        make_vehicle(),
        wind_provider=ConstantWindProvider(10.0, 0.0),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.weather is not None
    assert result.weather.is_feasible


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_inputs(tmp_path: Path, *, max_wind_mps: float) -> tuple[Path, Path]:
    mission_payload = make_mission_payload()
    mission_payload["route"] = [
        {"id": "takeoff", "action": "vtol_takeoff", "altitude_m": 80.0},
        {"id": "wp1", "action": "waypoint", "lat": 52.0, "lon": 4.02, "altitude_m": 120.0},
        {"id": "rtl", "action": "rtl"},
    ]
    mission_payload["constraints"] = {
        "min_landing_reserve_percent": 25.0,
        "max_wind_mps": max_wind_mps,
    }
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())
    return mission_path, vehicle_path


def test_checklist_shows_weather_fail(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(tmp_path, max_wind_mps=5.0)

    result = _RUNNER.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "checklist",
            "--wind-layer",
            "0:10:0",
        ],
    )

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "Weather limits" in result.stdout
    assert "FAIL" in result.stdout
    assert "WIND_LIMIT_EXCEEDED" in result.stdout
    assert "Status: NO-GO" in result.stdout


def test_checklist_shows_weather_pass(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(tmp_path, max_wind_mps=20.0)

    result = _RUNNER.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "checklist",
            "--wind-layer",
            "0:5:0",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Weather limits" in result.stdout
    assert "Status: GO" in result.stdout


def test_summary_shows_weather_fail(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_inputs(tmp_path, max_wind_mps=5.0)

    result = _RUNNER.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "summary",
            "--wind-layer",
            "0:10:0",
        ],
    )

    assert "weather FAIL" in result.stdout
