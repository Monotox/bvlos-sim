"""Tests for the scenario CLI command."""

import json
from pathlib import Path

from typer.testing import CliRunner

from adapters.cli import CliExitCode, app

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "golden" / "scenarios"
REPO_ROOT = Path(__file__).resolve().parents[1]

runner = CliRunner()


def _run(args: list[str], *, engineering_only: bool = True) -> object:
    resolved = [*args]
    if engineering_only:
        resolved.append("--engineering-only")
    return runner.invoke(app, resolved)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_passing_scenario_exits_0() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path])
    assert result.exit_code == 0


def test_passing_scenario_defaults_to_fail_closed_operational_exit() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")

    result = _run(["scenario", scenario_path], engineering_only=False)

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    assert payload["operational_readiness"]["verdict"] == "no_go"


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
    bad_file.write_text(
        "{not valid scenario yaml: yes, but: wrong schema}", encoding="utf-8"
    )
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
    assert payload["schema_version"] == "scenario-report.v3"


def test_v2_example_scenario_runs_from_cli() -> None:
    scenario_path = REPO_ROOT / "examples/scenarios/pipeline_demo_001_v2_scenario.yaml"

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    assert payload["estimate"]["metadata"]["estimator_version"] == "v2"


def test_integrated_example_scenario_loads_mission_assets_from_cli() -> None:
    scenario_path = (
        REPO_ROOT / "examples/scenarios/pipeline_demo_001_integrated_scenario.yaml"
    )

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


def test_resource_link_example_scenario_runs_from_cli() -> None:
    scenario_path = (
        REPO_ROOT / "examples/scenarios/pipeline_demo_001_resource_link_scenario.yaml"
    )

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    estimate = payload["estimate"]
    assert payload["status"] == "passed"
    assert estimate["resource"]["is_feasible"] is True
    assert estimate["link"]["is_feasible"] is True


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


def test_summary_format_produces_single_line() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--format", "summary"])
    assert result.exit_code == 0
    lines = [line for line in result.output.splitlines() if line.strip()]
    assert len(lines) == 1
    assert "PASSED" in lines[0]


def test_geojson_format_produces_feature_collection() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--format", "geojson"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["type"] == "FeatureCollection"
    layers = {f["properties"]["layer"] for f in payload["features"]}
    assert "route" in layers


def test_kml_format_produces_kml_document() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--format", "kml"])
    assert result.exit_code == 0
    assert result.output.startswith("<?xml")
    assert "<kml" in result.output
    assert "<Placemark" in result.output


def test_checklist_format_produces_go_no_go_status() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(
        ["scenario", scenario_path, "--format", "checklist"],
        engineering_only=False,
    )
    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    assert "## Pre-Flight Checklist:" in result.output
    assert "Status: NO-GO" in result.output


def test_profile_format_produces_altitude_table() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--format", "profile"])
    assert result.exit_code == 0
    assert "## Route Altitude Profile" in result.output


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
    scenario_path = (
        REPO_ROOT / "examples/scenarios/pipeline_demo_001_lz_availability_scenario.yaml"
    )

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    estimate = payload["estimate"]
    assert estimate["failure"]["code"] == "ALL_LANDING_ZONES_UNAVAILABLE"
    assert estimate["landing_zone"]["unavailable_zone_ids"] == ["demo_landing_zone_wp1"]
    assert estimate["metadata"]["scenario_lz_unavailability_event_count"] == 1


def test_divert_routing_example_scenario_runs_from_cli() -> None:
    scenario_path = (
        REPO_ROOT / "examples/scenarios/pipeline_demo_001_divert_routing_scenario.yaml"
    )

    result = _run(["scenario", str(scenario_path)])

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["status"] == "passed"
    lost_link_outcome = next(
        o for o in payload["event_outcomes"] if o["event_id"] == "lost-link-at-wp1"
    )
    policy_outcome = lost_link_outcome["policy_outcome"]
    assert policy_outcome["action"] == "divert"
    assert policy_outcome["divert_target_id"] == "demo_landing_zone_wp1"
    divert_estimate = policy_outcome["divert_estimate"]
    assert divert_estimate is not None
    assert divert_estimate["target_zone_id"] == "demo_landing_zone_wp1"
    assert divert_estimate["distance_m"] >= 0.0
    assert divert_estimate["is_feasible"] is True


def test_output_file_contains_assertion_results(tmp_path: Path) -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    out_file = tmp_path / "result.json"
    _run(["scenario", scenario_path, "--output", str(out_file)])
    payload = json.loads(out_file.read_text())
    assert len(payload["assertion_results"]) > 0


# ---------------------------------------------------------------------------
# --validate-only
# ---------------------------------------------------------------------------


def test_scenario_validate_only_exits_zero_for_valid_inputs() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--validate-only"])
    assert result.exit_code == 0
    assert "scenario.yaml: OK" in result.output
    assert "mission" in result.output
    assert "vehicle" in result.output


def test_scenario_validate_only_exits_nonzero_for_bad_scenario(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("{bad yaml: [unclosed", encoding="utf-8")
    result = _run(["scenario", str(bad), "--validate-only"])
    assert result.exit_code != 0


def test_scenario_validate_only_output_is_not_json() -> None:
    scenario_path = str(FIXTURE_ROOT / "passed" / "scenario.yaml")
    result = _run(["scenario", scenario_path, "--validate-only"])
    assert result.exit_code == 0
    try:
        json.loads(result.output)
        assert False, "output should not be JSON when --validate-only is used"
    except (json.JSONDecodeError, ValueError):
        pass
