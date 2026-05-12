"""Tests for SITL evidence bundle contract (Ticket 040)."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from adapters.io import load_mission, load_vehicle
from adapters.scenario_envelope import build_scenario_envelope
from adapters.scenario_io import load_scenario, resolve_scenario_asset_path
from adapters.sitl_evidence import (
    SITL_EVIDENCE_SCHEMA_VERSION,
    build_sitl_evidence_bundle,
    render_sitl_evidence_json,
)
from estimator.execution.scenario import run_scenario
from schemas import (
    SitlArtifactReference,
    SitlArtifactRole,
    SitlEvidenceBundle,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden" / "scenarios" / "passed"
REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATED_SCENARIO = REPO_ROOT / "examples/scenarios/pipeline_demo_001_integrated_scenario.yaml"

runner = CliRunner()


def _build_bundle() -> SitlEvidenceBundle:
    scenario_path = FIXTURE_ROOT / "scenario.yaml"
    scenario, scenario_doc = load_scenario(scenario_path)
    mission_path = resolve_scenario_asset_path(
        scenario.mission_file,
        scenario_path=scenario_path,
    )
    vehicle_path = resolve_scenario_asset_path(
        scenario.vehicle_file,
        scenario_path=scenario_path,
    )
    mission, mission_doc = load_mission(mission_path)
    vehicle, vehicle_doc = load_vehicle(vehicle_path)
    result = run_scenario(scenario, mission, vehicle)
    envelope = build_scenario_envelope(
        result=result,
        scenario_document=scenario_doc,
        mission_document=mission_doc,
        vehicle_document=vehicle_doc,
    )
    return build_sitl_evidence_bundle(
        evidence_id="test-evidence",
        scenario_envelope=envelope,
        scenario_document=scenario_doc,
        mission_document=mission_doc,
        vehicle_document=vehicle_doc,
        vehicle=vehicle,
    )


def test_sitl_evidence_bundle_schema_validates_happy_path() -> None:
    bundle = _build_bundle()

    assert bundle.schema_version == SITL_EVIDENCE_SCHEMA_VERSION
    assert bundle.status == "contract_only"
    assert bundle.expected.scenario_report is not None
    assert bundle.expected.estimator_result is not None
    assert bundle.simulator.adapter_kind == "noop_contract"
    assert bundle.observed.telemetry == []


def test_sitl_evidence_rendering_is_deterministic() -> None:
    first = render_sitl_evidence_json(_build_bundle())
    second = render_sitl_evidence_json(_build_bundle())

    assert first == second
    assert json.loads(first)["schema_version"] == SITL_EVIDENCE_SCHEMA_VERSION


def test_sitl_artifact_reference_accepts_all_contract_roles() -> None:
    for role in SitlArtifactRole:
        ref = SitlArtifactReference(role=role, path=f"artifacts/{role.value}.json")
        assert ref.role == role


def test_sitl_evidence_bundle_rejects_unknown_fields() -> None:
    payload = _build_bundle().model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError):
        SitlEvidenceBundle.model_validate(payload)


def test_sitl_cli_emits_contract_only_evidence_bundle() -> None:
    result = runner.invoke(app, ["sitl", str(FIXTURE_ROOT / "scenario.yaml")])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.output)
    assert payload["schema_version"] == SITL_EVIDENCE_SCHEMA_VERSION
    assert payload["status"] == "contract_only"
    assert payload["expected"]["scenario_report"]["schema_version"] == "scenario-report.v2"
    assert payload["simulator"]["metadata"]["live_simulator_started"] is False


def test_sitl_cli_references_mission_vehicle_scenario_and_assets() -> None:
    result = runner.invoke(app, ["sitl", str(INTEGRATED_SCENARIO)])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.output)
    roles = {artifact["role"] for artifact in payload["inputs"]}
    assert roles >= {
        "scenario",
        "mission",
        "vehicle",
        "geofences",
        "landing_zones",
        "terrain",
        "wind_grid",
    }


def test_sitl_cli_writes_output_file(tmp_path: Path) -> None:
    output_path = tmp_path / "evidence.json"

    result = runner.invoke(
        app,
        ["sitl", str(FIXTURE_ROOT / "scenario.yaml"), "--output", str(output_path)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert result.output == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SITL_EVIDENCE_SCHEMA_VERSION


def test_sitl_cli_invalid_scenario_exits_invalid_input(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("schema_version: wrong.v1\n", encoding="utf-8")

    result = runner.invoke(app, ["sitl", str(bad_file)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
