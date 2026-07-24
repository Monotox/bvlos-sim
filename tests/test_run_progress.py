"""Tests for machine-readable run progress (Ticket 106).

Covers the JSONL progress side-channel on ``sample``, ``propagate``, and
``batch``: record shape, monotonic ``completed`` with a final ``completed ==
total`` record, that progress never leaks into the ``--output`` stream, that the
feature is off by default, and a direct callback contract on ``run_monte_carlo``.
"""

import json
import os
from pathlib import Path

import yaml
from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.adapters.io import load_mission, load_vehicle
from bvlos_sim.adapters.uncertainty_io import (
    load_uncertainty_plan,
    resolve_uncertainty_asset_path,
)
from bvlos_sim.estimator.execution.monte_carlo import run_monte_carlo
from tests.helpers import make_mission_payload

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_UNCERTAINTY = (
    REPO_ROOT / "examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml"
)
EXAMPLE_STOCHASTIC = REPO_ROOT / "examples/stochastic/pipeline_demo_001_stochastic.yaml"
EXAMPLE_BATCH = REPO_ROOT / "examples/batch/demo_batch.yaml"

runner = CliRunner()


def _read_progress_records(path: Path) -> list[dict]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [json.loads(line) for line in lines]


def _assert_valid_progress(records: list[dict], *, command: str, total: int) -> None:
    assert records, "expected at least one progress record"
    completions = []
    for record in records:
        assert record["event"] == "progress"
        assert record["command"] == command
        assert record["total"] == total
        assert isinstance(record["elapsed_s"], (int, float))
        assert record["elapsed_s"] >= 0
        completions.append(record["completed"])
    # completed is strictly increasing and the final record reaches total.
    assert all(b > a for a, b in zip(completions, completions[1:], strict=False))
    assert completions[-1] == total


# ---------------------------------------------------------------------------
# CLI progress-file tests
# ---------------------------------------------------------------------------


def test_sample_progress_file_records(tmp_path: Path) -> None:
    progress_path = tmp_path / "progress.jsonl"
    output_path = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "sample",
            str(EXAMPLE_UNCERTAINTY),
            "--progress-file",
            str(progress_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    records = _read_progress_records(progress_path)
    _assert_valid_progress(records, command="sample", total=200)
    # The output envelope must not contain progress framing.
    assert '"event":"progress"' not in output_path.read_text(encoding="utf-8")
    assert '"event": "progress"' not in output_path.read_text(encoding="utf-8")


def test_propagate_progress_file_records(tmp_path: Path) -> None:
    progress_path = tmp_path / "progress.jsonl"
    output_path = tmp_path / "out.json"
    result = runner.invoke(
        app,
        [
            "propagate",
            str(EXAMPLE_STOCHASTIC),
            "--progress-file",
            str(progress_path),
            "--output",
            str(output_path),
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    records = _read_progress_records(progress_path)
    _assert_valid_progress(records, command="propagate", total=100)
    assert "progress" not in output_path.read_text(encoding="utf-8")


def test_batch_progress_file_records(tmp_path: Path) -> None:
    progress_path = tmp_path / "progress.jsonl"
    result = runner.invoke(
        app,
        [
            "batch",
            str(EXAMPLE_BATCH),
            "--progress-file",
            str(progress_path),
        ],
    )
    # The demo manifest includes an infeasible run, so the exit code is 10; the
    # progress side-channel is independent of the feasibility verdict.
    assert result.exit_code in {
        int(CliExitCode.SUCCESS),
        int(CliExitCode.INFEASIBLE),
    }
    records = _read_progress_records(progress_path)
    _assert_valid_progress(records, command="batch", total=3)
    # Batch records name the run that just completed so a worker can
    # attribute stalls.
    assert all(isinstance(record.get("run_id"), str) for record in records)
    # stdout carries the table, never progress framing.
    assert '"event":"progress"' not in result.stdout


# ---------------------------------------------------------------------------
# stderr sink and off-by-default
# ---------------------------------------------------------------------------


def test_progress_to_stderr_not_stdout() -> None:
    result = runner.invoke(
        app,
        ["sample", str(EXAMPLE_UNCERTAINTY), "--progress-format", "jsonl"],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert '"event":"progress"' in result.stderr
    # The result envelope on stdout stays clean JSON with no progress records.
    payload = json.loads(result.stdout)
    assert payload["schema_version"]
    assert '"event":"progress"' not in result.stdout


def test_progress_off_by_default_is_unchanged(tmp_path: Path) -> None:
    baseline_out = tmp_path / "baseline.json"
    progress_out = tmp_path / "with_progress.json"
    progress_file = tmp_path / "progress.jsonl"

    baseline = runner.invoke(
        app, ["sample", str(EXAMPLE_UNCERTAINTY), "--output", str(baseline_out)]
    )
    with_progress = runner.invoke(
        app,
        [
            "sample",
            str(EXAMPLE_UNCERTAINTY),
            "--output",
            str(progress_out),
            "--progress-file",
            str(progress_file),
        ],
    )

    assert baseline.exit_code == int(CliExitCode.SUCCESS)
    assert with_progress.exit_code == int(CliExitCode.SUCCESS)
    # Enabling progress does not change the result envelope at all.
    assert baseline_out.read_bytes() == progress_out.read_bytes()
    # A run with no progress flag emits no progress framing on stderr.
    assert "progress" not in baseline.stderr


def test_progress_file_cannot_overwrite_output(tmp_path: Path) -> None:
    shared_path = tmp_path / "shared.json"
    result = runner.invoke(
        app,
        [
            "sample",
            str(EXAMPLE_UNCERTAINTY),
            "--output",
            str(shared_path),
            "--progress-file",
            str(shared_path),
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert not shared_path.exists()
    assert "overwrite" in result.stdout


def test_progress_file_cannot_overwrite_input_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "uncertainty.yaml"
    text = EXAMPLE_UNCERTAINTY.read_text(encoding="utf-8")
    text = text.replace(
        "../missions/pipeline_demo_001.yaml",
        str(REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"),
    ).replace(
        "../vehicles/quadplane_v1.yaml",
        str(REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"),
    )
    plan_path.write_text(text, encoding="utf-8")
    original = plan_path.read_bytes()

    result = runner.invoke(
        app,
        ["sample", str(plan_path), "--progress-file", str(plan_path)],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert plan_path.read_bytes() == original


def test_batch_progress_file_must_be_outside_output_directory(tmp_path: Path) -> None:
    output_dir = tmp_path / "outputs"
    progress_path = output_dir / "progress.jsonl"
    result = runner.invoke(
        app,
        [
            "batch",
            str(EXAMPLE_BATCH),
            "--format",
            "json",
            "--output-dir",
            str(output_dir),
            "--progress-file",
            str(progress_path),
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert not progress_path.exists()


def test_batch_progress_file_cannot_overwrite_mission_asset(tmp_path: Path) -> None:
    terrain_path = tmp_path / "terrain.yaml"
    original = b"asset sentinel\n"
    terrain_path.write_bytes(original)
    mission_path = tmp_path / "mission.yaml"
    mission_payload = make_mission_payload()
    mission_payload["assets"] = {"terrain_file": terrain_path.name}
    mission_path.write_text(
        yaml.safe_dump(mission_payload, sort_keys=False),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "batch.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: run",
                f"    mission: {mission_path}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["batch", str(manifest_path), "--progress-file", str(terrain_path)],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert terrain_path.read_bytes() == original
    assert "overwrite" in result.output


def test_batch_progress_file_cannot_overwrite_hardlinked_input(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    mission_path.write_text(
        yaml.safe_dump(make_mission_payload(), sort_keys=False),
        encoding="utf-8",
    )
    progress_path = tmp_path / "progress.jsonl"
    os.link(mission_path, progress_path)
    original = mission_path.read_bytes()
    manifest_path = tmp_path / "batch.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "format_version: batch.v1",
                "runs:",
                "  - id: run",
                f"    mission: {mission_path}",
                f"    vehicle: {REPO_ROOT / 'examples/vehicles/quadplane_v1.yaml'}",
            ]
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["batch", str(manifest_path), "--progress-file", str(progress_path)],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert mission_path.read_bytes() == original
    assert "overwrite" in result.output


# ---------------------------------------------------------------------------
# Direct callback contract
# ---------------------------------------------------------------------------


def test_run_monte_carlo_invokes_callback_to_completion() -> None:
    plan, _ = load_uncertainty_plan(EXAMPLE_UNCERTAINTY)
    mission_path = resolve_uncertainty_asset_path(
        plan.mission_file, uncertainty_path=EXAMPLE_UNCERTAINTY
    )
    vehicle_path = resolve_uncertainty_asset_path(
        plan.vehicle_file, uncertainty_path=EXAMPLE_UNCERTAINTY
    )
    mission, _ = load_mission(mission_path)
    vehicle, _ = load_vehicle(vehicle_path)

    calls: list[tuple[int, int]] = []

    def record(completed: int, total: int) -> None:
        calls.append((completed, total))

    run_monte_carlo(plan, mission, vehicle, progress=record)

    assert calls, "callback should be invoked at least once"
    completions = [completed for completed, _ in calls]
    assert all(b >= a for a, b in zip(completions, completions[1:], strict=False))
    assert calls[-1] == (plan.samples, plan.samples)
