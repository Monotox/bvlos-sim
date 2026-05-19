from pathlib import Path

import pytest

from adapters.batch_io import load_batch_manifest
from adapters.batch_support import run_batch_manifest
from adapters.io import InputLoadError
from schemas.batch import BatchManifest, BatchRun

REPO_ROOT = Path(__file__).resolve().parents[1]


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
