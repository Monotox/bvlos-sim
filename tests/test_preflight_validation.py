"""Tests for the machine-readable preflight validation envelope (Ticket 107)."""

import json
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.schemas.preflight_validation import (
    PREFLIGHT_VALIDATION_SCHEMA_VERSION,
    FileCheck,
    PreflightError,
    PreflightValidationReport,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
VEHICLE = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"
SCENARIO = REPO_ROOT / "examples/scenarios/pipeline_demo_001_scenario.yaml"
TRACE = REPO_ROOT / "examples/flight_logs/pipeline_demo_001_trace.json"
REAL_GEOFENCE = REPO_ROOT / "data/geofences/demo.geojson"

runner = CliRunner()


def _json(result) -> dict:
    return json.loads(result.stdout)


def _file_by_role(payload: dict, role: str) -> dict:
    return next(f for f in payload["files"] if f["role"] == role)


def _mission_with_geofence(tmp_path: Path, geofence_value: str) -> Path:
    """Copy the example mission but reference only the given geofence file."""
    mission = yaml.safe_load(MISSION.read_text(encoding="utf-8"))
    mission["assets"] = {"geofences_file": geofence_value}
    path = tmp_path / "mission.yaml"
    path.write_text(yaml.safe_dump(mission), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_schema_round_trip() -> None:
    report = PreflightValidationReport(
        schema_version=PREFLIGHT_VALIDATION_SCHEMA_VERSION,
        command="estimate",
        ok=False,
        files=[
            FileCheck(path="m.yaml", role="mission", ok=True),
            FileCheck(
                path="g.geojson",
                role="geofence",
                ok=False,
                stage="asset-load",
                error=PreflightError(code="ASSET_FILE_MISSING", message="gone"),
            ),
        ],
    )
    restored = PreflightValidationReport.model_validate(report.model_dump(mode="json"))
    assert restored == report
    assert restored.generated_at is None


def test_schema_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        PreflightValidationReport(
            schema_version=PREFLIGHT_VALIDATION_SCHEMA_VERSION,
            command="estimate",
            ok=True,
            files=[],
            unexpected="x",
        )


def test_schema_version_literal_pinned() -> None:
    assert PREFLIGHT_VALIDATION_SCHEMA_VERSION == "preflight-validation.v1"
    with pytest.raises(ValidationError):
        PreflightValidationReport(
            schema_version="preflight-validation.v2",
            command="estimate",
            ok=True,
            files=[],
        )


# ---------------------------------------------------------------------------
# estimate
# ---------------------------------------------------------------------------


def test_estimate_valid_json_envelope() -> None:
    result = runner.invoke(
        app,
        [
            "estimate",
            str(MISSION),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = _json(result)
    assert payload["schema_version"] == PREFLIGHT_VALIDATION_SCHEMA_VERSION
    assert payload["command"] == "estimate"
    assert payload["ok"] is True
    assert payload["generated_at"] is None
    assert all(f["ok"] for f in payload["files"])
    assert {"mission", "vehicle"} <= {f["role"] for f in payload["files"]}


def test_estimate_bad_schema_json_envelope(tmp_path: Path) -> None:
    bad = tmp_path / "bad_mission.yaml"
    bad.write_text("schema_version: mission.v6\nmission_id: x\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "estimate",
            str(bad),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    assert payload["ok"] is False
    mission = _file_by_role(payload, "mission")
    assert mission["ok"] is False
    assert mission["stage"] == "schema"
    assert mission["error"]["code"] == "SCHEMA_VALIDATION_FAILED"


def test_estimate_missing_asset_json_envelope(tmp_path: Path) -> None:
    mission = _mission_with_geofence(tmp_path, "missing.geojson")
    result = runner.invoke(
        app,
        [
            "estimate",
            str(mission),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    assert payload["ok"] is False
    geofence = _file_by_role(payload, "geofence")
    assert geofence["ok"] is False
    assert geofence["stage"] == "asset-load"
    assert geofence["error"]["code"] == "ASSET_FILE_MISSING"


def test_estimate_malformed_geojson_json_envelope(tmp_path: Path) -> None:
    bad_geojson = tmp_path / "bad.geojson"
    bad_geojson.write_text("{ this is not valid json ", encoding="utf-8")
    mission = _mission_with_geofence(tmp_path, "bad.geojson")
    result = runner.invoke(
        app,
        [
            "estimate",
            str(mission),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    geofence = _file_by_role(payload, "geofence")
    assert geofence["ok"] is False
    assert geofence["stage"] == "asset-load"
    # A malformed asset is distinct from a missing one.
    assert geofence["error"]["code"] == "GEOJSON_PARSE_FAILED"
    assert geofence["error"]["code"] != "ASSET_FILE_MISSING"


def test_estimate_plain_text_default_unchanged() -> None:
    result = runner.invoke(
        app, ["estimate", str(MISSION), str(VEHICLE), "--validate-only"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "mission: pipeline_demo_001.yaml: OK" in result.stdout
    assert "vehicle: quadplane_v1.yaml: OK" in result.stdout
    # Default output is plain text, not the JSON envelope.
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


# ---------------------------------------------------------------------------
# scenario
# ---------------------------------------------------------------------------


def test_scenario_valid_json_envelope() -> None:
    result = runner.invoke(
        app, ["scenario", str(SCENARIO), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = _json(result)
    assert payload["command"] == "scenario"
    assert payload["ok"] is True
    assert {"scenario", "mission", "vehicle"} <= {f["role"] for f in payload["files"]}


def test_scenario_bad_schema_json_envelope(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{bad yaml: [unclosed", encoding="utf-8")
    result = runner.invoke(
        app, ["scenario", str(bad), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    assert payload["ok"] is False
    scenario = _file_by_role(payload, "scenario")
    assert scenario["ok"] is False


# ---------------------------------------------------------------------------
# batch
# ---------------------------------------------------------------------------


def _batch_manifest(tmp_path: Path, mission: Path) -> Path:
    manifest = tmp_path / "batch.yaml"
    manifest.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: run_a",
                f"    mission: {mission}",
                f"    vehicle: {VEHICLE}",
            ]
        ),
        encoding="utf-8",
    )
    return manifest


def test_batch_valid_json_envelope(tmp_path: Path) -> None:
    manifest = _batch_manifest(tmp_path, MISSION)
    result = runner.invoke(
        app, ["batch", str(manifest), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = _json(result)
    assert payload["command"] == "batch"
    assert payload["ok"] is True
    assert _file_by_role(payload, "batch")["ok"] is True
    assert {"mission", "vehicle"} <= {f["role"] for f in payload["files"]}


def test_batch_missing_asset_json_envelope(tmp_path: Path) -> None:
    mission = _mission_with_geofence(tmp_path, "missing.geojson")
    manifest = _batch_manifest(tmp_path, mission)
    result = runner.invoke(
        app, ["batch", str(manifest), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    geofence = _file_by_role(payload, "geofence")
    assert geofence["ok"] is False
    assert geofence["stage"] == "asset-load"


# ---------------------------------------------------------------------------
# export (the chosen one of sora/convert/export)
# ---------------------------------------------------------------------------


def test_export_valid_json_envelope() -> None:
    result = runner.invoke(
        app, ["export", str(MISSION), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = _json(result)
    assert payload["command"] == "export"
    assert payload["ok"] is True
    assert _file_by_role(payload, "mission")["ok"] is True


def test_export_bad_schema_json_envelope(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("mission_id: 1\n", encoding="utf-8")
    result = runner.invoke(
        app, ["export", str(bad), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    assert payload["ok"] is False
    assert _file_by_role(payload, "mission")["stage"] == "schema"


# ---------------------------------------------------------------------------
# calibrate / size-battery / compare — one valid + one invalid, text and json
# ---------------------------------------------------------------------------


def test_calibrate_validate_only_text_and_json() -> None:
    text = runner.invoke(
        app, ["calibrate", str(VEHICLE), str(TRACE), "--validate-only"]
    )
    assert text.exit_code == int(CliExitCode.SUCCESS)
    assert "vehicle: quadplane_v1.yaml: OK" in text.stdout

    js = runner.invoke(
        app,
        [
            "calibrate",
            str(VEHICLE),
            str(TRACE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert js.exit_code == int(CliExitCode.SUCCESS)
    payload = _json(js)
    assert payload["command"] == "calibrate"
    assert {"vehicle", "flight-trace"} == {f["role"] for f in payload["files"]}


def test_calibrate_invalid_trace(tmp_path: Path) -> None:
    bad_trace = tmp_path / "bad_trace.json"
    bad_trace.write_text("{ not valid ", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "calibrate",
            str(VEHICLE),
            str(bad_trace),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    assert payload["ok"] is False
    assert _file_by_role(payload, "flight-trace")["ok"] is False


def test_size_battery_validate_only_text_and_json() -> None:
    text = runner.invoke(
        app, ["size-battery", str(MISSION), str(VEHICLE), "--validate-only"]
    )
    assert text.exit_code == int(CliExitCode.SUCCESS)
    assert "mission: pipeline_demo_001.yaml: OK" in text.stdout

    js = runner.invoke(
        app,
        [
            "size-battery",
            str(MISSION),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert js.exit_code == int(CliExitCode.SUCCESS)
    assert _json(js)["command"] == "size-battery"


def test_size_battery_invalid_mission(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("mission_id: 1\n", encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "size-battery",
            str(bad),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert _json(result)["ok"] is False


def _evidence_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "evidence.json"
    result = runner.invoke(
        app, ["sitl", str(SCENARIO), "--format", "json", "--output", str(bundle)]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    return bundle


def test_compare_validate_only_text_and_json(tmp_path: Path) -> None:
    bundle = _evidence_bundle(tmp_path)
    text = runner.invoke(app, ["compare", str(bundle), "--validate-only"])
    assert text.exit_code == int(CliExitCode.SUCCESS)
    assert "evidence: evidence.json: OK" in text.stdout

    js = runner.invoke(
        app, ["compare", str(bundle), "--validate-only", "--validate-format", "json"]
    )
    assert js.exit_code == int(CliExitCode.SUCCESS)
    payload = _json(js)
    assert payload["command"] == "compare"
    assert _file_by_role(payload, "evidence")["ok"] is True


def test_compare_invalid_bundle(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not valid ", encoding="utf-8")
    result = runner.invoke(
        app, ["compare", str(bad), "--validate-only", "--validate-format", "json"]
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = _json(result)
    assert payload["ok"] is False
    assert _file_by_role(payload, "evidence")["stage"] == "asset-load"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_envelope_is_deterministic() -> None:
    args = [
        "estimate",
        str(MISSION),
        str(VEHICLE),
        "--validate-only",
        "--validate-format",
        "json",
    ]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.stdout == second.stdout


# ---------------------------------------------------------------------------
# Absent safety blocks
# ---------------------------------------------------------------------------


def test_validate_only_notes_absent_safety_blocks(tmp_path: Path) -> None:
    minimal = tmp_path / "minimal.yaml"
    minimal.write_text(
        "\n".join(
            [
                "schema_version: mission.v7",
                "mission_id: minimal_001",
                "vehicle_profile: quadplane_v1",
                "planned_home: {lat: 52.0, lon: 4.0, altitude_amsl_m: 12.0}",
                "defaults: {cruise_speed_mps: 18.0, altitude_reference: relative_home}",
                "route:",
                "  - {id: takeoff, action: vtol_takeoff, altitude_m: 80.0}",
                "  - {id: rtl, action: rtl}",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["estimate", str(minimal), str(VEHICLE), "--validate-only"]
    )
    assert result.exit_code == 0
    assert "no constraints/assets/policy block declared" in result.stdout

    as_json = runner.invoke(
        app,
        [
            "estimate",
            str(minimal),
            str(VEHICLE),
            "--validate-only",
            "--validate-format",
            "json",
        ],
    )
    payload = _json(as_json)
    assert _file_by_role(payload, "mission")["notes"] == [
        "no constraints/assets/policy block declared"
    ]


def test_validate_only_full_mission_has_no_notes() -> None:
    result = runner.invoke(
        app,
        ["estimate", str(MISSION), str(VEHICLE), "--validate-only", "--validate-format", "json"],
    )
    payload = _json(result)
    assert "notes" not in _file_by_role(payload, "mission")
