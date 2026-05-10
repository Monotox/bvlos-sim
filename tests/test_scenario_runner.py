"""Tests for deterministic scenario runner execution (scenario.v1)."""


from estimator.core.scenario import AssertionOutcome, ScenarioStatus
from estimator.execution.scenario import run_scenario
from schemas.scenario import (
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
    # mission has 4 route items expanded to 5 legs + home = 6 points
    assert len(result.timeline) == 6


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
    plan = _plan(
        assertions=[_assertion("a1", "estimate_succeeds")]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.status == ScenarioStatus.PASSED


def test_any_failed_assertion_gives_failed_status() -> None:
    plan = _plan(
        assertions=[
            _assertion("a1", "estimate_succeeds"),
            _assertion(
                "a2", "field_lt",
                field_path="estimate.total_time_s", expected=1.0,
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
            _assertion("a1", "field_lt",
                       field_path="estimate.total_time_s", expected=3600.0)
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_lt_fails_when_actual_is_not_less_than_expected() -> None:
    plan = _plan(
        assertions=[
            _assertion("a1", "field_lt",
                       field_path="estimate.total_time_s", expected=1.0)
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
            _assertion("a1", "field_eq",
                       field_path="estimate.energy.is_feasible", expected=True)
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.PASSED


def test_field_eq_with_bool_false_fails_when_true() -> None:
    plan = _plan(
        assertions=[
            _assertion("a1", "field_eq",
                       field_path="estimate.energy.is_feasible", expected=False)
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.FAILED


# ---------------------------------------------------------------------------
# Unsupported / skipped field paths
# ---------------------------------------------------------------------------


def test_unsupported_field_path_gives_unsupported_outcome() -> None:
    plan = _plan(
        assertions=[
            _assertion("a1", "field_lt",
                       field_path="estimate.unknown_field", expected=100.0)
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.UNSUPPORTED


def test_unavailable_field_gives_skipped_outcome() -> None:
    # energy.geofence.is_feasible requires a geofence, which is not set up here.
    plan = _plan(
        assertions=[
            _assertion("a1", "field_eq",
                       field_path="estimate.geofence.is_feasible", expected=True)
        ]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


# ---------------------------------------------------------------------------
# Event outcomes — observe
# ---------------------------------------------------------------------------


def test_observe_at_mission_start_fires_at_timeline_index_0() -> None:
    plan = _plan(
        events=[_observe_event("start", "at_mission_start")]
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    outcome = result.event_outcomes[0]
    assert outcome.fired is True
    assert outcome.timeline_index == 0


def test_observe_at_mission_end_fires_at_last_timeline_index() -> None:
    plan = _plan(
        events=[_observe_event("end", "at_mission_end")]
    )
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
            _observe_event("wp", "at_route_item", trigger_route_item_id="nonexistent-id")
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
            _lost_link_event("ll", "at_route_item", trigger_route_item_id="no-such-item")
        ],
        assertions=[_policy_assertion("a1", "ll", "rtl")],
        lost_link_policy={"action": "rtl", "loiter_s": 0.0},
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_policy_action_eq_skipped_when_no_policy_configured() -> None:
    plan = _plan(
        events=[_lost_link_event("ll", "at_mission_start")],
        assertions=[_policy_assertion("a1", "ll", "rtl")],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


def test_policy_action_eq_skipped_when_event_id_not_in_outcomes() -> None:
    plan = _plan(
        assertions=[_policy_assertion("a1", "nonexistent-event", "rtl")],
    )
    result = run_scenario(plan, make_mission(), make_vehicle())
    assert result.assertion_results[0].outcome == AssertionOutcome.SKIPPED


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
    loiter_outcome = next(o for o in result.event_outcomes if o.event_id == "loiter_event")
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
