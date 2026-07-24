"""Tests for deterministic scenario runner execution (scenario.v1)."""

import pytest
from pydantic import ValidationError

from bvlos_sim.estimator import LandingZone
from bvlos_sim.estimator.core.scenario import AssertionOutcome, ScenarioStatus
from bvlos_sim.estimator.environment.wind import LayeredWindProvider, WindLayer
from bvlos_sim.estimator.execution.scenario import run_scenario
from bvlos_sim.schemas.scenario import (
    ScenarioPlan,
)
from tests.helpers import make_mission, make_vehicle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _plan(
    *,
    events: list[dict] | None = None,
    assertions: list[dict] | None = None,
    scenario_id: str = "test",
    lost_link_policy: dict | None = None,
) -> ScenarioPlan:
    ic: dict = {"wind_east_mps": 0.0, "wind_north_mps": 0.0}
    if lost_link_policy is not None:
        ic["lost_link_policy"] = lost_link_policy
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": scenario_id,
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": ic,
            "events": events or [],
            "assertions": assertions or [],
        }
    )


def _plan_without_initial_wind() -> ScenarioPlan:
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "events": [],
            "assertions": [],
        }
    )


def _observe_event(event_id: str, trigger: str, **kwargs) -> dict:
    return {"event_id": event_id, "kind": "observe", "trigger": trigger, **kwargs}


def _lost_link_event(event_id: str, trigger: str, **kwargs) -> dict:
    return {"event_id": event_id, "kind": "lost_link", "trigger": trigger, **kwargs}


def _wind_change_event(event_id: str, trigger: str, **kwargs) -> dict:
    return {"event_id": event_id, "kind": "wind_change", "trigger": trigger, **kwargs}


def _assertion(assertion_id: str, kind: str, **kwargs) -> dict:
    return {"assertion_id": assertion_id, "kind": kind, **kwargs}


def _policy_assertion(assertion_id: str, event_id: str, expected: str) -> dict:
    return {
        "assertion_id": assertion_id,
        "kind": "policy_action_eq",
        "event_id": event_id,
        "expected": expected,
    }


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


def test_timeline_starts_with_mission_home() -> None:
    result = run_scenario(_plan(), make_mission(), make_vehicle())
    assert result.timeline[0].index == 0
    assert result.timeline[0].elapsed_time_s == 0.0
    assert result.timeline[0].route_item_id is None


def test_timeline_has_one_point_per_leg_plus_home() -> None:
    result = run_scenario(_plan(), make_mission(), make_vehicle())
    assert result.estimate is not None
    assert len(result.timeline) == len(result.estimate.legs) + 1


def test_timeline_indices_are_sequential() -> None:
    result = run_scenario(_plan(), make_mission(), make_vehicle())
    for i, point in enumerate(result.timeline):
        assert point.index == i


def test_timeline_elapsed_time_is_monotone() -> None:
    result = run_scenario(_plan(), make_mission(), make_vehicle())
    times = [p.elapsed_time_s for p in result.timeline]
    assert times == sorted(times)


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------


def test_no_assertions_gives_passed_status() -> None:
    result = run_scenario(_plan(), make_mission(), make_vehicle())
    assert result.status == ScenarioStatus.PASSED


def test_all_passing_assertions_gives_passed_status() -> None:
    plan = _plan(assertions=[_assertion("a1", "estimate_succeeds")])
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.status == ScenarioStatus.PASSED


def test_any_failed_assertion_gives_failed_status() -> None:
    plan = _plan(
        assertions=[
            _assertion("a1", "estimate_succeeds"),
            _assertion(
                "a2",
                "field_lt",
                field_path="estimate.total_time_s",
                expected=1.0,
            ),
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.status == ScenarioStatus.FAILED


# ---------------------------------------------------------------------------
# estimate_succeeds / estimate_fails assertions
# ---------------------------------------------------------------------------


def test_estimate_succeeds_passes_when_estimate_succeeds() -> None:
    plan = _plan(assertions=[_assertion("a1", "estimate_succeeds")])
    result = run_scenario(plan, make_mission(), make_vehicle())
    ar = result.assertion_results[0]
    assert ar.outcome == AssertionOutcome.PASSED


def test_estimate_fails_fails_when_estimate_succeeds() -> None:
    plan = _plan(assertions=[_assertion("a1", "estimate_fails")])
    result = run_scenario(plan, make_mission(), make_vehicle())
    ar = result.assertion_results[0]
    assert ar.outcome == AssertionOutcome.FAILED


# ---------------------------------------------------------------------------
# field_lt assertion
# ---------------------------------------------------------------------------


def test_field_lt_passes_when_actual_is_less_than_expected() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1", "field_lt", field_path="estimate.total_time_s", expected=3600.0
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_lt_fails_when_actual_is_not_less_than_expected() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1", "field_lt", field_path="estimate.total_time_s", expected=1.0
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.FAILED


# ---------------------------------------------------------------------------
# field_eq assertion with bool
# ---------------------------------------------------------------------------


def test_field_eq_with_bool_true_passes() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_eq",
                field_path="estimate.energy.is_feasible",
                expected=True,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_eq_with_bool_false_fails_when_true() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_eq",
                field_path="estimate.energy.is_feasible",
                expected=False,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.FAILED


# ---------------------------------------------------------------------------
# Unsupported / skipped field paths
# ---------------------------------------------------------------------------


def test_unsupported_field_path_rejected_at_schema_load() -> None:
    with pytest.raises(ValidationError, match="field_path.*is not supported"):
        _plan(
            assertions=[
                _assertion(
                    "a1",
                    "field_lt",
                    field_path="estimate.unknown_field",
                    expected=100.0,
                )
            ]
        )


def test_unsupported_field_path_error_lists_valid_paths() -> None:
    try:
        _plan(
            assertions=[
                _assertion(
                    "a1",
                    "field_lt",
                    field_path="estimate.unknown_field",
                    expected=100.0,
                )
            ]
        )
        pytest.fail("Expected ValidationError")
    except ValidationError as exc:
        msg = str(exc)
        assert "estimate.energy.total_energy_wh" in msg
        assert "estimate.totals_are_partial" in msg


def test_unavailable_field_gives_skipped_outcome() -> None:
    # energy.geofence.is_feasible requires a geofence, which is not set up here.
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_eq",
                field_path="estimate.geofence.is_feasible",
                expected=True,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_field_gt_total_energy_wh_passes_when_energy_positive() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_gt",
                field_path="estimate.energy.total_energy_wh",
                expected=0.0,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_gt_reserve_threshold_wh_passes_when_nonzero() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_gt",
                field_path="estimate.energy.reserve_threshold_wh",
                expected=0.0,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_eq_totals_are_partial_false_passes() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_eq",
                field_path="estimate.totals_are_partial",
                expected=False,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_gt_reserve_threshold_percent_passes_when_nonzero() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "a1",
                "field_gt",
                field_path="estimate.energy.reserve_threshold_percent",
                expected=0.0,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


# ---------------------------------------------------------------------------
# Event outcomes — observe
# ---------------------------------------------------------------------------


def test_observe_at_mission_start_fires_at_timeline_index_0() -> None:
    plan = _plan(events=[_observe_event("start", "at_mission_start")])
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.timeline_index == 0


def test_observe_at_mission_end_fires_at_last_timeline_index() -> None:
    plan = _plan(events=[_observe_event("end", "at_mission_end")])
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.timeline_index == len(result.timeline) - 1


def test_observe_at_route_item_fires_at_correct_index() -> None:
    plan = _plan(
        events=[
            _observe_event("loiter", "at_route_item", trigger_route_item_id="loiter")
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.timeline_index is not None
    # The loiter route item should appear in the timeline
    point = result.timeline[outcome.timeline_index]
    assert point.route_item_id == "loiter"


def test_observe_at_route_item_with_unknown_id_not_fired() -> None:
    plan = _plan(
        events=[
            _observe_event(
                "wp", "at_route_item", trigger_route_item_id="nonexistent-id"
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is False
    assert outcome.timeline_index is None


def test_observe_at_elapsed_time_beyond_mission_end_not_fired() -> None:
    plan = _plan(
        events=[
            _observe_event(
                "late-ev", "at_elapsed_time", trigger_elapsed_time_s=999_999.0
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is False
    assert outcome.timeline_index is None


# ---------------------------------------------------------------------------
# Event outcomes — wind_change
# ---------------------------------------------------------------------------


def test_wind_change_event_fires_and_changes_estimate_wind() -> None:
    plan = _plan(
        events=[
            _wind_change_event(
                "wind-gust",
                "at_mission_start",
                wind_east_mps=5.0,
                wind_north_mps=0.0,
            )
        ]
    )
    baseline = run_scenario(_plan(), make_mission(), make_vehicle())
    result = run_scenario(plan, make_mission(), make_vehicle())

    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.unsupported is False
    assert outcome.timeline_index == 0
    assert result.estimate is not None
    assert result.estimate.metadata["wind_provider_id"] == "time-varying"
    assert result.estimate.total_time_s != baseline.estimate.total_time_s
    assert any(leg.wind_east_mps == 5.0 for leg in result.estimate.legs)


def test_wind_change_event_at_unknown_route_item_does_not_fire() -> None:
    plan = _plan(
        events=[
            _wind_change_event(
                "wind-gust",
                "at_route_item",
                trigger_route_item_id="missing",
                wind_east_mps=5.0,
                wind_north_mps=0.0,
            )
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())

    outcome = result.event_outcomes[0]
    assert outcome.fired is False
    assert outcome.unsupported is False


def test_supplied_wind_provider_applies_when_initial_wind_is_unset() -> None:
    provider = LayeredWindProvider(
        [WindLayer(altitude_m=0.0, wind_east_mps=4.0, wind_north_mps=0.0)]
    )

    result = run_scenario(
        _plan_without_initial_wind(),
        make_mission(),
        make_vehicle(),
        wind_provider=provider,
    )

    assert result.estimate.metadata["wind_provider_id"] == "layered"


def test_explicit_initial_wind_overrides_supplied_wind_provider() -> None:
    provider = LayeredWindProvider(
        [WindLayer(altitude_m=0.0, wind_east_mps=4.0, wind_north_mps=0.0)]
    )

    result = run_scenario(
        _plan(),
        make_mission(),
        make_vehicle(),
        wind_provider=provider,
    )

    assert result.estimate.metadata["wind_provider_id"] == "constant"


# ---------------------------------------------------------------------------
# Event outcomes — lost_link (now supported)
# ---------------------------------------------------------------------------


def test_lost_link_event_fires_without_policy() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_elapsed_time", trigger_elapsed_time_s=30.0)]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.unsupported is False
    assert outcome.policy_outcome is None


def test_lost_link_event_fires_with_policy() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_elapsed_time", trigger_elapsed_time_s=30.0)],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.policy_outcome is not None
    assert outcome.policy_outcome.action == "rtl"


def test_lost_link_policy_action_is_recorded() -> None:
    for action in ("rtl", "land", "loiter"):
        plan = _plan(
            events=[_lost_link_event("ll", "at_mission_start")],
            lost_link_policy={"action": action, "loiter_s": 0.0},
        )
        result = run_scenario(plan, make_mission(), make_vehicle())
        assert result.event_outcomes[0].policy_outcome is not None
        assert result.event_outcomes[0].policy_outcome.action == action


def test_lost_link_policy_loiter_s_advances_action_time() -> None:
    loiter_s = 30.0
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        lost_link_policy={"action": "rtl", "loiter_s": loiter_s},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    po = result.event_outcomes[0].policy_outcome
    assert po is not None
    # action happens loiter_s after link loss
    assert po.action_at_elapsed_s == po.link_lost_at_elapsed_s + loiter_s


def test_lost_link_policy_action_position_is_valid_timeline_point() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_elapsed_time", trigger_elapsed_time_s=30.0)],
        lost_link_policy={"action": "land", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    po = result.event_outcomes[0].policy_outcome
    assert po is not None
    # The action position must match an actual timeline point
    tp = result.timeline[po.action_at_timeline_index]
    assert tp.lat == po.action_lat
    assert tp.lon == po.action_lon
    assert tp.altitude_amsl_m == po.action_altitude_amsl_m


def test_lost_link_event_at_mission_start_fires_at_index_0() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.timeline_index == 0
    po = outcome.policy_outcome
    assert po is not None
    assert po.link_lost_at_timeline_index == 0


# ---------------------------------------------------------------------------
# policy_action_eq assertion
# ---------------------------------------------------------------------------


def test_policy_action_eq_passes_when_action_matches() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_policy_assertion("a1", "ll", "rtl")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_policy_action_eq_fails_when_action_does_not_match() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_policy_assertion("a1", "ll", "land")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.FAILED


def test_policy_action_eq_skipped_when_event_not_fired() -> None:
    # Event fires at_route_item with a nonexistent id → not fired
    plan = _plan(
        events=[
            _lost_link_event(
                "ll", "at_route_item", trigger_route_item_id="no-such-item"
            )
        ],
        assertions=[_policy_assertion("a1", "ll", "rtl")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_not_fired_reason_set_for_unknown_route_item() -> None:
    plan = _plan(
        events=[
            _observe_event("obs", "at_route_item", trigger_route_item_id="no-such-wp")
        ],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is False
    assert outcome.not_fired_reason is not None
    assert "no-such-wp" in outcome.not_fired_reason


def test_not_fired_reason_set_for_exceeded_elapsed_time() -> None:
    plan = _plan(
        events=[
            _observe_event("obs", "at_elapsed_time", trigger_elapsed_time_s=99999.0)
        ],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is False
    assert outcome.not_fired_reason is not None
    assert "99999.0" in outcome.not_fired_reason


def test_not_fired_reason_none_when_event_fires() -> None:
    plan = _plan(events=[_observe_event("obs", "at_mission_start")])
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.not_fired_reason is None


def test_policy_action_eq_skipped_when_no_policy_configured() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_policy_assertion("a1", "ll", "rtl")],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_policy_assertion_with_unknown_event_id_raises_schema_error() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _plan(assertions=[_policy_assertion("a1", "nonexistent-event", "rtl")])
    assert any("nonexistent-event" in e["msg"] for e in exc_info.value.errors())


def test_policy_action_eq_carries_expected_and_actual() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_policy_assertion("a1", "ll", "land")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    ar = result.assertion_results[0]
    assert ar.outcome == AssertionOutcome.FAILED
    assert ar.expected == "land"
    assert ar.actual == "rtl"


def test_divert_policy_without_landing_zones_produces_infeasible_divert_estimate() -> (
    None
):
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        lost_link_policy={
            "action": "divert",
            "loiter_s": 0.0,
            "divert_target_id": "lz-alpha",
        },
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    po = result.event_outcomes[0].policy_outcome
    assert po is not None
    assert po.action == "divert"
    assert po.divert_estimate is not None
    assert po.divert_estimate.is_feasible is False
    assert po.divert_estimate.infeasible_reason is not None


# ---------------------------------------------------------------------------
# policy_divert_feasible assertion
# ---------------------------------------------------------------------------


def _divert_assertion(assertion_id: str, event_id: str) -> dict:
    return {
        "assertion_id": assertion_id,
        "kind": "policy_divert_feasible",
        "event_id": event_id,
    }


def test_policy_divert_feasible_skipped_when_event_not_fired() -> None:
    plan = _plan(
        events=[
            _lost_link_event("ll", "at_route_item", trigger_route_item_id="no-item")
        ],
        assertions=[_divert_assertion("a1", "ll")],
        lost_link_policy={
            "action": "divert",
            "loiter_s": 0.0,
            "divert_target_id": "lz-x",
        },
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_policy_divert_feasible_skipped_when_no_policy() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_divert_assertion("a1", "ll")],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_policy_divert_feasible_skipped_when_action_is_rtl() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_divert_assertion("a1", "ll")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_policy_divert_feasible_failed_when_no_landing_zones() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_divert_assertion("a1", "ll")],
        lost_link_policy={
            "action": "divert",
            "loiter_s": 0.0,
            "divert_target_id": "lz-alpha",
        },
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.FAILED
    assert "not feasible" in result.assertion_results[0].message


def test_policy_divert_feasible_requires_event_id_at_schema_level() -> None:
    with pytest.raises(ValidationError):
        ScenarioPlan.model_validate(
            {
                "schema_version": "scenario.v1",
                "scenario_id": "test",
                "mission_file": "m.yaml",
                "vehicle_file": "v.yaml",
                "events": [_lost_link_event("ll", "at_mission_start")],
                "assertions": [
                    {
                        "assertion_id": "a1",
                        "kind": "policy_divert_feasible",
                    }
                ],
            }
        )


def test_policy_divert_feasible_passed_when_route_is_feasible() -> None:
    zone = LandingZone.model_validate(
        {
            "id": "lz-near",
            "altitude_amsl_m": 12.0,
            "geometry": {"points": [{"lat": 52.001, "lon": 4.001}]},
        }
    )
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_divert_assertion("a1", "ll")],
        lost_link_policy={
            "action": "divert",
            "loiter_s": 0.0,
            "divert_target_id": "lz-near",
        },
    )
    result = run_scenario(plan, make_mission(), make_vehicle(), landing_zones=[zone])
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED
    assert "feasible" in result.assertion_results[0].message
    assert "reserve:" in result.assertion_results[0].message


# ---------------------------------------------------------------------------
# Repeatability
# ---------------------------------------------------------------------------


def test_two_runs_with_same_inputs_produce_identical_results() -> None:
    plan = _plan(
        events=[_observe_event("start", "at_mission_start")],
        assertions=[_assertion("a1", "estimate_succeeds")],
    )
    mission = make_mission()
    vehicle = make_vehicle()

    result_a = run_scenario(plan, mission, vehicle)
    result_b = run_scenario(plan, mission, vehicle)

    assert result_a.model_dump() == result_b.model_dump()


def test_scenario_is_marked_deterministic() -> None:
    result = run_scenario(_plan(), make_mission(), make_vehicle())
    assert result.deterministic is True


def test_max_segment_length_in_initial_conditions_propagates_to_options() -> None:
    """max_segment_length_m in initial_conditions reaches the estimator.

    With a constant wind, sub-segment sampling gives the same result.
    We verify it doesn't error and the result is deterministic.
    """
    plan = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "seg-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 2.0,
                "wind_north_mps": 0.0,
                "max_segment_length_m": 500.0,
            },
            "assertions": [{"assertion_id": "a1", "kind": "estimate_succeeds"}],
        }
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.status == ScenarioStatus.PASSED


def test_at_route_item_trigger_matches_first_occurrence() -> None:
    """_resolve_at_route_item returns the FIRST timeline index for a route item.

    The loiter item in make_mission() produces two legs (transit + dwell).
    The at_route_item trigger should fire at the first of those legs.
    """
    plan = _plan(
        events=[
            {
                "event_id": "loiter_event",
                "kind": "observe",
                "trigger": "at_route_item",
                "trigger_route_item_id": "loiter",
            }
        ],
        assertions=[
            {
                "assertion_id": "a1",
                "kind": "estimate_succeeds",
            }
        ],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    loiter_outcome = next(
        o for o in result.event_outcomes if o.event_id == "loiter_event"
    )
    assert loiter_outcome.fired is True
    # Timeline index must be the FIRST leg for this route item, not the last.
    # The loiter item has transit + dwell legs; the first is the transit.
    assert loiter_outcome.timeline_index is not None
    # The loiter dwell leg follows the transit leg. The first occurrence
    # has a strictly smaller index than the last.
    transit_index = loiter_outcome.timeline_index
    # Verify there's a later leg for the same route item (the dwell).
    timeline = result.timeline
    same_item_indices = [p.index for p in timeline if p.route_item_id == "loiter"]
    assert len(same_item_indices) >= 2
    assert transit_index == min(same_item_indices)


def test_field_resolvers_and_supported_paths_are_in_sync() -> None:
    # Guards against the private API drifting out of sync. Adding a new
    # assertion kind with a field_path requires updating both dicts.
    from bvlos_sim.estimator.execution.scenario_assertions import (
        _FIELD_RESOLVERS,
        _SUPPORTED_FIELD_PATHS,
    )

    assert set(_FIELD_RESOLVERS.keys()) == _SUPPORTED_FIELD_PATHS


def test_weather_and_ground_risk_field_paths_accepted_at_schema_load() -> None:
    # These feasibility/risk blocks exist in the estimate envelope and must be
    # assertable from scenarios, not only present in the JSON output.
    plan = _plan(
        assertions=[
            _assertion(
                "w1",
                "field_eq",
                field_path="estimate.weather.is_feasible",
                expected=True,
            ),
            _assertion(
                "w2",
                "field_le",
                field_path="estimate.weather.worst_wind_speed_mps",
                expected=12.0,
            ),
            _assertion(
                "g1",
                "field_le",
                field_path="estimate.ground_risk.mission_igrc",
                expected=7,
            ),
            _assertion(
                "r1", "field_eq", field_path="estimate.rth_is_feasible", expected=True
            ),
        ]
    )
    assert len(plan.assertions) == 4


def test_weather_and_ground_risk_field_resolvers_read_estimate_blocks() -> None:
    from bvlos_sim.estimator.core.enums import EstimateStatus
    from bvlos_sim.estimator.core.results import (
        GroundRiskEstimate,
        MissionEstimate,
        WeatherEstimate,
    )
    from bvlos_sim.estimator.execution.scenario_assertions import resolve_field_value

    estimate = MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=0.0,
        total_vertical_distance_m=0.0,
        total_path_distance_m=0.0,
        total_time_s=0.0,
        totals_are_partial=False,
        weather=WeatherEstimate(
            is_feasible=False,
            checked_leg_count=2,
            max_wind_mps=10.0,
            worst_wind_speed_mps=14.0,
        ),
        ground_risk=GroundRiskEstimate(
            characteristic_dimension_m=1.0,
            mission_igrc=6,
            legs=[],
        ),
    )

    assert resolve_field_value("estimate.weather.is_feasible", estimate) is False
    assert (
        resolve_field_value("estimate.weather.worst_wind_speed_mps", estimate) == 14.0
    )
    assert resolve_field_value("estimate.ground_risk.mission_igrc", estimate) == 6
    assert resolve_field_value("estimate.rth_is_feasible", estimate) is None


def test_rth_feasibility_field_is_assertable_from_scenario() -> None:
    plan = _plan(
        assertions=[
            _assertion(
                "rth",
                "field_eq",
                field_path="estimate.rth_is_feasible",
                expected=True,
            )
        ]
    )

    result = run_scenario(plan, make_mission(), make_vehicle())

    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_weather_field_resolver_returns_none_without_weather_block() -> None:
    from bvlos_sim.estimator.core.enums import EstimateStatus
    from bvlos_sim.estimator.core.results import MissionEstimate
    from bvlos_sim.estimator.execution.scenario_assertions import resolve_field_value

    estimate = MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=0.0,
        total_vertical_distance_m=0.0,
        total_path_distance_m=0.0,
        total_time_s=0.0,
        totals_are_partial=False,
    )
    assert resolve_field_value("estimate.weather.is_feasible", estimate) is None


def _make_turning_mission():
    """Mission with a ~90° heading change needed to produce v2 turn arcs."""
    from bvlos_sim.schemas.mission import MissionAction, RouteItem

    mission = make_mission()
    wp_north = RouteItem(
        id="north", action=MissionAction.WAYPOINT, lat=52.01, lon=4.0, altitude_m=120.0
    )
    wp_east = RouteItem(
        id="east", action=MissionAction.WAYPOINT, lat=52.01, lon=4.02, altitude_m=120.0
    )
    rtl = RouteItem(id="rtl", action=MissionAction.RTL)
    mission.route = [wp_north, wp_east, rtl]
    return mission


def test_scenario_without_explicit_fidelity_inherits_mission_fidelity_v2() -> None:
    from bvlos_sim.estimator.core.enums import LegPhase
    from bvlos_sim.schemas.mission import MissionEstimation

    mission = _make_turning_mission()
    mission.estimation = MissionEstimation(fidelity="v2")
    vehicle = make_vehicle()

    # Scenario with no explicit fidelity should inherit mission's v2 setting.
    plan = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "fidelity-inherit",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                # fidelity intentionally NOT set
            },
        }
    )

    result = run_scenario(plan, mission, vehicle)
    assert result.estimate is not None
    phases = {leg.phase for leg in result.estimate.legs}
    assert LegPhase.TURN_ARC in phases, (
        "v2 fidelity inherited from mission should produce turn arcs"
    )


def test_scenario_with_explicit_fidelity_v1_overrides_mission_v2() -> None:
    from bvlos_sim.estimator.core.enums import LegPhase
    from bvlos_sim.schemas.mission import MissionEstimation

    mission = _make_turning_mission()
    mission.estimation = MissionEstimation(fidelity="v2")
    vehicle = make_vehicle()

    plan = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "fidelity-override",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                "fidelity": "v1",
            },
        }
    )

    result = run_scenario(plan, mission, vehicle)
    assert result.estimate is not None
    phases = {leg.phase for leg in result.estimate.legs}
    assert LegPhase.TURN_ARC not in phases, (
        "explicit v1 in scenario should override mission v2"
    )
