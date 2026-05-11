"""Tests for the sample CLI command (Ticket 037)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from adapters.uncertainty_envelope import UNCERTAINTY_REPORT_SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_UNCERTAINTY = REPO_ROOT / "examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml"
EXAMPLE_SPEED_UNCERTAINTY = REPO_ROOT / "examples/uncertainty/pipeline_demo_001_speed_uncertainty.yaml"

runner = CliRunner()


def _run(args: list[str]):
    return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Happy-path CLI tests
# ---------------------------------------------------------------------------


def test_sample_command_exits_zero() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    assert result.exit_code == int(CliExitCode.SUCCESS)


def test_sample_command_json_schema_version() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    assert payload["schema_version"] == UNCERTAINTY_REPORT_SCHEMA_VERSION


def test_sample_command_uncertainty_id() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    assert payload["uncertainty_id"] == "pipeline-demo-wind-uncertainty"


def test_sample_command_result_has_expected_keys() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    r = payload["result"]
    assert "sample_count" in r
    assert "completed_sample_count" in r
    assert "failed_sample_count" in r
    assert "feasibility_rate" in r
    assert "total_time_s" in r
    assert "reserve_at_landing_wh" in r
    assert "reserve_at_landing_percent" in r
    assert "baseline" in r


def test_sample_command_stats_structure() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    stats = payload["result"]["total_time_s"]
    assert stats is not None
    for key in ("count", "mean", "std", "min", "p5", "p50", "p95", "max"):
        assert key in stats


def test_sample_command_sample_count_matches_plan() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    r = payload["result"]
    assert r["sample_count"] == 200


def test_sample_command_determinism_metadata_not_deterministic() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    assert payload["determinism_metadata"]["deterministic"] is False
    assert payload["determinism_metadata"]["randomness_used"] is True


def test_sample_command_provenance_has_required_inputs() -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    payload = json.loads(result.output)
    inputs = payload["provenance"]["inputs"]
    assert "uncertainty" in inputs
    assert "mission" in inputs
    assert "vehicle" in inputs


def test_sample_command_is_reproducible() -> None:
    r1 = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    r2 = _run(["sample", str(EXAMPLE_UNCERTAINTY)])
    assert r1.output == r2.output


def test_sample_command_speed_example() -> None:
    result = _run(["sample", str(EXAMPLE_SPEED_UNCERTAINTY)])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(result.output)
    assert payload["result"]["sample_count"] == 100


def test_sample_command_markdown_format(tmp_path: Path) -> None:
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY), "--format", "markdown"])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "# Uncertainty Report" in result.output
    assert "Seed" in result.output
    assert "Summary Statistics" in result.output
    assert "Baseline (Deterministic)" in result.output


def test_sample_command_output_to_file(tmp_path: Path) -> None:
    out_file = tmp_path / "report.json"
    result = _run(["sample", str(EXAMPLE_UNCERTAINTY), "--output", str(out_file)])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    payload = json.loads(out_file.read_text())
    assert payload["schema_version"] == UNCERTAINTY_REPORT_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_sample_command_invalid_file_exits_invalid_input(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("not_valid: true\nschema_version: wrong.v1\n", encoding="utf-8")
    result = _run(["sample", str(bad_file)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


def test_sample_command_missing_file_exits_nonzero() -> None:
    result = _run(["sample", "/nonexistent/path.yaml"])
    assert result.exit_code != 0
