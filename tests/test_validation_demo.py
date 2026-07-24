"""The shipped validation demo must pass its own acceptance gates.

The repository advertises a working validate → calibrate → estimate loop on
the bundled trace; a demo that fails its own thresholds is shipped evidence
that the model cannot be validated.
"""

from pathlib import Path

from typer.testing import CliRunner

from bvlos_sim.adapters.cli import app

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MISSION = _REPO_ROOT / "examples" / "missions" / "pipeline_demo_001.yaml"
_VEHICLE = _REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"
_TRACE = _REPO_ROOT / "examples" / "flight_logs" / "pipeline_demo_001_trace.json"
_CALIBRATION = (
    _REPO_ROOT / "examples" / "calibration" / "quadplane_v1_calibration.json"
)

runner = CliRunner()


def test_shipped_validation_demo_passes_acceptance_gates() -> None:
    result = runner.invoke(app, ["validate", str(_MISSION), str(_VEHICLE), str(_TRACE)])
    assert result.exit_code == 0, result.output


def test_shipped_calibration_applies_to_estimate() -> None:
    result = runner.invoke(
        app,
        [
            "estimate",
            str(_MISSION),
            str(_VEHICLE),
            "--calibration",
            str(_CALIBRATION),
            "--format",
            "summary",
            "--engineering-only",
        ],
    )
    assert result.exit_code == 0, result.output
