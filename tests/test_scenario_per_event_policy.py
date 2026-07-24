"""Tests for per-event lost-link policy overrides."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from bvlos_sim.adapters.cli import ScenarioExitCode, app
from bvlos_sim.estimator import LandingZone
from bvlos_sim.estimator.execution.scenario import run_scenario
from bvlos_sim.schemas.scenario import ScenarioEvent, ScenarioPlan
from tests.helpers import make_mission, make_vehicle

REPO_ROOT = Path(__file__).resolve().parents[1]
_runner = CliRunner()


def _plan(
    *,
    events: list[dict],
    lost_link_policy: dict | None = None,
) -> ScenarioPlan:
    initial_conditions: dict = {"wind_east_mps": 0.0, "wind_north_mps": 0.0}
    if lost_link_policy is not None:
        initial_conditions["lost_link_policy"] = lost_link_policy
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "per-event-policy-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": initial_conditions,
            "events": events,
            "assertions": [],
        }
    )


def _lost_link_event(event_id: str, **overrides: object) -> dict:
    event = {
        "event_id": event_id,
        "kind": "lost_link",
        "trigger": "at_mission_start",
    }
    event.update(overrides)
    return event


def _landing_zone() -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": "lz-near",
            "altitude_amsl_m": 12.0,
            "geometry": {"points": [{"lat": 52.001, "lon": 4.002}]},
        }
    )


def _outcome_actions(plan: ScenarioPlan) -> dict[str, str | None]:
    result = run_scenario(plan, make_mission(), make_vehicle())
    return {
        outcome.event_id: (
            None if outcome.policy_outcome is None else outcome.policy_outcome.action
        )
        for outcome in result.event_outcomes
    }


def test_per_event_policy_overrides_global_policy() -> None:
    plan = _plan(
        events=[
            _lost_link_event(
                "link-loss",
                policy={"action": "land", "loiter_s": 0.0},
            )
        ],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )

    assert _outcome_actions(plan)["link-loss"] == "land"


def test_two_events_different_policies() -> None:
    plan = _plan(
        events=[
            _lost_link_event(
                "early-loss",
                trigger="at_route_item",
                trigger_route_item_id="wp1",
                policy={"action": "rtl", "loiter_s": 0.0},
            ),
            _lost_link_event(
                "mid-loss",
                trigger="at_route_item",
                trigger_route_item_id="loiter",
                policy={
                    "action": "divert",
                    "loiter_s": 0.0,
                    "divert_target_id": "lz-near",
                },
            ),
        ],
        lost_link_policy={"action": "land", "loiter_s": 0.0},
    )

    result = run_scenario(
        plan,
        make_mission(),
        make_vehicle(),
        landing_zones=[_landing_zone()],
    )
    outcomes = {
        outcome.event_id: outcome.policy_outcome for outcome in result.event_outcomes
    }

    assert outcomes["early-loss"] is not None
    assert outcomes["early-loss"].action == "rtl"
    assert outcomes["mid-loss"] is not None
    assert outcomes["mid-loss"].action == "divert"


def test_event_without_policy_uses_global() -> None:
    plan = _plan(
        events=[_lost_link_event("link-loss")],
        lost_link_policy={"action": "loiter", "loiter_s": 30.0},
    )

    assert _outcome_actions(plan)["link-loss"] == "loiter"


def test_policy_field_on_wind_change_event_raises_schema_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(
            {
                "event_id": "wind-shift",
                "kind": "wind_change",
                "trigger": "at_mission_start",
                "wind_east_mps": 3.0,
                "wind_north_mps": 0.0,
                "policy": {"action": "rtl", "loiter_s": 0.0},
            }
        )

    assert any(
        "policy is only valid on lost_link events" in error["msg"]
        for error in exc_info.value.errors()
    )


def test_per_event_policy_none_and_no_global_produces_no_outcome() -> None:
    plan = _plan(events=[_lost_link_event("link-loss")])
    result = run_scenario(plan, make_mission(), make_vehicle())

    assert result.event_outcomes[0].policy_outcome is None


def test_divert_policy_on_second_event_resolves_divert_estimate() -> None:
    plan = _plan(
        events=[
            _lost_link_event(
                "early-loss",
                trigger="at_route_item",
                trigger_route_item_id="wp1",
                policy={"action": "rtl", "loiter_s": 0.0},
            ),
            _lost_link_event(
                "mid-loss",
                trigger="at_route_item",
                trigger_route_item_id="loiter",
                policy={
                    "action": "divert",
                    "loiter_s": 0.0,
                    "divert_target_id": "lz-near",
                },
            ),
        ]
    )

    result = run_scenario(
        plan,
        make_mission(),
        make_vehicle(),
        landing_zones=[_landing_zone()],
    )
    second = result.event_outcomes[1].policy_outcome

    assert second is not None
    assert second.action == "divert"
    assert second.divert_estimate is not None
    assert isinstance(second.divert_estimate.is_feasible, bool)


def test_example_scenario_runs_via_cli() -> None:
    result = _runner.invoke(
        app,
        [
            "scenario",
            str(
                REPO_ROOT
                / "examples/scenarios/pipeline_demo_001_waypoint_policy_scenario.yaml"
            ),
            "--format",
            "summary",
            "--engineering-only",
        ],
    )

    assert result.exit_code == int(ScenarioExitCode.PASSED)
    assert "PASSED" in result.output
