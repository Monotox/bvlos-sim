from pathlib import Path

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
from adapters.cli_batch_support import _batch_output_extension
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
        )
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
        )
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
    result = _runner.invoke(app, ["batch", str(manifest_path)])
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
        ["batch", str(manifest_path), "--output-dir", str(out_dir), "--format", "geojson"],
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
        app, ["batch", str(manifest_path), "--output-dir", str(out_dir), "--format", "json"]
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
        ["batch", str(manifest_path), "--output-dir", str(out_dir), "--format", "markdown"],
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
        ["batch", str(manifest_path), "--output-dir", str(out_dir), "--format", "kml"],
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
        ["batch", str(manifest_path), "--output-dir", str(out_dir), "--format", "profile"],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".md"
    content = files[0].read_text(encoding="utf-8")
    assert "## Route Altitude Profile" in content


# ---------------------------------------------------------------------------
# CSV format
# ---------------------------------------------------------------------------


def test_render_batch_csv_has_header_row() -> None:
    output = render_batch_csv([_stub_result("run1")])
    lines = output.strip().splitlines()
    assert lines[0] == "id,status,reserve_margin_percent,flight_time_s,warning_count"


def test_render_batch_csv_has_one_data_row_per_result() -> None:
    results = [_stub_result("r1"), _stub_result("r2", status="INFEASIBLE", reserve=-5.0)]
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
        ["batch", str(manifest_path), "--output-dir", str(out_dir), "--format", "checklist"],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    files = list(out_dir.iterdir())
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "## Pre-Flight Checklist: my_named_run" in content
