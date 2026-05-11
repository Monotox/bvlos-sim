import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from estimator import (
    EstimateStatus,
    FailureCode,
    try_estimate_mission_distance_time,
)
from estimator.core.scenario import ScenarioStatus
from estimator.execution.scenario import run_scenario
from schemas import LinkSystemConfig, ResourceSystemConfig, ScenarioPlan
from tests.helpers import make_mission, make_mission_payload, make_vehicle, make_vehicle_payload

runner = CliRunner()


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_external_power_resource_can_replace_battery_capacity_feasibility() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 30.0
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "fiber-power",
                "kind": "external_power",
                "delivery": "optical_fiber",
                "continuous_power_w": 2000.0,
            }
        )
    ]

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.SUCCESS
    assert result.energy is not None
    assert result.energy.is_feasible is False
    assert result.resource is not None
    assert result.resource.is_feasible is True
    assert result.resource.selected_resource_id == "fiber-power"


def test_resource_failure_has_full_mission_result_validity(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    vehicle_payload = make_vehicle_payload()
    vehicle_payload["resource_systems"] = [
        {
            "resource_id": "short-tether",
            "kind": "external_power",
            "delivery": "tethered",
            "continuous_power_w": 2000.0,
            "max_tether_length_m": 1.0,
        }
    ]
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, vehicle_payload)

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    envelope = json.loads(result.stdout)
    assert envelope["diagnostics"][-1]["code"] == FailureCode.RESOURCE_FEASIBILITY_FAILED
    assert envelope["result_validity"]["scope"] == "full_mission"
    assert envelope["result_validity"]["is_complete"] is True
    assert envelope["result"]["resource"]["is_feasible"] is False


def test_link_failure_has_full_mission_result_validity(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["link_systems"] = [
        {
            "link_id": "short-radio",
            "kind": "direct_radio",
            "max_range_m": 1.0,
        }
    ]
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    envelope = json.loads(result.stdout)
    assert envelope["diagnostics"][-1]["code"] == FailureCode.LINK_FEASIBILITY_FAILED
    assert envelope["result_validity"]["scope"] == "full_mission"
    assert envelope["result_validity"]["is_complete"] is True
    assert envelope["result"]["link"]["is_feasible"] is False


def test_unsupported_reserved_resource_system_returns_structured_failure() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "future-hydrogen",
                "kind": "hydrogen",
            }
        )
    ]

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.RESOURCE_FEASIBILITY_FAILED
    assert result.failure.kind == "unsupported"
    assert result.resource is not None
    assert result.resource.systems[0].limiting_reason == "unsupported_resource_system"


def test_scenario_link_systems_override_mission_link_systems() -> None:
    mission = make_mission()
    mission.link_systems = [
        LinkSystemConfig.model_validate(
            {
                "link_id": "short-radio",
                "kind": "direct_radio",
                "max_range_m": 1.0,
            }
        )
    ]
    scenario = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "scenario-link-override",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "link_systems": [
                    {
                        "link_id": "satcom",
                        "kind": "starlink",
                        "max_range_m": 100000.0,
                    }
                ]
            },
            "assertions": [
                {
                    "assertion_id": "link-feasible",
                    "kind": "field_eq",
                    "field_path": "estimate.link.is_feasible",
                    "expected": True,
                }
            ],
        }
    )

    result = run_scenario(scenario, mission, make_vehicle())

    assert result.status == ScenarioStatus.PASSED
    assert result.estimate is not None
    assert result.estimate.link is not None
    assert result.estimate.link.selected_link_id == "satcom"
