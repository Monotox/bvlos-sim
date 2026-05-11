"""Tests for the scenario CLI command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from adapters.cli import app

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden" / "scenarios"
REPO_ROOT = Path(__file__).resolve().parents[1]

runner = CliRunner()


def _run(args: list[str]) -> object:
    return runner.invoke(app, args)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_passing_scenario_exits_0() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path])
    assert result.exit_code == 0


def test_failing_scenario_exits_10() -> None:
    scenario_path = str(FIXTURE_ROOT / "failed" / "scenario.yaml")
    result = _run(["scenario", scenario_path])
    assert result.exit_code == 10


def test_missing_scenario_file_exits_nonzero(tmp_path: Path) -> None:
    result = _run(["scenario", str(tmp_path / "nonexistent.yaml")])
    # typer validates `exists=True` before the command body runs
    assert result.exit_code != 0


def test_invalid_scenario_yaml_exits_11(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("{not valid scenario yaml: yes, but: wrong schema}", encoding="utf-8")
    result = _run(["scenario", str(bad_file)])
    assert result.exit_code == 11


def test_invalid_yaml_syntax_exits_11(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad.yaml"
    bad_file.write_text("{invalid yaml: [unclosed", encoding="utf-8")
    result = _run(["scenario", str(bad_file)])
    assert result.exit_code == 11


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_json_format_is_default() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path])
    payload = json.loads(result.output)
    assert payload["schema_version"] == "scenario-report.v1"


def test_v2_example_scenario_runs_from_cli() -> None:
    scenario_path = REPO_ROOT / "examples/scenarios/pipeline_demo_001_v2_scenario.yaml"

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    assert payload["estimate"]["metadata"]["estimator_version"] == "v2"


def test_integrated_example_scenario_loads_mission_assets_from_cli() -> None:
    scenario_path = REPO_ROOT / "examples/scenarios/pipeline_demo_001_integrated_scenario.yaml"

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    estimate = payload["estimate"]
    assert payload["status"] == "passed"
    assert estimate["metadata"]["estimator_version"] == "v2"
    assert estimate["metadata"]["terrain_provider_id"] == "uniform_grid"
    assert estimate["metadata"]["wind_provider_id"] == "spatiotemporal_grid"
    assert estimate["geofence"]["is_feasible"] is True
    assert estimate["landing_zone"]["is_feasible"] is True
    assert set(payload["provenance"]["inputs"]) >= {
        "scenario",
        "mission",
        "vehicle",
        "geofences",
        "landing_zones",
        "terrain",
        "wind_grid",
    }
    lost_link_event = next(
        event
        for event in payload["event_outcomes"]
        if event["event_id"] == "lost-link-at-wp1"
    )
    assert lost_link_event["fired"] is True
    assert lost_link_event["policy_outcome"]["action"] == "divert"


def test_wind_change_scenario_runs_from_cli(tmp_path: Path) -> None:
    scenario_path = tmp_path / "wind-change-scenario.yaml"
    mission_path = FIXTURE_ROOT.parent / "success" / "mission.yaml"
    vehicle_path = FIXTURE_ROOT.parent / "success" / "vehicle.yaml"
    scenario_path.write_text(
        "\n".join(
            [
                "schema_version: scenario.v1",
                "scenario_id: wind-change-cli",
                f"mission_file: {mission_path}",
                f"vehicle_file: {vehicle_path}",
                "initial_conditions:",
                "  wind_east_mps: 0.0",
                "  wind_north_mps: 0.0",
                "events:",
                "  - event_id: wind",
                "    kind: wind_change",
                "    trigger: at_mission_start",
                "    wind_east_mps: 4.0",
                "    wind_north_mps: 0.0",
                "assertions:",
                "  - assertion_id: succeeds",
                "    kind: estimate_succeeds",
                "",
            ]
        ),
        encoding="utf-8",
    )

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["event_outcomes"][0]["fired"] is True
    assert payload["event_outcomes"][0]["unsupported"] is False
    assert payload["estimate"]["metadata"]["wind_provider_id"] == "time-varying"


def test_markdown_format_produces_markdown() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--format", "markdown"])
    assert result.output.startswith("# Scenario Report")


# ---------------------------------------------------------------------------
# Output file
# ---------------------------------------------------------------------------


def test_output_written_to_file(tmp_path: Path) -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    out_file = tmp_path / "result.json"
    _run(["scenario", scenario_path, "--output", str(out_file)])
    assert out_file.exists()
    payload = json.loads(out_file.read_text())
    assert "scenario_id" in payload


def test_lz_availability_example_scenario_runs_from_cli() -> None:
    scenario_path = REPO_ROOT / "examples/scenarios/pipeline_demo_001_lz_availability_scenario.yaml"

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    estimate = payload["estimate"]
    assert estimate["failure"]["code"] == "ALL_LANDING_ZONES_UNAVAILABLE"
    assert estimate["landing_zone"]["unavailable_zone_ids"] == ["demo_landing_zone_wp1"]
    assert estimate["metadata"]["scenario_lz_unavailability_event_count"] == 1


def test_output_file_contains_assertion_results(tmp_path: Path) -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    out_file = tmp_path / "result.json"
    _run(["scenario", scenario_path, "--output", str(out_file)])
    payload = json.loads(out_file.read_text())
    assert len(payload["assertion_results"]) > 0
