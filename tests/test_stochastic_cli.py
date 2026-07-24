"""Tests for the propagate CLI command (Ticket 047)."""

import json
from pathlib import Path

from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.adapters.stochastic_envelope import STOCHASTIC_ENVELOPE_SCHEMA_VERSION

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_STOCHASTIC = REPO_ROOT / "examples/stochastic/pipeline_demo_001_stochastic.yaml"
GOLDEN_STOCHASTIC = REPO_ROOT / "tests/fixtures/golden/stochastic/stochastic.yaml"

runner = CliRunner()


def _run(args: list[str]):
    return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Happy-path CLI tests
# ---------------------------------------------------------------------------


def test_propagate_command_exits_zero() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    assert result.exit_code == int(CliExitCode.SUCCESS)


def test_propagate_command_json_schema_version() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    payload = json.loads(result.output)
    assert payload["schema_version"] == STOCHASTIC_ENVELOPE_SCHEMA_VERSION


def test_propagate_command_propagation_id() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    payload = json.loads(result.output)
    assert payload["propagation_id"] == "pipeline-demo-stochastic"


def test_propagate_command_result_has_expected_keys() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    payload = json.loads(result.output)
    r = payload["result"]
    assert "sample_count" in r
    assert "failed_sample_count" in r
    assert "timeline" in r
    assert "modeled_constraint_pass_rate" in r
    assert r["operational_feasibility_assessed"] is False
    assert "reserve_at_mission_end_wh" in r
    assert "baseline" in r
    assert "seed" in r
    assert "dt_s" in r


def test_propagate_command_timeline_is_non_empty() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    payload = json.loads(result.output)
    assert len(payload["result"]["timeline"]) >= 1


def test_propagate_command_determinism_metadata_not_deterministic() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    payload = json.loads(result.output)
    assert payload["determinism_metadata"]["deterministic"] is False
    assert payload["determinism_metadata"]["randomness_used"] is True


def test_propagate_command_provenance_has_required_inputs() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    payload = json.loads(result.output)
    assert set(payload["provenance"]["inputs"].keys()) == {
        "stochastic",
        "mission",
        "vehicle",
    }


def test_propagate_command_is_reproducible() -> None:
    r1 = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    r2 = _run(["propagate", str(EXAMPLE_STOCHASTIC)])
    assert r1.output == r2.output


def test_propagate_command_markdown_format() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC), "--format", "markdown"])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "# Diagnostic Stochastic Parameter Sweep" in result.output
    assert "Operational Feasibility Assessed:** No" in result.output


def test_propagate_command_markdown_includes_reserve_distribution() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC), "--format", "markdown"])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Conditional Reserve at Mission End" in result.output
    assert "p50" in result.output
    assert "p5" in result.output
    assert "p95" in result.output


def test_propagate_command_summary_format() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC), "--format", "summary"])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "DIAGNOSTIC" in result.output
    assert "modeled_pass" in result.output
    assert "conditional_reserve" in result.output
    assert "n=" in result.output


def test_propagate_command_output_to_file(tmp_path: Path) -> None:
    out_file = tmp_path / "report.json"
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC), "--output", str(out_file)])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert out_file.exists()
    payload = json.loads(out_file.read_text())
    assert payload["schema_version"] == STOCHASTIC_ENVELOPE_SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_propagate_command_invalid_file_exits_invalid_input(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text(
        "\n".join(
            [
                "schema_version: stochastic.v2",
                "propagation_id: x",
                "mission_file: m.yaml",
                "vehicle_file: v.yaml",
            ]
        ),
        encoding="utf-8",
    )
    result = _run(["propagate", str(bad_file)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


def test_propagate_command_schema_error_includes_details(tmp_path: Path) -> None:
    """Error output includes field-level validation details for operator diagnosis."""
    import json

    bad_file = tmp_path / "no_params.yaml"
    bad_file.write_text(
        "\n".join(
            [
                "schema_version: stochastic.v2",
                "propagation_id: x",
                "mission_file: m.yaml",
                "vehicle_file: v.yaml",
                "samples: 10",
                "seed: 1",
                # 'parameters' field missing intentionally
            ]
        ),
        encoding="utf-8",
    )
    result = _run(["propagate", str(bad_file)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    payload = json.loads(result.output)
    assert "details" in payload
    assert payload["details"].get("first_error_path") == "parameters"
    assert payload["details"].get("first_error_type") == "missing"


def test_propagate_command_missing_file_exits_nonzero() -> None:
    result = _run(["propagate", "/does/not/exist.yaml"])
    assert result.exit_code != 0


def test_propagate_infeasible_baseline_exits_invalid_input(tmp_path: Path) -> None:
    MISSION_PATH = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
    VEHICLE_PATH = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"

    # Write a vehicle without an energy model
    import yaml as yaml_mod

    with open(VEHICLE_PATH, encoding="utf-8") as f:
        vehicle_data = yaml_mod.safe_load(f)
    vehicle_data.pop("energy", None)
    no_energy_vehicle = tmp_path / "no_energy_vehicle.yaml"
    no_energy_vehicle.write_text(yaml_mod.dump(vehicle_data), encoding="utf-8")

    stochastic = tmp_path / "test.yaml"
    stochastic.write_text(
        yaml_mod.dump(
            {
                "schema_version": "stochastic.v2",
                "propagation_id": "test",
                "mission_file": str(MISSION_PATH),
                "vehicle_file": str(no_energy_vehicle),
                "seed": 1,
                "samples": 5,
                "parameters": {},
            }
        ),
        encoding="utf-8",
    )
    result = _run(["propagate", str(stochastic)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


# ---------------------------------------------------------------------------
# --validate-only
# ---------------------------------------------------------------------------


def test_propagate_validate_only_exits_zero_for_valid_inputs() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC), "--validate-only"])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "stochastic" in result.output
    assert "OK" in result.output


def test_propagate_validate_only_exits_invalid_input_for_bad_stochastic(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{bad yaml: [unclosed", encoding="utf-8")
    result = _run(["propagate", str(bad), "--validate-only"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# EKF / twin-state example
# ---------------------------------------------------------------------------

EXAMPLE_STOCHASTIC_EKF = (
    REPO_ROOT / "examples/stochastic/pipeline_demo_001_stochastic_ekf.yaml"
)


def test_propagate_controller_example_fails_closed() -> None:
    result = _run(["propagate", str(EXAMPLE_STOCHASTIC_EKF)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "does not support closed-loop controller" in result.output


def test_legacy_stochastic_v1_is_rejected(tmp_path: Path) -> None:
    payload = EXAMPLE_STOCHASTIC.read_text(encoding="utf-8").replace(
        "stochastic.v2", "stochastic.v1", 1
    )
    path = tmp_path / "legacy.yaml"
    path.write_text(payload, encoding="utf-8")

    result = _run(["propagate", str(path)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


# ---------------------------------------------------------------------------
# Golden fixture regression test
# ---------------------------------------------------------------------------


def test_propagate_canonical_json_matches_golden_fixture() -> None:
    fixture_dir = REPO_ROOT / "tests/fixtures/golden/stochastic"
    result = _run(["propagate", str(GOLDEN_STOCHASTIC)])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    expected = (fixture_dir / "envelope.json").read_text(encoding="utf-8")
    assert result.output == expected
