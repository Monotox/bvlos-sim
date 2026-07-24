"""The shipped complete-evidence mission must keep producing a GO.

Before this suite existed the project contained no GO verdict anywhere — not in
a fixture, an example, or a doc — so the passing branch of the readiness gate
was never exercised and teams had no reference for what complete evidence looks
like. These tests pin the example itself: if a future change makes GO
unreachable, or reachable without the evidence it is supposed to require, they
fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner
import yaml

from bvlos_sim.adapters.cli import CliExitCode, app

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPO_ROOT / "examples/missions/pipeline_demo_001_go.yaml"
VEHICLE = REPO_ROOT / "examples/vehicles/quadplane_v1_complete.yaml"
CALIBRATION = REPO_ROOT / "examples/calibration/quadplane_v1_calibration.json"

runner = CliRunner()

# Every category evaluate_operational_readiness() can report as missing.
GATED_EVIDENCE = (
    "energy",
    "geofence",
    "landing_zone",
    "resource",
    "link",
    "obstacle",
    "weather",
    "ground_risk",
)


def _estimate(*extra: str) -> dict:
    result = runner.invoke(
        app,
        ["estimate", str(MISSION), str(VEHICLE), "--format", "json", *extra],
    )
    assert result.stdout, result.output
    return json.loads(result.stdout)


def _calibrated() -> dict:
    return _estimate("--calibration", str(CALIBRATION))


def test_reference_mission_reaches_go() -> None:
    result = runner.invoke(
        app,
        [
            "estimate",
            str(MISSION),
            str(VEHICLE),
            "--calibration",
            str(CALIBRATION),
            "--format",
            "checklist",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Status: GO" in result.stdout


def test_go_requires_no_warning_waiver() -> None:
    """A GO that needs a waiver trains operators to waive warnings by habit."""
    readiness = _calibrated()["operational_readiness"]

    assert readiness["verdict"] == "go"
    assert readiness["is_go"] is True
    assert readiness["warning_codes"] == []
    assert readiness.get("acknowledged_warning_codes", []) == []
    assert MISSION.read_text(encoding="utf-8").find("accepted_warning_codes") == -1


def test_every_gated_evidence_category_is_present_and_feasible() -> None:
    envelope = _calibrated()
    readiness = envelope["operational_readiness"]

    assert readiness["missing_evidence"] == []
    assert readiness["failed_checks"] == []
    for category in GATED_EVIDENCE:
        check = envelope["result"][category]
        assert check is not None, f"{category} evidence is missing"
    assert envelope["result"]["rth_is_feasible"] is not False


def test_uncalibrated_run_of_the_same_mission_is_blocked() -> None:
    """Identical inputs minus the calibration profile must not reach GO.

    Placeholder power coefficients used to produce a GO indistinguishable from
    one backed by real flight data.
    """
    readiness = _estimate()["operational_readiness"]

    assert readiness["is_go"] is False
    assert "ENERGY_MODEL_UNCALIBRATED" in readiness["warning_codes"]


@pytest.mark.parametrize(
    "asset",
    ["geofences_file", "landing_zones_file", "obstacles_file", "population_grid_file"],
)
def test_dropping_any_asset_falls_back_to_no_go(asset: str, tmp_path: Path) -> None:
    """Fail-closed means the GO is load-bearing on every asset, not decorative."""
    payload = yaml.safe_load(MISSION.read_text(encoding="utf-8"))
    assets = payload["assets"]
    for name, value in list(assets.items()):
        assets[name] = str((MISSION.parent / value).resolve())
    del assets[asset]
    reduced = tmp_path / "reduced.yaml"
    reduced.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "estimate",
            str(reduced),
            str(VEHICLE),
            "--calibration",
            str(CALIBRATION),
            "--format",
            "json",
        ],
    )
    readiness = json.loads(result.stdout)["operational_readiness"]

    assert readiness["is_go"] is False
