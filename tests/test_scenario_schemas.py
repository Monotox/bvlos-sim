"""Tests for scenario.v1 schema validation."""

import pytest
from pydantic import ValidationError

from schemas.scenario import (
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
    with pytest.raises(ValidationError, match="event ids must be unique"):
        ScenarioPlan.model_validate(payload)


def test_duplicate_assertion_ids_rejected() -> None:
    assertions = [
        _make_assertion(assertion_id="dup"),
        _make_assertion(assertion_id="dup"),
    ]
    payload = _make_scenario_payload(assertions=assertions)
    with pytest.raises(ValidationError, match="assertion ids must be unique"):
        ScenarioPlan.model_validate(payload)


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


# ---------------------------------------------------------------------------
# ScenarioEvent trigger validation
# ---------------------------------------------------------------------------


def test_at_route_item_without_trigger_route_item_id_rejected() -> None:
    with pytest.raises(ValidationError, match="trigger_route_item_id"):
        ScenarioEvent.model_validate(
            _make_event(trigger="at_route_item")
        )


def test_at_route_item_with_trigger_route_item_id_accepted() -> None:
    event = ScenarioEvent.model_validate(
        _make_event(trigger="at_route_item", trigger_route_item_id="loiter")
    )
    assert event.trigger_route_item_id == "loiter"


def test_at_elapsed_time_without_trigger_elapsed_time_s_rejected() -> None:
    with pytest.raises(ValidationError, match="trigger_elapsed_time_s"):
        ScenarioEvent.model_validate(
            _make_event(trigger="at_elapsed_time")
        )


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
    with pytest.raises(ValidationError, match="wind_east_mps and wind_north_mps"):
        ScenarioEvent.model_validate(_make_event(kind="wind_change"))


def test_wind_change_rejects_partial_scalar_wind_payload() -> None:
    with pytest.raises(ValidationError, match="wind_east_mps and wind_north_mps"):
        ScenarioEvent.model_validate(
            _make_event(kind="wind_change", wind_east_mps=4.0)
        )


def test_wind_change_rejects_mixed_scalar_and_layered_payload() -> None:
    with pytest.raises(ValidationError, match="either wind_layers"):
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


def test_non_wind_change_rejects_wind_payload() -> None:
    with pytest.raises(ValidationError, match="only valid for wind_change"):
        ScenarioEvent.model_validate(_make_event(wind_east_mps=4.0, wind_north_mps=0.0))


# ---------------------------------------------------------------------------
# ScenarioAssertion validation
# ---------------------------------------------------------------------------


def test_field_lt_without_field_path_rejected() -> None:
    with pytest.raises(ValidationError, match="field_path"):
        ScenarioAssertion.model_validate(
            _make_assertion(kind="field_lt", expected=100.0)
        )


def test_field_lt_without_expected_rejected() -> None:
    with pytest.raises(ValidationError, match="expected"):
        ScenarioAssertion.model_validate(
            _make_assertion(kind="field_lt", field_path="estimate.total_time_s")
        )


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
    assertion = ScenarioAssertion.model_validate(_make_assertion(kind="estimate_succeeds"))
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
