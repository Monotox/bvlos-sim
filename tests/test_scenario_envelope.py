"""Tests for scenario result envelope construction and rendering."""

import json
from pathlib import Path

import pytest

from adapters.io import load_mission, load_vehicle
from adapters.scenario_envelope import (
    SCENARIO_REPORT_SCHEMA_VERSION,
    ScenarioResultEnvelope,
    build_scenario_envelope,
    render_scenario_envelope_json,
)
from adapters.scenario_io import load_scenario, resolve_scenario_asset_path
from adapters.scenario_markdown import render_scenario_markdown
from estimator.core.scenario import ScenarioStatus
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
