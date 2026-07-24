from pathlib import Path
from dataclasses import replace

import pytest

from adapters.batch_io import load_batch_manifest
from adapters.batch_support import (
    BatchRunResult,
    format_flight_time,
    format_reserve_margin,
    render_batch_csv,
    render_batch_table,
    run_batch_manifest,
)
from adapters.cli import CliExitCode, app
from adapters.cli_batch_support import _batch_output_extension, write_batch_outputs
from adapters.envelope import OutputFormat
from adapters.io import InputLoadError
from schemas.batch import BatchManifest, BatchRun
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
_runner = CliRunner()


def _manifest(*runs: BatchRun) -> BatchManifest:
    return BatchManifest(format_version="batch.v1", runs=list(runs))


def _run(run_id: str, mission: Path, vehicle: Path) -> BatchRun:
    return BatchRun(id=run_id, mission=mission, vehicle=vehicle)


def test_batch_feasible_run_reports_positive_reserve() -> None:
    results = run_batch_manifest(
        _manifest(
            _run(
                "pipeline_demo",
                REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            )
        ),
        engineering_only=True,
    )

    assert len(results) == 1
    assert results[0].status == "FEASIBLE"
    assert results[0].reserve_margin_percent is not None
    assert results[0].reserve_margin_percent > 0


def test_batch_infeasible_run_reports_negative_reserve() -> None:
    results = run_batch_manifest(
        _manifest(
            _run(
                "alpine_infeasible",
                REPO_ROOT / "examples/real_world/alpine_infeasible.yaml",
                REPO_ROOT / "examples/real_world/quadplane_small_battery.yaml",
            )
        )
    )

    assert len(results) == 1
    assert results[0].status == "INFEASIBLE"
    assert results[0].reserve_margin_percent is not None
    assert results[0].reserve_margin_percent < 0


def test_batch_defaults_to_fail_closed_operational_status() -> None:
    results = run_batch_manifest(
        _manifest(
            _run(
                "pipeline_demo",
                REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            )
        )
    )

    assert results[0].status == "INFEASIBLE"


def test_batch_input_error_marks_run_error_and_continues() -> None:
    results = run_batch_manifest(
        _manifest(
            _run(
                "missing_mission",
                REPO_ROOT / "examples/missions/does_not_exist.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            ),
            _run(
                "pipeline_demo",
                REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            ),
        ),
        engineering_only=True,
    )

    assert [result.status for result in results] == ["ERROR", "FEASIBLE"]
    assert results[0].error_message is not None
    assert results[1].reserve_margin_percent is not None
    assert results[1].reserve_margin_percent > 0


def test_invalid_batch_format_version_raises_input_load_error(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    manifest_path.write_text(
        "format_version: batch.v2\nruns:\n  - id: run\n    mission: m.yaml\n    vehicle: v.yaml\n",
        encoding="utf-8",
    )

    with pytest.raises(InputLoadError):
        load_batch_manifest(manifest_path)


# ---------------------------------------------------------------------------
# CLI-level tests for the batch command
# ---------------------------------------------------------------------------


def test_batch_cli_feasible_manifest_exits_zero() -> None:
    result = _runner.invoke(
        app,
        [
            "batch",
            str(REPO_ROOT / "examples/batch/demo_batch.yaml"),
        ],
    )
    assert result.exit_code == int(CliExitCode.INFEASIBLE)  # alpine_infeasible run


def test_batch_cli_all_feasible_exits_zero(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: run1",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        ["batch", str(manifest_path), "--engineering-only"],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)


def test_batch_cli_invalid_manifest_exits_invalid_input(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.yaml"
    bad_path.write_text("format_version: batch.v99\nruns: []\n", encoding="utf-8")
    result = _runner.invoke(app, ["batch", str(bad_path)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


def test_batch_cli_output_dir_geojson_writes_geojson_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: demo",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--engineering-only",
            "--output-dir",
            str(out_dir),
            "--format",
            "geojson",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".geojson"
    import json

    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["type"] == "FeatureCollection"
    layers = {f["properties"]["layer"] for f in doc["features"]}
    assert "route" in layers


def test_batch_cli_output_dir_writes_envelopes(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: demo",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--engineering-only",
            "--output-dir",
            str(out_dir),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert out_dir.is_dir()
    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".json"


# ---------------------------------------------------------------------------
# Batch table formatting helpers
# ---------------------------------------------------------------------------


def _stub_result(
    run_id: str = "run",
    status: str = "FEASIBLE",
    reserve: float | None = 12.5,
    flight_time_s: float | None = 1628.0,
    warning_count: int = 0,
) -> BatchRunResult:
    return BatchRunResult(
        id=run_id,
        status=status,
        reserve_margin_percent=reserve,
        flight_time_s=flight_time_s,
        envelope=None,
        warning_count=warning_count,
    )


def test_format_reserve_margin_positive() -> None:
    assert format_reserve_margin(12.5) == "+12.5 %"


def test_format_reserve_margin_negative() -> None:
    assert format_reserve_margin(-4.1) == "−4.1 %"


def test_format_reserve_margin_none_shows_dash() -> None:
    assert format_reserve_margin(None) == "—"


def test_format_flight_time_formats_minutes_and_seconds() -> None:
    assert format_flight_time(1628.0) == "27m 08s"


def test_format_flight_time_zero_seconds() -> None:
    assert format_flight_time(120.0) == "2m 00s"


def test_format_flight_time_none_shows_dash() -> None:
    assert format_flight_time(None) == "—"


def test_render_batch_table_contains_run_id() -> None:
    output = render_batch_table([_stub_result("my-run")])
    assert "my-run" in output


def test_render_batch_table_shows_warnings_count_when_nonzero() -> None:
    output = render_batch_table([_stub_result(warning_count=3)])
    assert "3" in output


def test_render_batch_table_shows_dash_for_zero_warnings() -> None:
    output = render_batch_table([_stub_result(warning_count=0)])
    assert "—" in output


# ---------------------------------------------------------------------------
# _batch_output_extension unit tests
# ---------------------------------------------------------------------------


def test_batch_output_extension_markdown_returns_md() -> None:
    assert _batch_output_extension(OutputFormat.MARKDOWN) == ".md"


def test_batch_output_extension_summary_returns_txt() -> None:
    assert _batch_output_extension(OutputFormat.SUMMARY) == ".txt"


def test_batch_output_extension_kml_returns_kml() -> None:
    assert _batch_output_extension(OutputFormat.KML) == ".kml"


def test_batch_output_extension_geojson_returns_geojson() -> None:
    assert _batch_output_extension(OutputFormat.GEOJSON) == ".geojson"


def test_batch_output_extension_json_returns_json() -> None:
    assert _batch_output_extension(OutputFormat.JSON) == ".json"


def test_batch_cli_output_dir_markdown_writes_md_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: demo",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--engineering-only",
            "--output-dir",
            str(out_dir),
            "--format",
            "markdown",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".md"
    content = files[0].read_text(encoding="utf-8")
    assert "# Estimator Report" in content


def test_batch_cli_output_dir_kml_writes_kml_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: demo",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--engineering-only",
            "--output-dir",
            str(out_dir),
            "--format",
            "kml",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".kml"
    content = files[0].read_text(encoding="utf-8")
    assert "<?xml" in content
    assert "<kml" in content


def test_render_batch_table_summary_line_contains_counts() -> None:
    results = [
        _stub_result("r1", status="FEASIBLE"),
        _stub_result("r2", status="INFEASIBLE", reserve=-3.0),
        _stub_result("r3", status="ERROR", reserve=None, flight_time_s=None),
    ]
    output = render_batch_table(results)
    assert "3 runs" in output
    assert "1 feasible" in output
    assert "1 infeasible" in output
    assert "1 errors" in output


def test_batch_cli_output_dir_profile_writes_md_files(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: demo",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--engineering-only",
            "--output-dir",
            str(out_dir),
            "--format",
            "profile",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".md"
    content = files[0].read_text(encoding="utf-8")
    assert "## Route Altitude Profile" in content


def test_batch_profile_preserves_terrain_evidence(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: alpine",
                f"    mission: {REPO_ROOT / 'examples/real_world/alpine_mission.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--output-dir",
            str(out_dir),
            "--format",
            "profile",
        ],
    )

    assert result.exit_code in {int(CliExitCode.SUCCESS), int(CliExitCode.INFEASIBLE)}
    content = (out_dir / "alpine.md").read_text(encoding="utf-8")
    assert "Terrain data not available" not in content
    assert "Terrain m" in content


def test_batch_error_overwrites_stale_success_artifact(tmp_path: Path) -> None:
    output = tmp_path / "run.json"
    output.write_text('{"status": "success"}\n', encoding="utf-8")
    result = _stub_result(
        "run",
        status="ERROR",
        reserve=None,
        flight_time_s=None,
    )
    result = replace(result, error_message="mission input missing")

    write_batch_outputs(
        output_dir=tmp_path,
        output_format=OutputFormat.JSON,
        results=[result],
    )

    content = output.read_text(encoding="utf-8")
    assert '"status": "ERROR"' in content
    assert "mission input missing" in content


def test_batch_cli_rejects_stale_files_from_removed_runs(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    stale = output_dir / "removed-run.json"
    stale.write_text('{"status":"success"}\n', encoding="utf-8")
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: current-run",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--format",
            "json",
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "not produced by this run" in result.output
    assert stale.exists()


# ---------------------------------------------------------------------------
# CSV format
# ---------------------------------------------------------------------------


def test_render_batch_csv_has_header_row() -> None:
    output = render_batch_csv([_stub_result("run1")])
    lines = output.strip().splitlines()
    assert lines[0] == "id,status,reserve_margin_percent,flight_time_s,warning_count"


def test_render_batch_csv_has_one_data_row_per_result() -> None:
    results = [
        _stub_result("r1"),
        _stub_result("r2", status="INFEASIBLE", reserve=-5.0),
    ]
    output = render_batch_csv(results)
    data_rows = output.strip().splitlines()[1:]
    assert len(data_rows) == 2


def test_render_batch_csv_none_fields_are_empty() -> None:
    output = render_batch_csv([_stub_result("r1", reserve=None, flight_time_s=None)])
    data_line = output.strip().splitlines()[1]
    parts = data_line.split(",")
    assert parts[2] == ""  # reserve_margin_percent empty
    assert parts[3] == ""  # flight_time_s empty


def test_render_batch_csv_ends_with_newline() -> None:
    output = render_batch_csv([_stub_result("r1")])
    assert output.endswith("\n")


def test_batch_cli_csv_format_exits_zero() -> None:
    result = _runner.invoke(
        app,
        ["batch", str(REPO_ROOT / "examples/batch/demo_batch.yaml"), "--format", "csv"],
    )
    assert result.exit_code in (int(CliExitCode.SUCCESS), int(CliExitCode.INFEASIBLE))
    lines = result.output.strip().splitlines()
    assert lines[0] == "id,status,reserve_margin_percent,flight_time_s,warning_count"
    assert len(lines) >= 2


def test_batch_cli_output_dir_checklist_shows_run_id(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    out_dir = tmp_path / "out"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: my_named_run",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest_path),
            "--engineering-only",
            "--output-dir",
            str(out_dir),
            "--format",
            "checklist",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "## Pre-Flight Checklist: my_named_run" in content


def test_batch_validate_only_exits_success(tmp_path: Path) -> None:
    manifest_path = tmp_path / "batch.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: run_a",
                f"    mission: {REPO_ROOT / 'examples/missions/pipeline_demo_001.yaml'}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(app, ["batch", str(manifest_path), "--validate-only"])
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "batch.yaml: OK (1 runs)" in result.output
    assert "pipeline_demo_001.yaml: OK" in result.output
    assert "quadplane_v1.yaml: OK" in result.output


def test_batch_validate_only_invalid_mission_exits_invalid_input(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "batch.yaml"
    bad_mission = tmp_path / "bad.yaml"
    bad_mission.write_text("not: valid: mission", encoding="utf-8")
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: run_a",
                f"    mission: {bad_mission}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )
    result = _runner.invoke(app, ["batch", str(manifest_path), "--validate-only"])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


def test_batch_manifest_rejects_duplicate_run_ids() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="Duplicate run id"):
        _manifest(
            _run(
                "same_id",
                REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            ),
            _run(
                "same_id",
                REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            ),
        )


def test_batch_manifest_rejects_invalid_run_id_characters() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="pattern"):
        _manifest(
            _run(
                "run/bad",
                REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
                REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
            ),
        )


def test_batch_parses_shared_inputs_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runs sharing mission/vehicle/asset files must not re-parse them."""
    import adapters.cli_support as cli_support
    from adapters.batch_support import run_batch_manifest as run_manifest

    fixture = Path(__file__).parent / "fixtures" / "golden" / "terrain"
    calls = {"terrain": 0}
    original = cli_support.load_terrain_grid

    def counting_loader(path: Path):  # noqa: ANN202
        calls["terrain"] += 1
        return original(path)

    monkeypatch.setattr(cli_support, "load_terrain_grid", counting_loader)
    manifest = BatchManifest(
        format_version="batch.v1",
        runs=[
            BatchRun(
                id=f"r{index}",
                mission=fixture / "mission.yaml",
                vehicle=fixture / "vehicle.yaml",
            )
            for index in range(3)
        ],
    )

    results = run_manifest(manifest, engineering_only=True)

    assert len(results) == 3
    assert calls["terrain"] == 1


# ---------------------------------------------------------------------------
# Ticket 064: scenario and propagate run types
# ---------------------------------------------------------------------------

_SCENARIO = REPO_ROOT / "examples/scenarios/pipeline_demo_001_scenario.yaml"
_DEMO_MISSION = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
_DEMO_VEHICLE = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"
_PLAN = REPO_ROOT / "examples/stochastic/pipeline_demo_001_stochastic.yaml"


def _write_manifest(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "batch.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_batch_manifest_defaults_run_type_to_estimate() -> None:
    manifest = _manifest(
        _run(
            "r1",
            REPO_ROOT / "examples/missions/pipeline_demo_001.yaml",
            REPO_ROOT / "examples/vehicles/quadplane_v1.yaml",
        )
    )
    assert manifest.run_type == "estimate"


def test_scenario_run_type_requires_scenario_field() -> None:
    with pytest.raises(ValueError, match="must set scenario"):
        BatchManifest(
            format_version="batch.v1",
            run_type="scenario",
            runs=[BatchRun(id="r1", mission=Path("m.yaml"), vehicle=Path("v.yaml"))],
        )


def test_scenario_run_type_forbids_mission_field() -> None:
    with pytest.raises(ValueError, match="must not set mission"):
        BatchManifest(
            format_version="batch.v1",
            run_type="scenario",
            runs=[
                BatchRun(id="r1", scenario=Path("s.yaml"), mission=Path("m.yaml"))
            ],
        )


def test_propagate_run_type_requires_plan_field() -> None:
    with pytest.raises(ValueError, match="must set plan"):
        BatchManifest(
            format_version="batch.v1",
            run_type="propagate",
            runs=[BatchRun(id="r1", scenario=Path("s.yaml"))],
        )


def test_batch_cli_scenario_run_type(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        "format_version: \"batch.v1\"\n"
        "run_type: scenario\n"
        "runs:\n"
        f"  - {{id: s1, scenario: {_SCENARIO}}}\n"
        f"  - {{id: s2, scenario: {_SCENARIO}}}\n",
    )
    # The demo scenario passes its assertions but the mission is NO-GO on
    # missing evidence, so the operational gate applies unless it is waived.
    result = _runner.invoke(app, ["batch", str(manifest), "--engineering-only"])
    assert result.exit_code == 0, result.output
    assert "assertions" in result.output
    assert "PASSED" in result.output


def test_batch_scenario_runs_apply_the_operational_gate(tmp_path: Path) -> None:
    """A batch must grade a scenario exactly as the scenario command does."""

    manifest = _write_manifest(
        tmp_path,
        'format_version: "batch.v1"\n'
        "run_type: scenario\n"
        "runs:\n"
        f"  - {{id: s1, scenario: {_SCENARIO}}}\n",
    )

    gated = _runner.invoke(app, ["batch", str(manifest)])
    waived = _runner.invoke(app, ["batch", str(manifest), "--engineering-only"])
    direct = _runner.invoke(app, ["scenario", str(_SCENARIO)])

    assert gated.exit_code == int(CliExitCode.INFEASIBLE), gated.output
    assert "FAILED" in gated.output
    assert waived.exit_code == 0, waived.output
    # Same run, same verdict, whichever command graded it.
    assert gated.exit_code == direct.exit_code


def test_batch_cli_scenario_writes_per_run_envelopes(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    manifest = _write_manifest(
        tmp_path,
        "format_version: \"batch.v1\"\n"
        "run_type: scenario\n"
        f"runs:\n  - {{id: s1, scenario: {_SCENARIO}}}\n",
    )
    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest),
            "--format",
            "json",
            "--output-dir",
            str(out_dir),
            "--engineering-only",
        ],
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads((out_dir / "s1.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "scenario-report.v3"


def test_batch_cli_propagate_run_type(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        "format_version: \"batch.v1\"\n"
        "run_type: propagate\n"
        f"runs:\n  - {{id: p1, plan: {_PLAN}}}\n",
    )
    result = _runner.invoke(app, ["batch", str(manifest)])
    assert result.exit_code == 0, result.output
    assert "modeled pass rate" in result.output
    assert "DIAGNOSTIC" in result.output


def test_batch_cli_propagate_writes_stochastic_envelope(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    manifest = _write_manifest(
        tmp_path,
        "format_version: \"batch.v1\"\n"
        "run_type: propagate\n"
        f"runs:\n  - {{id: p1, plan: {_PLAN}}}\n",
    )
    result = _runner.invoke(
        app, ["batch", str(manifest), "--format", "json", "--output-dir", str(out_dir)]
    )
    assert result.exit_code == 0, result.output
    import json

    payload = json.loads((out_dir / "p1.json").read_text(encoding="utf-8"))
    assert payload["schema_version"] == "stochastic-envelope.v2"


def test_batch_cli_scenario_rejects_estimate_only_format(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    manifest = _write_manifest(
        tmp_path,
        "format_version: \"batch.v1\"\n"
        "run_type: scenario\n"
        f"runs:\n  - {{id: s1, scenario: {_SCENARIO}}}\n",
    )
    result = _runner.invoke(
        app,
        ["batch", str(manifest), "--format", "geojson", "--output-dir", str(out_dir)],
    )
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "only available for estimate runs" in result.output


def test_batch_cli_scenario_validate_only(tmp_path: Path) -> None:
    manifest = _write_manifest(
        tmp_path,
        "format_version: \"batch.v1\"\n"
        "run_type: scenario\n"
        f"runs:\n  - {{id: s1, scenario: {_SCENARIO}}}\n",
    )
    result = _runner.invoke(app, ["batch", str(manifest), "--validate-only"])
    assert result.exit_code == 0, result.output
    assert "scenario:" in result.output


def test_scenario_failed_status_exits_infeasible() -> None:
    from adapters.cli_batch_support import _batch_exit_code

    results = [
        BatchRunResult(
            id="s1",
            status="FAILED",
            run_type="scenario",
            reserve_margin_percent=None,
            flight_time_s=None,
            envelope=None,
        )
    ]
    assert _batch_exit_code(results) == int(CliExitCode.INFEASIBLE)


def test_propagate_diagnostic_status_exits_zero() -> None:
    from adapters.cli_batch_support import _batch_exit_code

    results = [
        BatchRunResult(
            id="p1",
            status="DIAGNOSTIC",
            run_type="propagate",
            reserve_margin_percent=None,
            flight_time_s=None,
            envelope=None,
        )
    ]
    assert _batch_exit_code(results) == int(CliExitCode.SUCCESS)


def test_batch_completes_good_runs_when_one_run_cannot_load(tmp_path: Path) -> None:
    """One bad run must not discard every run that already completed.

    Missions are preloaded to enumerate their assets, so a single unreadable
    mission aborted the whole batch before any run executed.
    """

    manifest = _write_manifest(
        tmp_path,
        'format_version: "batch.v1"\n'
        "runs:\n"
        f"  - {{id: good1, mission: {_DEMO_MISSION}, vehicle: {_DEMO_VEHICLE}}}\n"
        f"  - {{id: bad, mission: /nonexistent/mission.yaml, vehicle: {_DEMO_VEHICLE}}}\n"
        f"  - {{id: good2, mission: {_DEMO_MISSION}, vehicle: {_DEMO_VEHICLE}}}\n",
    )

    result = _runner.invoke(app, ["batch", str(manifest), "--engineering-only"])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT), result.output
    assert "good1" in result.output
    assert "good2" in result.output
    assert "2 feasible" in result.output
    # The failing run is named along with the file that could not be read.
    assert "bad" in result.output
    assert "/nonexistent/mission.yaml" in result.output


def test_batch_output_dir_tolerates_a_leftover_temp_file(tmp_path: Path) -> None:
    """An interrupted run left a temp file that blocked the directory forever."""

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / ".e1.json.abc123.tmp").write_text("partial", encoding="utf-8")
    manifest = _write_manifest(
        tmp_path,
        'format_version: "batch.v1"\n'
        f"runs:\n  - {{id: e1, mission: {_DEMO_MISSION}, vehicle: {_DEMO_VEHICLE}}}\n",
    )

    result = _runner.invoke(
        app,
        [
            "batch",
            str(manifest),
            "--format",
            "json",
            "--output-dir",
            str(out_dir),
            "--engineering-only",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (out_dir / "e1.json").exists()
    assert not (out_dir / ".e1.json.abc123.tmp").exists()
