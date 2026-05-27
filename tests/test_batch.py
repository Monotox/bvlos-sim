from pathlib import Path

import pytest

from adapters.batch_io import load_batch_manifest
from adapters.batch_support import run_batch_manifest
from adapters.cli import CliExitCode, app
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
