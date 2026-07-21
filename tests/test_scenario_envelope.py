"""Tests for scenario result envelope construction and rendering."""

import json
from pathlib import Path

import pytest

from adapters.envelope import DeterminismMetadata, ProvenanceInput
from adapters.io import load_mission, load_vehicle
from adapters.operational_readiness import evaluate_operational_readiness
from adapters.scenario_envelope import (
    SCENARIO_REPORT_SCHEMA_VERSION,
    ScenarioProvenance,
    ScenarioResultEnvelope,
    build_scenario_envelope,
    render_scenario_envelope_json,
)
from adapters.scenario_io import load_scenario, resolve_scenario_asset_path
from adapters.scenario_markdown import render_scenario_markdown
from estimator.core.enums import WarningCode
from estimator.core.scenario import (
    CommsLinkPolicyOutcome,
    DivertRouteEstimate,
    ScenarioEventOutcome,
    ScenarioStatus,
)
from estimator.execution.scenario import run_scenario

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden" / "scenarios"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_envelope_for(scenario_name: str) -> ScenarioResultEnvelope:
    scenario_path = FIXTURE_ROOT / scenario_name / "scenario.yaml"
    scenario, scenario_doc = load_scenario(scenario_path)

    mission_path = resolve_scenario_asset_path(
        scenario.mission_file, scenario_path=scenario_path
    )
    vehicle_path = resolve_scenario_asset_path(
        scenario.vehicle_file, scenario_path=scenario_path
    )

    mission, mission_doc = load_mission(mission_path)
    vehicle, vehicle_doc = load_vehicle(vehicle_path)

    result = run_scenario(scenario, mission, vehicle)
    return build_scenario_envelope(
        result=result,
        scenario_document=scenario_doc,
        mission_document=mission_doc,
        vehicle_document=vehicle_doc,
    )


# ---------------------------------------------------------------------------
# Schema version and metadata
# ---------------------------------------------------------------------------


def test_envelope_schema_version_is_current_scenario_report_version() -> None:
    envelope = _build_envelope_for("passed")
    assert envelope.schema_version == SCENARIO_REPORT_SCHEMA_VERSION


def test_envelope_scenario_schema_version_is_set() -> None:
    envelope = _build_envelope_for("passed")
    assert envelope.scenario_schema_version == "scenario.v1"


def test_passed_scenario_has_passed_status() -> None:
    envelope = _build_envelope_for("passed")
    assert envelope.status == ScenarioStatus.PASSED


def test_failed_scenario_has_failed_status() -> None:
    envelope = _build_envelope_for("failed")
    assert envelope.status == ScenarioStatus.FAILED


# ---------------------------------------------------------------------------
# JSON canonicality
# ---------------------------------------------------------------------------


def test_json_rendering_is_deterministic() -> None:
    envelope = _build_envelope_for("passed")
    render_a = render_scenario_envelope_json(envelope)
    render_b = render_scenario_envelope_json(envelope)
    assert render_a == render_b


def test_json_output_is_valid_json() -> None:
    envelope = _build_envelope_for("passed")
    rendered = render_scenario_envelope_json(envelope)
    parsed = json.loads(rendered)
    assert isinstance(parsed, dict)


def test_json_contains_assertion_results() -> None:
    envelope = _build_envelope_for("passed")
    rendered = render_scenario_envelope_json(envelope)
    payload = json.loads(rendered)
    assert "assertion_results" in payload
    assert len(payload["assertion_results"]) > 0


def test_json_contains_timeline() -> None:
    envelope = _build_envelope_for("passed")
    rendered = render_scenario_envelope_json(envelope)
    payload = json.loads(rendered)
    assert "timeline" in payload
    assert len(payload["timeline"]) > 0


def test_json_contains_event_outcomes() -> None:
    envelope = _build_envelope_for("passed")
    rendered = render_scenario_envelope_json(envelope)
    payload = json.loads(rendered)
    assert "event_outcomes" in payload


def test_json_keys_are_sorted() -> None:
    envelope = _build_envelope_for("passed")
    rendered = render_scenario_envelope_json(envelope)
    payload = json.loads(rendered)
    top_keys = list(payload.keys())
    assert top_keys == sorted(top_keys)


# ---------------------------------------------------------------------------
# Schema strictness
# ---------------------------------------------------------------------------


def test_envelope_rejects_unknown_fields() -> None:
    from pydantic import ValidationError

    envelope = _build_envelope_for("passed")
    payload = json.loads(render_scenario_envelope_json(envelope))
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        ScenarioResultEnvelope.model_validate(payload)


def test_envelope_rejects_wrong_contract_version() -> None:
    from pydantic import ValidationError

    envelope = _build_envelope_for("passed")
    payload = json.loads(render_scenario_envelope_json(envelope))
    payload["schema_version"] = "scenario-report.v2"

    with pytest.raises(ValidationError):
        ScenarioResultEnvelope.model_validate(payload)


# ---------------------------------------------------------------------------
# Golden fixture regression tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("scenario_name", ["passed", "failed"])
def test_canonical_json_matches_golden_fixture(scenario_name: str) -> None:
    rendered = render_scenario_envelope_json(_build_envelope_for(scenario_name))
    expected = (FIXTURE_ROOT / scenario_name / "envelope.json").read_text(
        encoding="utf-8"
    )
    assert rendered == expected


@pytest.mark.parametrize("scenario_name", ["passed", "failed"])
def test_markdown_matches_golden_fixture(scenario_name: str) -> None:
    rendered = render_scenario_markdown(_build_envelope_for(scenario_name))
    expected = (FIXTURE_ROOT / scenario_name / "report.md").read_text(encoding="utf-8")
    assert rendered == expected


# ---------------------------------------------------------------------------
# scenario_markdown: event outcome branch coverage
# ---------------------------------------------------------------------------


def _minimal_envelope(
    event_outcomes: list[ScenarioEventOutcome],
) -> ScenarioResultEnvelope:
    return ScenarioResultEnvelope(
        schema_version=SCENARIO_REPORT_SCHEMA_VERSION,
        tool_version="0.0.0",
        scenario_schema_version="scenario.v1",
        scenario_id="test",
        status=ScenarioStatus.PASSED,
        determinism_metadata=DeterminismMetadata(
            deterministic=True,
            randomness_used=False,
            external_network_access_used=False,
            canonical_json=True,
            canonical_json_sort_keys=True,
        ),
        provenance=ScenarioProvenance(
            scenario_runner_api="scenario_runner.run_scenario",
            inputs={"scenario": ProvenanceInput(format="yaml", sha256="abc")},
        ),
        timeline=[],
        event_outcomes=event_outcomes,
        assertion_results=[],
        operational_readiness=evaluate_operational_readiness(None),
        estimate=None,
    )


def test_scenario_markdown_unsupported_event_shows_reason() -> None:
    outcome = ScenarioEventOutcome(
        event_id="wind-evt",
        kind="wind_change",
        fired=False,
        unsupported=True,
        unsupported_reason="wind_change events are not yet simulated",
    )
    output = render_scenario_markdown(_minimal_envelope([outcome]))
    assert "unsupported" in output
    assert "wind_change events are not yet simulated" in output


def test_scenario_markdown_not_fired_with_reason_shows_reason() -> None:
    outcome = ScenarioEventOutcome(
        event_id="route-evt",
        kind="observe",
        fired=False,
        not_fired_reason="route item 'missing-wp' not found in timeline",
    )
    output = render_scenario_markdown(_minimal_envelope([outcome]))
    assert "not fired" in output
    assert "route item 'missing-wp' not found in timeline" in output


def test_scenario_markdown_not_fired_without_reason_shows_not_fired() -> None:
    outcome = ScenarioEventOutcome(
        event_id="end-evt",
        kind="observe",
        fired=False,
    )
    output = render_scenario_markdown(_minimal_envelope([outcome]))
    assert "not fired" in output


def _policy_outcome(
    *,
    is_feasible: bool = True,
    infeasible_reason: str | None = None,
    warnings: list[WarningCode] | None = None,
) -> CommsLinkPolicyOutcome:
    divert = DivertRouteEstimate(
        target_zone_id="lz-a",
        distance_m=500.0,
        time_s=60.0,
        energy_wh=20.0,
        energy_remaining_at_action_wh=200.0,
        reserve_after_divert_wh=150.0,
        reserve_after_divert_percent=16.7,
        reserve_threshold_wh=100.0,
        is_feasible=is_feasible,
        infeasible_reason=infeasible_reason,
        warnings=warnings or [],
    )
    return CommsLinkPolicyOutcome(
        action="divert",
        loiter_s=0.0,
        link_lost_at_timeline_index=0,
        link_lost_at_elapsed_s=0.0,
        action_at_elapsed_s=0.0,
        action_at_timeline_index=0,
        action_lat=52.0,
        action_lon=4.0,
        action_altitude_amsl_m=100.0,
        divert_target_id="lz-a",
        divert_estimate=divert,
    )


def test_scenario_markdown_infeasible_divert_shows_reason() -> None:
    outcome = ScenarioEventOutcome(
        event_id="link-evt",
        kind="lost_link",
        fired=True,
        timeline_index=2,
        policy_outcome=_policy_outcome(
            is_feasible=False,
            infeasible_reason="reserve below threshold",
        ),
    )
    output = render_scenario_markdown(_minimal_envelope([outcome]))
    assert "Divert infeasible" in output
    assert "reserve below threshold" in output


def test_scenario_markdown_divert_warnings_are_shown() -> None:
    outcome = ScenarioEventOutcome(
        event_id="link-evt",
        kind="lost_link",
        fired=True,
        timeline_index=2,
        policy_outcome=_policy_outcome(
            warnings=[WarningCode.DIVERT_ENERGY_TAS_ONLY],
        ),
    )
    output = render_scenario_markdown(_minimal_envelope([outcome]))
    assert "Divert warning" in output
    assert "DIVERT_ENERGY_TAS_ONLY" in output
