"""Backend-facing CLI exit-code contract (Ticket 103).

These tests pin the part of the contract that is easy to regress: an unexpected
exception inside ``validate``, ``sora``, or ``calibrate`` must surface as the
documented ``INTERNAL_ERROR`` (exit ``13``) rather than escaping as a bare
traceback (shell status ``1``). They also assert the success exit is unchanged
by the catch-all. See ``docs/cli.md`` for the full per-command table.
"""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

# Import the CLI app first so adapters.cli finishes registering every command
# before we grab the individual command modules (avoids a circular import).
from adapters.cli import CliExitCode, app
import adapters.commands.calibrate as calibrate_cmd
import adapters.commands.sora as sora_cmd
import adapters.commands.validate as validate_cmd

runner = CliRunner()

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

_MISSION = EXAMPLES / "missions" / "pipeline_demo_001.yaml"
_VEHICLE = EXAMPLES / "vehicles" / "quadplane_v1.yaml"
_SORA_MISSION = EXAMPLES / "missions" / "pipeline_demo_001_ground_risk.yaml"
_SORA_VEHICLE = EXAMPLES / "vehicles" / "quadplane_v1_ground_risk.yaml"
_TRACE = EXAMPLES / "flight_logs" / "pipeline_demo_001_trace.json"

INTERNAL_ERROR = int(CliExitCode.INTERNAL_ERROR)
SUCCESS = int(CliExitCode.SUCCESS)
INFEASIBLE = int(CliExitCode.INFEASIBLE)


def _boom(*_args: object, **_kwargs: object) -> None:
    raise RuntimeError("unexpected failure")


# --- validate -------------------------------------------------------------


def test_validate_out_of_threshold_exit_code(tmp_path: Path) -> None:
    trace = json.loads(_TRACE.read_text(encoding="utf-8"))
    for record in trace["records"]:
        record["timestamp_s"] = round(record["timestamp_s"] * 2.0, 1)
    slow_trace = tmp_path / "slow_trace.json"
    slow_trace.write_text(json.dumps(trace), encoding="utf-8")

    result = runner.invoke(
        app, ["validate", str(_MISSION), str(_VEHICLE), str(slow_trace)]
    )
    assert result.exit_code == INFEASIBLE
    assert "Acceptance: **FAIL**" in result.stdout


def test_validate_rejects_mismatched_trace_hash(tmp_path: Path) -> None:
    payload = json.loads(_TRACE.read_text(encoding="utf-8"))
    payload["mission_ref"]["mission_sha256"] = "0" * 64
    trace = tmp_path / "trace.json"
    trace.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["validate", str(_MISSION), str(_VEHICLE), str(trace)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "does not match" in result.stdout


def test_validate_internal_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(validate_cmd, "build_validation_report", _boom)
    result = runner.invoke(app, ["validate", str(_MISSION), str(_VEHICLE), str(_TRACE)])
    assert result.exit_code == INTERNAL_ERROR


# --- sora -----------------------------------------------------------------


def test_sora_success_exit_code() -> None:
    result = runner.invoke(app, ["sora", str(_SORA_MISSION), str(_SORA_VEHICLE)])
    assert result.exit_code == SUCCESS


def test_sora_internal_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sora_cmd, "build_sora_assessment", _boom)
    result = runner.invoke(app, ["sora", str(_SORA_MISSION), str(_SORA_VEHICLE)])
    assert result.exit_code == INTERNAL_ERROR


# --- convert --------------------------------------------------------------


def _write_survey_plan(tmp_path: Path) -> Path:
    plan = {
        "fileType": "Plan",
        "mission": {
            "plannedHomePosition": [52.0, 4.0, 12.0],
            "items": [
                {"type": "ComplexItem", "complexItemType": "survey", "command": 16},
                {
                    "type": "SimpleItem",
                    "command": 16,
                    "frame": 3,
                    "coordinate": [52.001, 4.002, 120.0],
                    "params": [0, 0, 0, None, 52.001, 4.002, 120.0],
                },
            ],
        },
    }
    plan_path = tmp_path / "survey.plan"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")
    return plan_path


def test_convert_lossy_plan_exits_unsupported(tmp_path: Path) -> None:
    plan_path = _write_survey_plan(tmp_path)
    result = runner.invoke(
        app, ["convert", str(plan_path), "--vehicle-profile", "quadplane_v1"]
    )
    assert result.exit_code == int(CliExitCode.UNSUPPORTED)


def test_convert_lossy_plan_with_allow_lossy_exits_success(tmp_path: Path) -> None:
    plan_path = _write_survey_plan(tmp_path)
    result = runner.invoke(
        app,
        [
            "convert",
            str(plan_path),
            "--vehicle-profile",
            "quadplane_v1",
            "--allow-lossy",
        ],
    )
    assert result.exit_code == SUCCESS


# --- calibrate ------------------------------------------------------------


def test_calibrate_success_exit_code() -> None:
    result = runner.invoke(app, ["calibrate", str(_VEHICLE), str(_TRACE)])
    assert result.exit_code == SUCCESS


def test_calibrate_internal_error_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(calibrate_cmd, "fit_calibration_profile", _boom)
    result = runner.invoke(app, ["calibrate", str(_VEHICLE), str(_TRACE)])
    assert result.exit_code == INTERNAL_ERROR
