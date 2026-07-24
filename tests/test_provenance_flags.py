"""Tests for --operator-id/--generated-at provenance flags and --no-clobber."""

import json
from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, app

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden"
MISSION = FIXTURE_ROOT / "success" / "mission.yaml"
VEHICLE = FIXTURE_ROOT / "success" / "vehicle.yaml"
SCENARIO = FIXTURE_ROOT / "scenarios" / "passed" / "scenario.yaml"

runner = CliRunner()


# --- provenance identity flags --------------------------------------------


def test_estimate_records_operator_id_and_generated_at() -> None:
    result = runner.invoke(
        app,
        [
            "estimate",
            str(MISSION),
            str(VEHICLE),
            "--operator-id",
            "ops-anna",
            "--generated-at",
            "2026-07-23T10:00:00Z",
        ],
    )

    metadata = json.loads(result.output)["result"]["metadata"]
    assert metadata["operator_id"] == "ops-anna"
    assert metadata["generated_at"] == "2026-07-23T10:00:00Z"


def test_estimate_metadata_absent_by_default_and_byte_identical() -> None:
    first = runner.invoke(app, ["estimate", str(MISSION), str(VEHICLE)])
    second = runner.invoke(app, ["estimate", str(MISSION), str(VEHICLE)])

    metadata = json.loads(first.output)["result"]["metadata"]
    assert "operator_id" not in metadata
    assert "generated_at" not in metadata
    assert first.output == second.output


def test_estimate_generated_at_now_resolves_to_utc_iso8601() -> None:
    result = runner.invoke(
        app,
        ["estimate", str(MISSION), str(VEHICLE), "--generated-at", "now"],
    )

    generated_at = json.loads(result.output)["result"]["metadata"]["generated_at"]
    assert generated_at.endswith("Z")
    parsed = datetime.fromisoformat(generated_at)
    assert parsed.tzinfo is not None


def test_estimate_rejects_invalid_generated_at() -> None:
    result = runner.invoke(
        app,
        ["estimate", str(MISSION), str(VEHICLE), "--generated-at", "yesterday"],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


def test_scenario_records_provenance_metadata() -> None:
    result = runner.invoke(
        app,
        [
            "scenario",
            str(SCENARIO),
            "--operator-id",
            "ops-anna",
            "--generated-at",
            "2026-07-23T10:00:00Z",
        ],
    )

    metadata = json.loads(result.output)["estimate"]["metadata"]
    assert metadata["operator_id"] == "ops-anna"
    assert metadata["generated_at"] == "2026-07-23T10:00:00Z"


def test_scenario_metadata_absent_by_default() -> None:
    result = runner.invoke(app, ["scenario", str(SCENARIO)])

    metadata = json.loads(result.output)["estimate"]["metadata"]
    assert "operator_id" not in metadata
    assert "generated_at" not in metadata


def test_sitl_records_provenance_metadata() -> None:
    result = runner.invoke(
        app,
        [
            "sitl",
            str(SCENARIO),
            "--operator-id",
            "ops-anna",
            "--generated-at",
            "2026-07-23T10:00:00Z",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    metadata = json.loads(result.output)["metadata"]
    assert metadata["operator_id"] == "ops-anna"
    assert metadata["generated_at"] == "2026-07-23T10:00:00Z"


def test_sitl_metadata_absent_by_default() -> None:
    result = runner.invoke(app, ["sitl", str(SCENARIO)])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    metadata = json.loads(result.output)["metadata"]
    assert "operator_id" not in metadata
    assert "generated_at" not in metadata


def test_sitl_rejects_invalid_generated_at() -> None:
    result = runner.invoke(
        app,
        ["sitl", str(SCENARIO), "--generated-at", "not-a-timestamp"],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "sitl"
    assert payload["status"] == "error"


# --- --no-clobber ----------------------------------------------------------


def test_estimate_no_clobber_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "envelope.json"
    output.write_text("sentinel", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "estimate",
            str(MISSION),
            str(VEHICLE),
            "--output",
            str(output),
            "--no-clobber",
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert output.read_text(encoding="utf-8") == "sentinel"
    payload = json.loads(result.output)
    assert payload["command"] == "estimate"
    assert payload["status"] == "error"
    assert "--no-clobber" in payload["message"]


def test_estimate_no_clobber_allows_new_output_file(tmp_path: Path) -> None:
    output = tmp_path / "envelope.json"

    result = runner.invoke(
        app,
        [
            "estimate",
            str(MISSION),
            str(VEHICLE),
            "--engineering-only",
            "--output",
            str(output),
            "--no-clobber",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "estimator-envelope.v10"


def test_estimate_overwrites_existing_output_without_no_clobber(
    tmp_path: Path,
) -> None:
    output = tmp_path / "envelope.json"
    output.write_text("sentinel", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "estimate",
            str(MISSION),
            str(VEHICLE),
            "--engineering-only",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert output.read_text(encoding="utf-8") != "sentinel"


def test_sitl_no_clobber_refuses_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "evidence.json"
    output.write_text("sentinel", encoding="utf-8")

    result = runner.invoke(
        app,
        ["sitl", str(SCENARIO), "--output", str(output), "--no-clobber"],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert output.read_text(encoding="utf-8") == "sentinel"
    payload = json.loads(result.output)
    assert payload["command"] == "sitl"
    assert "--no-clobber" in payload["message"]
