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
    SitlComparisonSummary,
    SitlEvidenceBundle,
)

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden" / "scenarios" / "passed"
REPO_ROOT = Path(__file__).resolve().parents[1]
INTEGRATED_SCENARIO = (
    REPO_ROOT / "examples/scenarios/pipeline_demo_001_integrated_scenario.yaml"
)

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


def _build_failed_assertion_bundle() -> SitlEvidenceBundle:
    payload = _build_bundle().model_dump(mode="json")
    assertion = payload["expected"]["scenario_report"]["assertion_results"][0]
    assertion["passed"] = False
    assertion["observed_value"] = "unexpected"
    payload["status"] = "completed"
    return SitlEvidenceBundle.model_validate(payload)


def _write_json_artifact(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _artifact_reference(path: Path, role: str, schema_version: str) -> dict:
    return {
        "role": role,
        "path": str(path),
        "format": "json",
        "schema_version": schema_version,
    }


def _build_drifted_bundle(tmp_path: Path) -> SitlEvidenceBundle:
    payload = _build_bundle().model_dump(mode="json")
    scenario_report = payload["expected"]["scenario_report"]
    timeline = scenario_report["timeline"]
    expected_mission_items = len(timeline) - 1
    telemetry_records = [
        {"timestamp_s": 0.0, "message_type": "HEARTBEAT", "fields": {}},
        *[
            {
                "timestamp_s": float(point["index"]),
                "message_type": "GLOBAL_POSITION_INT",
                "fields": {
                    "lat": int(point["lat"] * 10_000_000),
                    "lon": int(point["lon"] * 10_000_000),
                },
            }
            for point in timeline
            if point["index"] != 0
        ],
    ]
    telemetry_path = _write_json_artifact(
        tmp_path / "telemetry.json",
        {"schema_version": "sitl-telemetry.v1", "records": telemetry_records},
    )
    command_log_path = _write_json_artifact(
        tmp_path / "command_log.json",
        {
            "schema_version": "sitl-command-log.v1",
            "commands": [
                {
                    "timestamp_s": 0.0,
                    "command": "MISSION_COUNT",
                    "fields": {"item_count": expected_mission_items + 1},
                }
            ],
        },
    )
    simulator_log_path = _write_json_artifact(
        tmp_path / "simulator_log.json",
        {
            "schema_version": "sitl-simulator-log.v1",
            "events": [{"timestamp_s": 0.0, "event": "connected", "fields": {}}],
        },
    )
    adapter_log_path = _write_json_artifact(
        tmp_path / "adapter_log.json",
        {
            "schema_version": "sitl-adapter-log.v1",
            "events": [
                {"timestamp_s": 0.0, "event": "adapter_initialized", "fields": {}},
                {"timestamp_s": 0.0, "event": "recording_started", "fields": {}},
            ],
        },
    )
    payload["status"] = "completed"
    payload["observed"] = {
        "telemetry": [
            _artifact_reference(telemetry_path, "telemetry", "sitl-telemetry.v1")
        ],
        "command_logs": [
            _artifact_reference(
                command_log_path,
                "command_log",
                "sitl-command-log.v1",
            )
        ],
        "simulator_logs": [
            _artifact_reference(
                simulator_log_path,
                "simulator_log",
                "sitl-simulator-log.v1",
            )
        ],
        "adapter_logs": [
            _artifact_reference(adapter_log_path, "adapter_log", "sitl-adapter-log.v1")
        ],
    }
    return SitlEvidenceBundle.model_validate(payload)


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
    assert (
        payload["expected"]["scenario_report"]["schema_version"] == "scenario-report.v2"
    )
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


def test_compare_command_renders_json_from_contract_only_bundle(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_bundle()), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(evidence_path),
            "--comparison-id",
            "estimate-comparison",
        ],
    )

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    payload = json.loads(result.output)
    assert payload["schema_version"] == "sitl-comparison.v1"
    assert payload["comparison_id"] == "estimate-comparison"
    assert payload["evidence_id"] == "test-evidence"
    assert payload["summary"] in {summary.value for summary in SitlComparisonSummary}
    assert any(
        item["dimension"] == "bundle_completeness" and item["outcome"] == "skipped"
        for item in payload["items"]
    )


def test_compare_command_renders_markdown(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_bundle()), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(evidence_path),
            "--format",
            "markdown",
        ],
    )

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert "# SITL Comparison Report" in result.output
    assert "- Evidence ID: `test-evidence`" in result.output


def test_compare_command_writes_to_output_file(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    output_path = tmp_path / "comparison.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_bundle()), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        ["compare", str(evidence_path), "--output", str(output_path)],
    )

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert result.output == ""
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "sitl-comparison.v1"


def test_compare_command_exits_nonzero_when_summary_fails(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_failed_assertion_bundle()),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["compare", str(evidence_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    payload = json.loads(result.output)
    assert payload["schema_version"] == "sitl-comparison.v1"
    assert payload["summary"] == SitlComparisonSummary.FAILED.value


def test_compare_command_exits_nonzero_when_summary_drifted(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_drifted_bundle(tmp_path)),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["compare", str(evidence_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    payload = json.loads(result.output)
    assert payload["schema_version"] == "sitl-comparison.v1"
    assert payload["summary"] == SitlComparisonSummary.DRIFTED.value


def test_compare_command_unsupported_summary_exits_unsupported(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_bundle()), encoding="utf-8"
    )

    result = runner.invoke(app, ["compare", str(evidence_path)])

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    payload = json.loads(result.output)
    assert payload["schema_version"] == "sitl-comparison.v1"
    assert payload["summary"] == SitlComparisonSummary.UNSUPPORTED.value


def test_compare_command_invalid_evidence_file(tmp_path: Path) -> None:
    evidence_path = tmp_path / "bad-evidence.json"
    evidence_path.write_text("{bad json", encoding="utf-8")

    result = runner.invoke(app, ["compare", str(evidence_path)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "compare"
    assert payload["status"] == "error"


def test_compare_command_invalid_comparison_id_exits_invalid_input(
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(
        render_sitl_evidence_json(_build_bundle()), encoding="utf-8"
    )

    result = runner.invoke(
        app,
        [
            "compare",
            str(evidence_path),
            "--comparison-id",
            "bad id",
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "compare"
    assert payload["status"] == "error"
    assert "comparison_id" in payload["message"]


def test_sitl_command_now_accepts_format_flag() -> None:
    result = runner.invoke(
        app,
        ["sitl", str(FIXTURE_ROOT / "scenario.yaml"), "--format", "json"],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.output)
    assert payload["schema_version"] == SITL_EVIDENCE_SCHEMA_VERSION


def test_sitl_command_format_markdown() -> None:
    result = runner.invoke(
        app,
        ["sitl", str(FIXTURE_ROOT / "scenario.yaml"), "--format", "markdown"],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "SITL Evidence Bundle" in result.output


def test_sitl_live_requires_artifact_dir() -> None:
    result = runner.invoke(app, ["sitl", str(FIXTURE_ROOT / "scenario.yaml"), "--live"])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "sitl"
    assert payload["status"] == "error"
    assert "--artifact-dir" in payload["message"]


def test_estimate_no_longer_accepts_sitl_evidence_flag(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "estimate",
            str(FIXTURE_ROOT.parent.parent / "success" / "mission.yaml"),
            str(FIXTURE_ROOT.parent.parent / "success" / "vehicle.yaml"),
            "--sitl-evidence",
            str(tmp_path / "evidence.json"),
        ],
    )

    assert result.exit_code != int(CliExitCode.SUCCESS)
