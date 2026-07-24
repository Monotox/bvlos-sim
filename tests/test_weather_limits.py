import yaml
from pathlib import Path

import pytest
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from estimator import (
    EstimateStatus,
    FailureCode,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.environment.wind import (
    ConstantWindProvider,
    LayeredWindProvider,
    TimedWindChange,
    TimeVaryingWindProvider,
    WindLayer,
)
from schemas.mission import AltitudeReference, MissionAction, MissionPlan, RouteItem
from tests.helpers import (
    make_mission,
    make_mission_payload,
    make_vehicle,
    make_vehicle_payload,
)

_RUNNER = CliRunner()


def _transit_mission(
    *,
    max_wind_mps: float | None = None,
    max_crosswind_mps: float | None = None,
    max_gust_mps: float | None = None,
    min_visibility_m: float | None = None,
    max_precipitation_mm_h: float | None = None,
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
    constraints: dict = {
        "min_landing_reserve_percent": 25.0,
        "require_rth_reserve": False,
    }
    if max_wind_mps is not None:
        constraints["max_wind_mps"] = max_wind_mps
    if max_crosswind_mps is not None:
        constraints["max_crosswind_mps"] = max_crosswind_mps
    if max_gust_mps is not None:
        constraints["max_gust_mps"] = max_gust_mps
    if min_visibility_m is not None:
        constraints["min_visibility_m"] = min_visibility_m
    if max_precipitation_mm_h is not None:
        constraints["max_precipitation_mm_h"] = max_precipitation_mm_h
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


def test_gust_limit_without_gust_data_fails_closed() -> None:
    result = try_estimate_mission_distance_time(
        _transit_mission(max_wind_mps=10.0, max_gust_mps=12.0),
        make_vehicle(),
        wind_provider=ConstantWindProvider(5.0, 0.0),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.WEATHER_DATA_UNAVAILABLE
    assert "constraints.max_gust_mps" in result.failure.context["unavailable_fields"]


def test_visibility_limit_without_observations_fails_closed() -> None:
    result = try_estimate_mission_distance_time(
        _transit_mission(min_visibility_m=5_000.0),
        make_vehicle(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.WEATHER_DATA_UNAVAILABLE
    assert (
        "constraints.min_visibility_m" in result.failure.context["unavailable_fields"]
    )


def test_precipitation_limit_without_observations_fails_closed() -> None:
    result = try_estimate_mission_distance_time(
        _transit_mission(max_precipitation_mm_h=0.0),
        make_vehicle(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.WEATHER_DATA_UNAVAILABLE
    assert (
        "constraints.max_precipitation_mm_h"
        in result.failure.context["unavailable_fields"]
    )


def test_sustained_wind_at_limit_is_feasible() -> None:
    result = estimate_mission_distance_time(
        _transit_mission(max_wind_mps=10.0),
        make_vehicle(),
        wind_provider=ConstantWindProvider(10.0, 0.0),
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.weather is not None
    assert result.weather.is_feasible


def test_vertical_leg_is_included_in_sustained_wind_check() -> None:
    mission = _transit_mission(max_wind_mps=5.0)
    vertical = mission.route[0]
    vertical.altitude_m = 80.0
    mission.route = [vertical]

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        wind_provider=ConstantWindProvider(10.0, 0.0),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.WIND_LIMIT_EXCEEDED
    assert result.weather is not None
    assert result.weather.checked_leg_count == 1


def test_hover_loiter_checks_wind_change_during_full_dwell() -> None:
    mission = _transit_mission()
    loiter = mission.route[1]
    loiter.action = MissionAction.LOITER_TIME
    loiter.lat = mission.planned_home.lat
    loiter.lon = mission.planned_home.lon
    loiter.altitude_reference = AltitudeReference.AMSL
    loiter.altitude_m = mission.planned_home.altitude_amsl_m
    loiter.loiter_time_s = 120.0
    mission.route = [loiter]
    provider = TimeVaryingWindProvider(
        ConstantWindProvider(0.0, 0.0),
        [
            TimedWindChange(
                effective_elapsed_time_s=30.0,
                provider=ConstantWindProvider(10.0, 0.0),
            )
        ],
    )

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        wind_provider=provider,
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.STATION_KEEP_INFEASIBLE_WIND
    assert result.failure.context["elapsed_time_s"] == 30.0


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_inputs(tmp_path: Path, *, max_wind_mps: float) -> tuple[Path, Path]:
    mission_payload = make_mission_payload()
    mission_payload["route"] = [
        {"id": "takeoff", "action": "vtol_takeoff", "altitude_m": 80.0},
        {
            "id": "wp1",
            "action": "waypoint",
            "lat": 52.0,
            "lon": 4.02,
            "altitude_m": 120.0,
        },
        {"id": "rtl", "action": "rtl"},
    ]
    mission_payload["constraints"] = {
        "min_landing_reserve_percent": 25.0,
        "require_rth_reserve": False,
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

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "Weather limits" in result.stdout
    assert "worst wind 5.00 m/s" in result.stdout
    assert any(
        "Weather limits" in line and "PASS" in line
        for line in result.stdout.splitlines()
    )
    assert "Status: NO-GO" in result.stdout


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


def test_wind_limit_sees_the_altitudes_a_climb_dominated_leg_reaches() -> None:
    """A leg whose climb outlasts its ground track must still be observed.

    The stored per-leg wind comes from the horizontal integration, whose
    elapsed time runs out early when the climb takes longer than the ground
    track. The altitudes above that point were never queried, so the wind limit
    was evaluated on the departure-end wind and a 10 m/s band went unseen.
    """

    provider = LayeredWindProvider(
        [
            WindLayer(altitude_m=0.0, wind_east_mps=2.0, wind_north_mps=0.0),
            WindLayer(altitude_m=300.0, wind_east_mps=10.0, wind_north_mps=0.0),
        ]
    )

    def run(delta_lon: float):
        mission = make_mission()
        mission.constraints.require_rth_reserve = False
        mission.constraints.max_wind_mps = 8.0
        mission.route = [
            RouteItem(
                id="up",
                action=MissionAction.WAYPOINT,
                lat=52.0,
                lon=4.0 + delta_lon,
                altitude_reference=AltitudeReference.AMSL,
                altitude_m=320.0,
            )
        ]
        return try_estimate_mission_distance_time(
            mission, make_vehicle(), wind_provider=provider
        )

    climb_dominated = run(0.006)
    horizontal_dominated = run(0.05)

    for result in (climb_dominated, horizontal_dominated):
        assert result.weather is not None
        assert result.weather.is_feasible is False
        assert result.weather.worst_wind_speed_mps == pytest.approx(10.0)
        assert result.status == EstimateStatus.INFEASIBLE

    climb_leg = next(
        leg for leg in climb_dominated.legs if leg.route_item_id == "up"
    )
    # The defect only appears when the vertical phase outlasts the ground track.
    assert climb_leg.horizontal_distance_m < 1_000.0
