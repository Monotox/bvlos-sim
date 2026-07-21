"""Tests for energy reserve sensitivity reports."""

from pathlib import Path

from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from adapters.io import load_mission, load_vehicle
from adapters.sensitivity import (
    SensitivityLevel,
    render_sensitivity_markdown,
    run_sensitivity_sweep,
)
from estimator import MissionEstimate, try_estimate_mission_distance_time
from schemas import MissionPlan, VehicleProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"
_runner = CliRunner()


def _mission_vehicle() -> tuple[MissionPlan, VehicleProfile]:
    mission, _mission_doc = load_mission(MISSION_PATH)
    vehicle, _vehicle_doc = load_vehicle(VEHICLE_PATH)
    return mission, vehicle


def _baseline() -> MissionEstimate:
    mission, vehicle = _mission_vehicle()
    return try_estimate_mission_distance_time(mission, vehicle)


def _levels() -> list[SensitivityLevel]:
    mission, vehicle = _mission_vehicle()
    return run_sensitivity_sweep(
        mission,
        vehicle,
        power_steps=[10, 20, 30],
        wind_steps=[1.0, 2.0, 3.0],
        battery_steps=[10, 20, 30],
    )


def _level(
    levels: list[SensitivityLevel],
    parameter: str,
    variation_value: float,
) -> SensitivityLevel:
    return next(
        level
        for level in levels
        if level.parameter == parameter and level.variation_value == variation_value
    )


def test_sensitivity_baseline_run_matches_plain_estimate() -> None:
    baseline = _baseline()
    levels = _levels()

    assert baseline.energy is not None
    baseline_levels = [level for level in levels if level.variation_value == 0.0]
    assert len(baseline_levels) == 3
    assert all(
        level.reserve_wh == baseline.energy.reserve_at_landing_wh
        for level in baseline_levels
    )


def test_sensitivity_positive_power_reduces_reserve() -> None:
    levels = _levels()

    assert (
        _level(levels, "cruise_power", 10.0).reserve_wh
        < _level(
            levels,
            "cruise_power",
            0.0,
        ).reserve_wh
    )


def test_sensitivity_headwind_reduces_reserve() -> None:
    levels = _levels()
    headwind_levels = [level for level in levels if level.parameter == "headwind"]
    reserves = [level.reserve_wh for level in headwind_levels]

    assert reserves == sorted(reserves, reverse=True)


def test_sensitivity_battery_reduction_reduces_reserve() -> None:
    levels = _levels()

    assert (
        _level(levels, "battery_capacity", -10.0).reserve_wh
        < _level(
            levels,
            "battery_capacity",
            0.0,
        ).reserve_wh
    )


def test_sensitivity_all_levels_completed() -> None:
    levels = _levels()

    assert len(levels) == 21
    assert {level.status for level in levels} == {"FEASIBLE"}


def test_sensitivity_markdown_contains_all_sections() -> None:
    output = render_sensitivity_markdown(
        _baseline(),
        _levels(),
        mission_id="pipeline_demo_001",
    )

    assert "# Energy Reserve Sensitivity: pipeline_demo_001" in output
    assert "## Cruise Power Variation" in output
    assert "## Headwind Variation (applied to all legs)" in output
    assert "## Battery Capacity Variation" in output
    assert "Sensitivity scan: 3 parameters x 7 levels = 21 runs" in output


def test_sensitivity_markdown_status_robust_when_all_feasible() -> None:
    output = render_sensitivity_markdown(
        _baseline(),
        _levels(),
        mission_id="pipeline_demo_001",
    )

    assert "Status: ROBUST" in output


def test_sensitivity_markdown_status_marginal_when_any_infeasible() -> None:
    levels = [
        SensitivityLevel(
            parameter="cruise_power",
            variation_label="baseline",
            variation_value=0.0,
            reserve_wh=100.0,
            reserve_pct=50.0,
            status="FEASIBLE",
        ),
        SensitivityLevel(
            parameter="cruise_power",
            variation_label="+30%",
            variation_value=30.0,
            reserve_wh=10.0,
            reserve_pct=5.0,
            status="INFEASIBLE",
        ),
    ]

    output = render_sensitivity_markdown(
        _baseline(),
        levels,
        mission_id="pipeline_demo_001",
    )

    assert "Status: MARGINAL" in output


def test_estimate_sensitivity_format_exits_zero_and_reports_status() -> None:
    result = _runner.invoke(
        app,
        [
            "estimate",
            str(MISSION_PATH),
            str(VEHICLE_PATH),
            "--format",
            "sensitivity",
            "--engineering-only",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Status: ROBUST" in result.output
