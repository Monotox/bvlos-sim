"""Tests for the `verify` evidence checksum re-verification command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, VerifyExitCode, app

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden"

runner = CliRunner()


def _write_fixture_tree(tmp_path: Path) -> Path:
    """Copy the golden passed scenario and its inputs into a flat tmp tree."""
    scenario_text = (
        (FIXTURE_ROOT / "scenarios" / "passed" / "scenario.yaml")
        .read_text(encoding="utf-8")
        .replace("../../success/mission.yaml", "mission.yaml")
        .replace("../../success/vehicle.yaml", "vehicle.yaml")
    )
    scenario_path = tmp_path / "scenario.yaml"
    scenario_path.write_text(scenario_text, encoding="utf-8")
    for name in ("mission.yaml", "vehicle.yaml"):
        (tmp_path / name).write_bytes((FIXTURE_ROOT / "success" / name).read_bytes())
    return scenario_path


def _write_evidence_bundle(tmp_path: Path) -> Path:
    """Produce a contract-only sitl-evidence.v1 bundle referencing tmp inputs."""
    scenario_path = _write_fixture_tree(tmp_path)
    bundle_path = tmp_path / "out" / "evidence.json"
    bundle_path.parent.mkdir()
    result = runner.invoke(
        app, ["sitl", str(scenario_path), "--output", str(bundle_path)]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    return bundle_path


def test_verify_passes_on_untampered_bundle(tmp_path: Path) -> None:
    bundle_path = _write_evidence_bundle(tmp_path)

    result = runner.invoke(app, ["verify", str(bundle_path)])

    assert result.exit_code == int(VerifyExitCode.PASSED)
    for role in ("scenario", "mission", "vehicle"):
        assert f"OK       {role}" in result.output
    assert "verify: PASS" in result.output


def test_verify_skips_references_without_recorded_checksum(tmp_path: Path) -> None:
    bundle_path = _write_evidence_bundle(tmp_path)

    result = runner.invoke(app, ["verify", str(bundle_path)])

    # The embedded scenario-report reference carries no sha256; it must be
    # reported but must not fail the verdict.
    assert result.exit_code == int(VerifyExitCode.PASSED)
    assert "SKIPPED" in result.output
    assert "no recorded sha256" in result.output


def test_verify_detects_tampered_artifact_byte(tmp_path: Path) -> None:
    bundle_path = _write_evidence_bundle(tmp_path)
    mission_path = tmp_path / "mission.yaml"
    original = bytearray(mission_path.read_bytes())
    original[-1] ^= 0x01
    mission_path.write_bytes(bytes(original))

    result = runner.invoke(app, ["verify", str(bundle_path)])

    assert result.exit_code == int(VerifyExitCode.FAILED)
    assert "MISMATCH mission" in result.output
    assert "recorded" in result.output
    assert "computed" in result.output
    assert "verify: FAIL" in result.output


def test_verify_reports_missing_artifact_file(tmp_path: Path) -> None:
    bundle_path = _write_evidence_bundle(tmp_path)
    (tmp_path / "vehicle.yaml").unlink()

    result = runner.invoke(app, ["verify", str(bundle_path)])

    assert result.exit_code == int(VerifyExitCode.FAILED)
    assert "MISSING  vehicle" in result.output
    assert "verify: FAIL" in result.output


def test_verify_resolves_relative_artifact_paths_from_bundle_directory(
    tmp_path: Path,
) -> None:
    bundle_path = _write_evidence_bundle(tmp_path)
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))

    # The bundle written with --output records portable relative input paths;
    # verify must resolve them against the bundle file's directory, not cwd.
    assert all(
        not Path(reference["path"]).is_absolute() for reference in payload["inputs"]
    )
    result = runner.invoke(app, ["verify", str(bundle_path)])
    assert result.exit_code == int(VerifyExitCode.PASSED)


def test_verify_invalid_bundle_exits_invalid_input(tmp_path: Path) -> None:
    bad_bundle = tmp_path / "bad-evidence.json"
    bad_bundle.write_text("{bad json", encoding="utf-8")

    result = runner.invoke(app, ["verify", str(bad_bundle)])

    assert result.exit_code == int(VerifyExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "verify"
    assert payload["status"] == "error"


def test_verify_unreadable_bundle_path_exits_invalid_input(tmp_path: Path) -> None:
    result = runner.invoke(app, ["verify", str(tmp_path / "does-not-exist.json")])

    assert result.exit_code == int(VerifyExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "verify"
    assert payload["status"] == "error"


def test_verify_schema_invalid_bundle_exits_invalid_input(tmp_path: Path) -> None:
    bundle_path = _write_evidence_bundle(tmp_path)
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    payload["schema_version"] = "sitl-evidence.v999"
    bundle_path.write_text(json.dumps(payload), encoding="utf-8")

    result = runner.invoke(app, ["verify", str(bundle_path)])

    assert result.exit_code == int(VerifyExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert payload["command"] == "verify"
    assert payload["status"] == "error"
