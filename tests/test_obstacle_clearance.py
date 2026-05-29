import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from adapters.assets.obstacle_geojson import load_obstacles
from adapters.cli import CliExitCode, app
from estimator import EstimateStatus, FailureCode, try_estimate_mission_distance_time
from estimator.core.obstacle import Obstacle
from estimator.environment.obstacle import ListObstacleProvider
from estimator.environment.terrain import GridTerrainProvider
from schemas.mission import MissionPlan
from tests.helpers import make_mission, make_mission_payload, make_vehicle, make_vehicle_payload

_FIXTURE_ROOT = Path(__file__).parent / "fixtures"
_RUNNER = CliRunner()


def _point_obstacle_provider() -> ListObstacleProvider:
    obstacle = Obstacle.model_validate(
        {
            "id": "mast-midpoint",
            "geometry": {
                "type": "point",
                "points": [{"lat": 52.0005, "lon": 4.001}],
            },
            "height_m": 105.0,
            "radius_m": 20.0,
        }
    )
    return ListObstacleProvider([obstacle])


def _mission_with_obstacle_clearance() -> MissionPlan:
    mission = make_mission()
    constraints = mission.constraints.model_copy(
        update={"min_obstacle_clearance_m": 15.0}
    )
    return mission.model_copy(update={"constraints": constraints})


def _mission_with_terrain_clearance() -> MissionPlan:
    payload = make_mission_payload()
    payload["planned_home"]["altitude_amsl_m"] = 100.0
    payload["constraints"]["min_terrain_clearance_m"] = 30.0
    return MissionPlan.model_validate(payload)


def _ridge_provider() -> GridTerrainProvider:
    return GridTerrainProvider(
        origin_lat=52.0,
        origin_lon=4.0,
        step_lat_deg=0.0005,
        step_lon_deg=0.001,
        elevations_m=[
            [0.0, 0.0, 0.0],
            [0.0, 180.0, 0.0],
            [0.0, 0.0, 0.0],
        ],
    )


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_obstacle_inputs(tmp_path: Path) -> tuple[Path, Path]:
    obstacle_path = tmp_path / "obstacles.geojson"
    obstacle_path.write_text(
        (_FIXTURE_ROOT / "obstacles.geojson").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    mission_payload = make_mission_payload()
    mission_payload["constraints"]["min_obstacle_clearance_m"] = 15.0
    mission_payload["assets"] = {"obstacles_file": obstacle_path.name}
    vehicle_payload = make_vehicle_payload()

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, vehicle_payload)
    return mission_path, vehicle_path


def test_obstacle_clearance_violation_returns_infeasible() -> None:
    result = try_estimate_mission_distance_time(
        _mission_with_obstacle_clearance(),
        make_vehicle(),
        obstacle_provider=_point_obstacle_provider(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.OBSTACLE_CLEARANCE_VIOLATED
    assert result.failure.context["obstacle_id"] == "mast-midpoint"
    assert result.obstacle is not None
    assert result.obstacle.violations[0].obstacle_id == "mast-midpoint"


def test_terrain_clearance_checks_subsegment_between_waypoints() -> None:
    result = try_estimate_mission_distance_time(
        _mission_with_terrain_clearance(),
        make_vehicle(),
        terrain_provider=_ridge_provider(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.TERRAIN_CLEARANCE_VIOLATED
    assert result.obstacle is not None
    assert result.obstacle.violations[0].terrain_elevation_m == pytest.approx(
        180.0, abs=0.01
    )


def test_missing_obstacle_inputs_leaves_obstacle_block_inactive() -> None:
    result = try_estimate_mission_distance_time(make_mission(), make_vehicle())

    assert result.status == EstimateStatus.SUCCESS
    assert result.obstacle is None


def test_obstacle_loader_reads_fixture() -> None:
    provider, document = load_obstacles(_FIXTURE_ROOT / "obstacles.geojson")

    obstacles = provider.obstacles()
    assert document.format == "geojson"
    assert len(obstacles) == 1
    assert obstacles[0].id == "mast-midpoint"
    assert obstacles[0].height_m == pytest.approx(105.0)


def test_obstacle_outputs_surface_clearance_result(tmp_path: Path) -> None:
    mission_path, vehicle_path = _write_obstacle_inputs(tmp_path)

    json_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "json"]
    )
    checklist_result = _RUNNER.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--format", "checklist"],
    )
    summary_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "summary"]
    )
    markdown_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "markdown"]
    )
    geojson_result = _RUNNER.invoke(
        app, ["estimate", str(mission_path), str(vehicle_path), "--format", "geojson"]
    )

    assert json_result.exit_code == int(CliExitCode.INFEASIBLE)
    payload = json.loads(json_result.stdout)
    assert payload["result"]["obstacle"]["is_feasible"] is False
    assert "Obstacle clearance" in checklist_result.stdout
    assert "FAIL" in checklist_result.stdout
    assert "obstacle FAIL" in summary_result.stdout
    assert "## Obstacle Clearance" in markdown_result.stdout
    geojson = json.loads(geojson_result.stdout)
    obstacle_features = [
        feature
        for feature in geojson["features"]
        if feature["properties"]["layer"] == "obstacles"
    ]
    assert obstacle_features
    assert obstacle_features[0]["properties"]["conflict"] is True
