"""Tests for scenario.v1 schema validation."""

import pytest
from pydantic import ValidationError

from schemas.scenario import (
    LostLinkPolicy,
    ScenarioAssertion,
    ScenarioAssertionKind,
    ScenarioEvent,
    ScenarioInitialConditions,
    ScenarioPlan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scenario_payload(**overrides) -> dict:
    base = {
        "schema_version": "scenario.v1",
        "scenario_id": "test-scenario",
        "mission_file": "mission.yaml",
        "vehicle_file": "vehicle.yaml",
    }
    base.update(overrides)
    return base


def _make_event(**overrides) -> dict:
    base = {
        "event_id": "evt1",
        "kind": "observe",
        "trigger": "at_mission_start",
    }
    base.update(overrides)
    return base


def _make_assertion(**overrides) -> dict:
    base = {
        "assertion_id": "a1",
        "kind": "estimate_succeeds",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# ScenarioPlan validation
# ---------------------------------------------------------------------------


def test_valid_scenario_plan_accepted() -> None:
    payload = _make_scenario_payload()
    plan = ScenarioPlan.model_validate(payload)
    assert plan.scenario_id == "test-scenario"
    assert plan.schema_version == "scenario.v1"


def test_invalid_schema_version_rejected() -> None:
    payload = _make_scenario_payload(schema_version="scenario.v2")
    with pytest.raises(ValidationError):
        ScenarioPlan.model_validate(payload)


def test_extra_fields_rejected() -> None:
    payload = _make_scenario_payload(unexpected_field=True)
    with pytest.raises(ValidationError):
        ScenarioPlan.model_validate(payload)


def test_duplicate_event_ids_rejected() -> None:
    events = [
        _make_event(event_id="dup"),
        _make_event(event_id="dup"),
    ]
    payload = _make_scenario_payload(events=events)
    with pytest.raises(ValidationError) as exc_info:
        ScenarioPlan.model_validate(payload)
    assert any("event ids must be unique" in e["msg"] for e in exc_info.value.errors())


def test_duplicate_assertion_ids_rejected() -> None:
    assertions = [
        _make_assertion(assertion_id="dup"),
        _make_assertion(assertion_id="dup"),
    ]
    payload = _make_scenario_payload(assertions=assertions)
    with pytest.raises(ValidationError) as exc_info:
        ScenarioPlan.model_validate(payload)
    assert any(
        "assertion ids must be unique" in e["msg"] for e in exc_info.value.errors()
    )


def test_unique_event_ids_accepted() -> None:
    events = [
        _make_event(event_id="e1"),
        _make_event(event_id="e2"),
    ]
    payload = _make_scenario_payload(events=events)
    plan = ScenarioPlan.model_validate(payload)
    assert len(plan.events) == 2


def test_empty_events_and_assertions_accepted() -> None:
    payload = _make_scenario_payload(events=[], assertions=[])
    plan = ScenarioPlan.model_validate(payload)
    assert plan.events == []
    assert plan.assertions == []


def test_policy_assertion_with_unknown_event_id_rejected() -> None:
    events = [_make_event(event_id="link-lost", kind="lost_link")]
    assertions = [
        _make_assertion(
            assertion_id="check",
            kind="policy_action_eq",
            event_id="no-such-event",
            expected="rtl",
        )
    ]
    payload = _make_scenario_payload(events=events, assertions=assertions)
    with pytest.raises(ValidationError) as exc_info:
        ScenarioPlan.model_validate(payload)
    assert any("no-such-event" in e["msg"] for e in exc_info.value.errors())


def test_policy_assertion_with_valid_event_id_accepted() -> None:
    events = [_make_event(event_id="link-lost", kind="lost_link")]
    assertions = [
        _make_assertion(
            assertion_id="check",
            kind="policy_action_eq",
            event_id="link-lost",
            expected="rtl",
        )
    ]
    payload = _make_scenario_payload(events=events, assertions=assertions)
    plan = ScenarioPlan.model_validate(payload)
    assert plan.assertions[0].event_id == "link-lost"


def test_policy_divert_feasible_accepted_without_expected() -> None:
    events = [_make_event(event_id="ll", kind="lost_link")]
    assertions = [
        _make_assertion(
            assertion_id="check",
            kind="policy_divert_feasible",
            event_id="ll",
        )
    ]
    payload = _make_scenario_payload(events=events, assertions=assertions)
    plan = ScenarioPlan.model_validate(payload)
    assert plan.assertions[0].kind.value == "policy_divert_feasible"
    assert plan.assertions[0].expected is None


def test_policy_divert_feasible_without_event_id_rejected() -> None:
    assertions = [
        _make_assertion(
            assertion_id="check",
            kind="policy_divert_feasible",
        )
    ]
    payload = _make_scenario_payload(assertions=assertions)
    with pytest.raises(ValidationError) as exc_info:
        ScenarioPlan.model_validate(payload)
    assert any("event_id" in e["msg"] for e in exc_info.value.errors())


def test_initial_conditions_accept_link_systems() -> None:
    initial_conditions = ScenarioInitialConditions.model_validate(
        {
            "link_systems": [
                {
                    "link_id": "mesh",
                    "kind": "mesh_network",
                    "max_range_m": 5000.0,
                }
            ]
        }
    )

    assert initial_conditions.link_systems is not None
    assert initial_conditions.link_systems[0].link_id == "mesh"


# ---------------------------------------------------------------------------
# ScenarioEvent trigger validation
# ---------------------------------------------------------------------------


def test_at_route_item_without_trigger_route_item_id_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(_make_event(trigger="at_route_item"))
    assert any("trigger_route_item_id" in e["msg"] for e in exc_info.value.errors())


def test_at_route_item_with_trigger_route_item_id_accepted() -> None:
    event = ScenarioEvent.model_validate(
        _make_event(trigger="at_route_item", trigger_route_item_id="loiter")
    )
    assert event.trigger_route_item_id == "loiter"


def test_at_elapsed_time_without_trigger_elapsed_time_s_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(_make_event(trigger="at_elapsed_time"))
    assert any("trigger_elapsed_time_s" in e["msg"] for e in exc_info.value.errors())


def test_at_elapsed_time_with_trigger_elapsed_time_s_accepted() -> None:
    event = ScenarioEvent.model_validate(
        _make_event(trigger="at_elapsed_time", trigger_elapsed_time_s=30.0)
    )
    assert event.trigger_elapsed_time_s == 30.0


def test_at_elapsed_time_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioEvent.model_validate(
            _make_event(trigger="at_elapsed_time", trigger_elapsed_time_s=-1.0)
        )


def test_event_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioEvent.model_validate(_make_event(unknown="field"))


def test_wind_change_scalar_wind_accepted() -> None:
    event = ScenarioEvent.model_validate(
        _make_event(
            kind="wind_change",
            wind_east_mps=4.0,
            wind_north_mps=-1.0,
        )
    )
    assert event.wind_east_mps == 4.0
    assert event.wind_north_mps == -1.0


def test_wind_change_layered_wind_accepted() -> None:
    event = ScenarioEvent.model_validate(
        _make_event(
            kind="wind_change",
            wind_layers=[
                {"altitude_m": 0.0, "wind_east_mps": 2.0, "wind_north_mps": 0.0}
            ],
        )
    )
    assert event.wind_layers is not None
    assert event.wind_layers[0].wind_east_mps == 2.0


def test_wind_change_requires_wind_payload() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(_make_event(kind="wind_change"))
    assert any(
        "wind_east_mps and wind_north_mps" in e["msg"] for e in exc_info.value.errors()
    )


def test_wind_change_rejects_partial_scalar_wind_payload() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(_make_event(kind="wind_change", wind_east_mps=4.0))
    assert any(
        "wind_east_mps and wind_north_mps" in e["msg"] for e in exc_info.value.errors()
    )


def test_wind_change_rejects_mixed_scalar_and_layered_payload() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(
            _make_event(
                kind="wind_change",
                wind_east_mps=4.0,
                wind_north_mps=0.0,
                wind_layers=[
                    {"altitude_m": 0.0, "wind_east_mps": 2.0, "wind_north_mps": 0.0}
                ],
            )
        )
    assert any("either wind_layers" in e["msg"] for e in exc_info.value.errors())


def test_non_wind_change_rejects_wind_payload() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(_make_event(wind_east_mps=4.0, wind_north_mps=0.0))
    assert any(
        "only valid for wind_change" in e["msg"] for e in exc_info.value.errors()
    )


# ---------------------------------------------------------------------------
# ScenarioAssertion validation
# ---------------------------------------------------------------------------


def test_field_lt_without_field_path_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioAssertion.model_validate(
            _make_assertion(kind="field_lt", expected=100.0)
        )
    assert any("field_path" in e["msg"] for e in exc_info.value.errors())


def test_field_lt_without_expected_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioAssertion.model_validate(
            _make_assertion(kind="field_lt", field_path="estimate.total_time_s")
        )
    assert any("expected" in e["msg"] for e in exc_info.value.errors())


def test_field_lt_with_all_params_accepted() -> None:
    assertion = ScenarioAssertion.model_validate(
        _make_assertion(
            kind="field_lt",
            field_path="estimate.total_time_s",
            expected=3600.0,
        )
    )
    assert assertion.field_path == "estimate.total_time_s"
    assert assertion.expected == 3600.0


def test_estimate_succeeds_without_field_path_accepted() -> None:
    assertion = ScenarioAssertion.model_validate(
        _make_assertion(kind="estimate_succeeds")
    )
    assert assertion.kind == ScenarioAssertionKind.ESTIMATE_SUCCEEDS
    assert assertion.field_path is None


def test_assertion_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioAssertion.model_validate(_make_assertion(unknown="field"))


# ---------------------------------------------------------------------------
# ScenarioInitialConditions: max_segment_length_m validation
# ---------------------------------------------------------------------------


def test_initial_conditions_max_segment_length_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioInitialConditions.model_validate({"max_segment_length_m": 0.0})


def test_initial_conditions_max_segment_length_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioInitialConditions.model_validate({"max_segment_length_m": -100.0})


# ---------------------------------------------------------------------------
# ScenarioEvent: landing_zone_unavailable validation
# ---------------------------------------------------------------------------


def test_lz_unavailable_event_with_zone_ids_accepted() -> None:
    event = ScenarioEvent.model_validate(
        _make_event(
            kind="landing_zone_unavailable",
            unavailable_zone_ids=["zone-1"],
        )
    )
    assert event.unavailable_zone_ids == ["zone-1"]


def test_lz_unavailable_event_without_zone_ids_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(_make_event(kind="landing_zone_unavailable"))
    assert any("unavailable_zone_ids" in e["msg"] for e in exc_info.value.errors())


def test_lz_unavailable_event_with_empty_zone_ids_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(
            _make_event(kind="landing_zone_unavailable", unavailable_zone_ids=[])
        )
    assert any("at least one zone id" in e["msg"] for e in exc_info.value.errors())


def test_non_lz_event_with_unavailable_zone_ids_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ScenarioEvent.model_validate(
            _make_event(kind="observe", unavailable_zone_ids=["zone-1"])
        )
    assert any("only valid for landing_zone_unavailable" in e["msg"] for e in exc_info.value.errors())


# ---------------------------------------------------------------------------
# LostLinkPolicy: divert_target_id validation
# ---------------------------------------------------------------------------


def test_rtl_policy_accepted_without_divert_target() -> None:
    policy = LostLinkPolicy.model_validate({"action": "rtl", "loiter_s": 30.0})
    assert policy.action.value == "rtl"
    assert policy.divert_target_id is None


def test_divert_policy_with_target_accepted() -> None:
    policy = LostLinkPolicy.model_validate(
        {"action": "divert", "divert_target_id": "lz-alpha"}
    )
    assert policy.divert_target_id == "lz-alpha"


def test_divert_policy_without_target_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        LostLinkPolicy.model_validate({"action": "divert"})
    assert any(
        "divert_target_id is required" in e["msg"] for e in exc_info.value.errors()
    )


def test_lost_link_policy_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        LostLinkPolicy.model_validate({"action": "rtl", "unknown_field": True})


# ---------------------------------------------------------------------------
# ID field pattern validation (event_id, assertion_id, scenario_id)
# ---------------------------------------------------------------------------


def test_event_id_with_spaces_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioEvent.model_validate(_make_event(event_id="bad id"))


def test_event_id_starting_with_dash_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioEvent.model_validate(_make_event(event_id="-bad"))


def test_event_id_with_valid_hyphens_and_digits_accepted() -> None:
    event = ScenarioEvent.model_validate(_make_event(event_id="wp1-lost-link"))
    assert event.event_id == "wp1-lost-link"


def test_assertion_id_with_spaces_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioAssertion.model_validate(_make_assertion(assertion_id="bad id"))


def test_scenario_id_with_spaces_rejected() -> None:
    with pytest.raises(ValidationError):
        ScenarioPlan.model_validate(_make_scenario_payload(scenario_id="bad scenario id"))
