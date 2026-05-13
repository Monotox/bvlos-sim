"""Tests proving all implemented features are accessible via YAML configuration.

Covers: fidelity, max_segment_length_m, min_groundspeed_mps, and wind_layers
in both mission estimation and scenario initial_conditions.
"""

import math
from pathlib import Path

import pytest
from pydantic import ValidationError

from adapters.io import load_mission, load_vehicle
from adapters.scenario_io import load_scenario, resolve_scenario_asset_path
from estimator import (
    LegPhase,
    estimate_mission_distance_time,
    run_scenario,
)
from schemas import MissionEstimation
from schemas.scenario import ScenarioInitialConditions, ScenarioPlan
from tests.helpers import make_mission, make_vehicle

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scenario_plan(**ic_overrides) -> ScenarioPlan:
    ic = {"wind_east_mps": 0.0, "wind_north_mps": 0.0}
    ic.update(ic_overrides)
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "yaml-config-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": ic,
            "events": [],
            "assertions": [],
        }
    )


# ---------------------------------------------------------------------------
# MissionEstimation schema — new fields accepted
# ---------------------------------------------------------------------------


def test_mission_estimation_fidelity_v2_accepted() -> None:
    me = MissionEstimation.model_validate({"fidelity": "v2"})
    assert me.fidelity == "v2"


def test_mission_estimation_fidelity_defaults_to_v1() -> None:
    me = MissionEstimation.model_validate({})
    assert me.fidelity == "v1"


def test_mission_estimation_fidelity_rejects_invalid() -> None:
    with pytest.raises(ValidationError):
        MissionEstimation.model_validate({"fidelity": "v3"})


def test_mission_estimation_max_segment_length_m_accepted() -> None:
    me = MissionEstimation.model_validate({"max_segment_length_m": 500.0})
    assert me.max_segment_length_m == 500.0


def test_mission_estimation_max_segment_length_m_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        MissionEstimation.model_validate({"max_segment_length_m": 0.0})


def test_mission_estimation_wind_layers_accepted() -> None:
    me = MissionEstimation.model_validate(
        {
            "wind_layers": [
                {"altitude_m": 0.0, "wind_east_mps": 3.0, "wind_north_mps": 0.0},
                {"altitude_m": 500.0, "wind_east_mps": 6.0, "wind_north_mps": -1.0},
            ]
        }
    )
    assert len(me.wind_layers) == 2
    assert me.wind_layers[0].wind_east_mps == 3.0


def test_mission_estimation_wind_layers_none_by_default() -> None:
    me = MissionEstimation.model_validate({})
    assert me.wind_layers is None


# ---------------------------------------------------------------------------
# ScenarioInitialConditions schema — new fields accepted
# ---------------------------------------------------------------------------


def test_scenario_ic_fidelity_v2_accepted() -> None:
    ic = ScenarioInitialConditions.model_validate({"fidelity": "v2"})
    assert ic.fidelity == "v2"


def test_scenario_ic_fidelity_defaults_to_v1() -> None:
    ic = ScenarioInitialConditions.model_validate({})
    assert ic.fidelity == "v1"


def test_scenario_ic_min_groundspeed_mps_accepted() -> None:
    ic = ScenarioInitialConditions.model_validate({"min_groundspeed_mps": 2.0})
    assert ic.min_groundspeed_mps == 2.0


def test_scenario_ic_min_groundspeed_mps_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioInitialConditions.model_validate({"min_groundspeed_mps": 0.0})


def test_scenario_ic_wind_layers_accepted() -> None:
    ic = ScenarioInitialConditions.model_validate(
        {
            "wind_layers": [
                {"altitude_m": 0.0, "wind_east_mps": 5.0, "wind_north_mps": 0.0},
            ]
        }
    )
    assert len(ic.wind_layers) == 1


def test_scenario_ic_wind_layers_none_by_default() -> None:
    ic = ScenarioInitialConditions.model_validate({})
    assert ic.wind_layers is None


# ---------------------------------------------------------------------------
# Mission YAML fidelity → estimator behavior
# ---------------------------------------------------------------------------


def test_mission_yaml_fidelity_v2_activates_turn_arcs() -> None:
    """fidelity: v2 in mission estimation YAML must produce TURN_ARC legs."""
    from schemas.mission import MissionAction, RouteItem

    mission = make_mission()
    mission.estimation = MissionEstimation.model_validate({"fidelity": "v2"})
    # Two waypoints with a clear ~90° heading change
    wp1 = RouteItem(id="north", action=MissionAction.WAYPOINT, lat=52.01, lon=4.0, altitude_m=120.0)
    wp2 = RouteItem(id="east", action=MissionAction.WAYPOINT, lat=52.01, lon=4.02, altitude_m=120.0)
    mission.route = [wp1, wp2, mission.route[-1]]

    result = estimate_mission_distance_time(mission, make_vehicle())
    assert any(leg.phase == LegPhase.TURN_ARC for leg in result.legs)


def test_mission_yaml_fidelity_v1_no_turn_arcs() -> None:
    """fidelity: v1 (default) must not produce TURN_ARC legs."""
    mission = make_mission()
    mission.estimation = MissionEstimation.model_validate({"fidelity": "v1"})

    result = estimate_mission_distance_time(mission, make_vehicle())
    assert not any(leg.phase == LegPhase.TURN_ARC for leg in result.legs)


def test_mission_yaml_fidelity_v2_metadata() -> None:
    """estimator_version metadata must read 'v2' when fidelity v2 comes from mission YAML."""
    mission = make_mission()
    mission.estimation = MissionEstimation.model_validate({"fidelity": "v2"})

    result = estimate_mission_distance_time(mission, make_vehicle())
    assert result.metadata["estimator_version"] == "v2"


# ---------------------------------------------------------------------------
# Mission YAML wind_layers → LayeredWindProvider behavior
# ---------------------------------------------------------------------------


def test_mission_yaml_wind_layers_change_leg_wind_fields() -> None:
    """wind_layers in mission estimation YAML must apply to leg wind fields."""
    mission = make_mission()
    # No wind_layers — zero wind
    r_no_wind = estimate_mission_distance_time(mission, make_vehicle())

    # Easterly layered wind (within station-keep limit of 8 m/s)
    mission.estimation = MissionEstimation.model_validate(
        {
            "wind_layers": [
                {"altitude_m": 0.0, "wind_east_mps": 5.0, "wind_north_mps": 0.0},
            ]
        }
    )
    r_wind = estimate_mission_distance_time(mission, make_vehicle())

    assert r_wind.total_time_s != r_no_wind.total_time_s


def test_mission_yaml_wind_layers_runtime_options_override() -> None:
    """Runtime options (CLI) must override mission YAML wind_layers."""
    from estimator import ConstantWindProvider

    mission = make_mission()
    mission.estimation = MissionEstimation.model_validate(
        {
            "wind_layers": [
                {"altitude_m": 0.0, "wind_east_mps": 5.0, "wind_north_mps": 0.0},
            ]
        }
    )
    # Passing a runtime wind_provider overrides mission yaml wind_layers
    zero_wind_provider = ConstantWindProvider(0.0, 0.0)
    r_overridden = estimate_mission_distance_time(
        mission, make_vehicle(), wind_provider=zero_wind_provider
    )
    r_no_layers = estimate_mission_distance_time(make_mission(), make_vehicle())

    assert math.isclose(r_overridden.total_time_s, r_no_layers.total_time_s, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# Scenario YAML fidelity → run_scenario behavior
# ---------------------------------------------------------------------------


def test_scenario_yaml_fidelity_v2_activates_turn_arcs() -> None:
    """fidelity: v2 in scenario initial_conditions must produce TURN_ARC legs."""
    from schemas.mission import MissionAction, RouteItem

    mission = make_mission()
    wp1 = RouteItem(id="north", action=MissionAction.WAYPOINT, lat=52.01, lon=4.0, altitude_m=120.0)
    wp2 = RouteItem(id="east", action=MissionAction.WAYPOINT, lat=52.01, lon=4.02, altitude_m=120.0)
    mission.route = [wp1, wp2, mission.route[-1]]

    plan = _make_scenario_plan(fidelity="v2")
    result = run_scenario(plan, mission, make_vehicle())

    assert any(leg.phase == LegPhase.TURN_ARC for leg in result.estimate.legs)


def test_scenario_yaml_fidelity_default_is_v1() -> None:
    plan = _make_scenario_plan()
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.estimate.metadata["estimator_version"] == "v1"


# ---------------------------------------------------------------------------
# Scenario YAML wind_layers → run_scenario behavior
# ---------------------------------------------------------------------------


def test_scenario_yaml_wind_layers_applied() -> None:
    """wind_layers in scenario initial_conditions must affect estimation time."""
    plan_no_wind = _make_scenario_plan()
    plan_wind = _make_scenario_plan(
        wind_layers=[
            {"altitude_m": 0.0, "wind_east_mps": 5.0, "wind_north_mps": 0.0},
        ]
    )
    mission = make_mission()
    vehicle = make_vehicle()

    r_no_wind = run_scenario(plan_no_wind, mission, vehicle)
    r_wind = run_scenario(plan_wind, mission, vehicle)

    assert r_wind.estimate.total_time_s != r_no_wind.estimate.total_time_s


# ---------------------------------------------------------------------------
# Scenario YAML min_groundspeed_mps → run_scenario behavior
# ---------------------------------------------------------------------------


def test_scenario_yaml_min_groundspeed_mps_propagated() -> None:
    """min_groundspeed_mps in scenario initial_conditions must reach the estimator."""
    plan = _make_scenario_plan(min_groundspeed_mps=12.0)
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.estimate is not None
    # When a non-default min_groundspeed is set, the library-default marker must be absent.
    assert "applied_default_min_groundspeed_mps" not in result.estimate.metadata


# ---------------------------------------------------------------------------
# Mission YAML max_segment_length_m → estimator behavior
# ---------------------------------------------------------------------------


def test_mission_yaml_max_segment_length_m_propagated() -> None:
    """max_segment_length_m in mission estimation YAML must affect wind sampling.

    A long leg climbing through a wind shear boundary will yield a different
    total_time_s when sampled at 100 m intervals vs. at a single midpoint.
    """
    from schemas.mission import AltitudeReference, RouteItem, MissionAction

    mission_coarse = make_mission()
    mission_fine = make_mission()

    # 5 km east leg crossing a strong wind shear at 100 m amsl.
    wp = RouteItem(
        id="east-far",
        action=MissionAction.WAYPOINT,
        lat=52.0,
        lon=4.073,
        altitude_reference=AltitudeReference.AMSL,
        altitude_m=200.0,
    )
    layers = [
        {"altitude_m": 0.0, "wind_east_mps": -8.0, "wind_north_mps": 0.0},
        {"altitude_m": 120.0, "wind_east_mps": 8.0, "wind_north_mps": 0.0},
    ]
    # coarse: one sample per leg (no max_segment_length_m)
    mission_coarse.route = [wp]
    mission_coarse.estimation = MissionEstimation.model_validate({"wind_layers": layers})
    # fine: sample every 50 m
    mission_fine.route = [wp]
    mission_fine.estimation = MissionEstimation.model_validate(
        {"max_segment_length_m": 50.0, "wind_layers": layers}
    )

    result_coarse = estimate_mission_distance_time(mission_coarse, make_vehicle())
    result_fine = estimate_mission_distance_time(mission_fine, make_vehicle())
    # Dense sub-segment sampling should produce a different total time than a single sample.
    assert result_coarse.total_time_s != result_fine.total_time_s


def test_example_yaml_files_round_trip_through_loaders_and_runtime() -> None:
    mission, _ = load_mission(ROOT / "examples/missions/pipeline_demo_001.yaml")
    vehicle, _ = load_vehicle(ROOT / "examples/vehicles/quadplane_v1.yaml")

    estimate = estimate_mission_distance_time(mission, vehicle)

    assert estimate.status == "success"


def test_example_v2_scenario_yaml_round_trips_through_loader_and_runtime() -> None:
    scenario_path = ROOT / "examples/scenarios/pipeline_demo_001_v2_scenario.yaml"
    scenario, _ = load_scenario(scenario_path)
    mission, _ = load_mission(
        resolve_scenario_asset_path(scenario.mission_file, scenario_path=scenario_path)
    )
    vehicle, _ = load_vehicle(
        resolve_scenario_asset_path(scenario.vehicle_file, scenario_path=scenario_path)
    )

    result = run_scenario(scenario, mission, vehicle)

    assert result.status == "passed"
    assert result.estimate.metadata["estimator_version"] == "v2"
