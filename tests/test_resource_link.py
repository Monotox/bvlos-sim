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
from schemas import (
    AltitudeReference,
    LinkSystemConfig,
    ResourceSystemConfig,
    ScenarioPlan,
    UsableCapacityPoint,
)
from schemas.mission import MissionAction, RouteItem
from tests.helpers import (
    make_mission,
    make_mission_payload,
    make_vehicle,
    make_vehicle_payload,
)

runner = CliRunner()


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _one_way_mission():
    mission = make_mission()
    waypoint = mission.route[1]
    waypoint.lat = mission.planned_home.lat
    waypoint.lon = mission.planned_home.lon + 0.05
    mission.route = [waypoint]
    return mission


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
    assert result.rth_is_feasible is True


def test_external_power_must_cover_rth_peak_power() -> None:
    mission = _one_way_mission()
    mission.route[0].altitude_reference = AltitudeReference.AMSL
    mission.route[0].altitude_m = 0.0
    vehicle = make_vehicle()
    vehicle.energy.descent_power_w = 300.0
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "weak-external",
                "kind": "external_power",
                "continuous_power_w": 350.0,
            }
        )
    ]

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.RESOURCE_FEASIBILITY_FAILED
    assert result.resource is not None
    system = result.resource.systems[0]
    assert system.peak_power_w == 450.0
    assert system.limiting_reason == "power_limit_exceeded"
    assert result.rth_is_feasible is None


def test_external_power_reports_rth_shortfall_when_gate_is_disabled() -> None:
    mission = _one_way_mission()
    mission.constraints.require_rth_reserve = False
    # Keep the leg short enough that the descent dominates it, so the route
    # really does draw descent power while the RTH cruise peak does not fit.
    mission.route[0].lon = mission.planned_home.lon + 0.001
    mission.route[0].altitude_reference = AltitudeReference.AMSL
    mission.route[0].altitude_m = 0.0
    vehicle = make_vehicle()
    vehicle.energy.descent_power_w = 300.0
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "route-only-external",
                "kind": "external_power",
                "continuous_power_w": 400.0,
            }
        )
    ]

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.SUCCESS
    assert result.resource is not None and result.resource.is_feasible is True
    assert result.rth_is_feasible is False


def test_selected_onboard_resource_replaces_base_battery_rth_margin() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 30.0
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "large-pack",
                "kind": "onboard_battery",
                "battery_capacity_wh": 900.0,
            }
        )
    ]

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.SUCCESS
    assert result.energy is not None and result.energy.is_feasible is False
    assert result.resource is not None and result.resource.is_feasible is True
    assert result.resource.selected_resource_id == "large-pack"
    assert result.rth_is_feasible is True


def test_onboard_resource_fails_when_only_rth_reserve_is_insufficient() -> None:
    vehicle = make_vehicle()
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "small-pack",
                "kind": "onboard_battery",
                "battery_capacity_wh": 80.0,
            }
        )
    ]

    result = try_estimate_mission_distance_time(_one_way_mission(), vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.RESOURCE_FEASIBILITY_FAILED
    assert result.resource is not None
    system = result.resource.systems[0]
    assert system.reserve_after_resource_wh >= system.reserve_threshold_wh
    assert system.limiting_reason == "resource_rth_reserve_below_threshold"
    assert result.rth_is_feasible is None


def test_hybrid_resource_accounts_for_residual_rth_energy() -> None:
    vehicle = make_vehicle()
    vehicle.resource_systems = [
        ResourceSystemConfig.model_validate(
            {
                "resource_id": "small-hybrid",
                "kind": "hybrid",
                "battery_capacity_wh": 20.0,
                "continuous_power_w": 400.0,
            }
        )
    ]

    result = try_estimate_mission_distance_time(_one_way_mission(), vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.RESOURCE_FEASIBILITY_FAILED
    assert result.resource is not None
    system = result.resource.systems[0]
    assert system.reserve_after_resource_wh >= system.reserve_threshold_wh
    assert system.limiting_reason == "resource_rth_reserve_below_threshold"
    assert result.rth_is_feasible is None


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
    assert (
        envelope["diagnostics"][-1]["code"] == FailureCode.RESOURCE_FEASIBILITY_FAILED
    )
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


def test_declaring_a_resource_system_does_not_void_capacity_derating() -> None:
    """A resource system replaces the battery and RTH gates, not the derating.

    engine.py hands both gates to the resource path whenever any resource
    system is declared, and that path budgeted against the nameplate pack, so
    declaring one silently voided usable_capacity_curve: an INFEASIBLE mission
    became SUCCESS with RTH reported feasible.
    """

    def run(*, with_resource: bool, derated: bool):
        mission = make_mission()
        mission.constraints.require_rth_reserve = True
        mission.constraints.min_landing_reserve_percent = 25.0
        mission.route = [
            RouteItem(
                id="far",
                action=MissionAction.WAYPOINT,
                lat=mission.planned_home.lat,
                lon=mission.planned_home.lon + 0.05,
                altitude_m=120.0,
            )
        ]
        vehicle = make_vehicle()
        vehicle.energy.battery_capacity_wh = 170.0
        if derated:
            vehicle.energy.usable_capacity_curve = [
                UsableCapacityPoint(soc=0.0, usable_fraction=0.0),
                UsableCapacityPoint(soc=1.0, usable_fraction=0.55),
            ]
        if with_resource:
            vehicle.resource_systems = [
                ResourceSystemConfig.model_validate(
                    {"resource_id": "pack", "kind": "onboard_battery"}
                )
            ]
        return try_estimate_mission_distance_time(mission, vehicle)

    # Derated: infeasible either way. Declaring the resource system must not
    # buy back the 76.5 Wh the curve removed.
    assert run(with_resource=False, derated=True).status == EstimateStatus.INFEASIBLE
    assert run(with_resource=True, derated=True).status == EstimateStatus.INFEASIBLE

    # Control: with no curve the same mission is feasible on both paths, so the
    # gate above is the derating and not a blanket tightening.
    assert run(with_resource=False, derated=False).status == EstimateStatus.SUCCESS
    assert run(with_resource=True, derated=False).status == EstimateStatus.SUCCESS
