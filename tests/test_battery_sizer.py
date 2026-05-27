import json
from pathlib import Path

from typer.testing import CliRunner

from adapters.battery_sizer import (
    compute_minimum_battery_capacity,
    render_battery_sizing_markdown,
)
from adapters.cli import CliExitCode, app
from adapters.io import load_mission, load_vehicle
from estimator import try_estimate_mission_distance_time
from schemas import VehicleProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples" / "missions" / "pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"
INFEASIBLE_MISSION_PATH = REPO_ROOT / "examples" / "real_world" / "alpine_infeasible.yaml"
INFEASIBLE_VEHICLE_PATH = (
    REPO_ROOT / "examples" / "real_world" / "quadplane_small_battery.yaml"
)
GOLDEN_ROOT = REPO_ROOT / "tests" / "fixtures" / "golden"
SUCCESS_MISSION_PATH = GOLDEN_ROOT / "success" / "mission.yaml"
SUCCESS_VEHICLE_PATH = GOLDEN_ROOT / "success" / "vehicle.yaml"
BATTERY_SIZING_GOLDEN = GOLDEN_ROOT / "battery_sizing" / "envelope.json"

runner = CliRunner()


def _pipeline_inputs():
    mission, _ = load_mission(MISSION_PATH)
    vehicle, _ = load_vehicle(VEHICLE_PATH)
    return mission, vehicle


def _vehicle_with_capacity(vehicle: VehicleProfile, capacity_wh: float) -> VehicleProfile:
    return vehicle.model_copy(
        update={
            "energy": vehicle.energy.model_copy(
                update={"battery_capacity_wh": capacity_wh}
            )
        }
    )


def test_binary_search_finds_minimum_capacity() -> None:
    mission, vehicle = _pipeline_inputs()

    result = compute_minimum_battery_capacity(
        mission,
        vehicle,
        tolerance_wh=0.05,
    )

    reserve_fraction = result.reserve_threshold_wh / result.current_capacity_wh
    expected_capacity = result.mission_energy_wh / (1.0 - reserve_fraction)
    assert abs(result.minimum_capacity_wh - expected_capacity) < 0.1


def test_minimum_capacity_is_at_feasibility_boundary() -> None:
    mission, vehicle = _pipeline_inputs()
    result = compute_minimum_battery_capacity(
        mission,
        vehicle,
        tolerance_wh=0.05,
    )

    minimum_estimate = try_estimate_mission_distance_time(
        mission,
        _vehicle_with_capacity(vehicle, result.minimum_capacity_wh),
    )
    below_estimate = try_estimate_mission_distance_time(
        mission,
        _vehicle_with_capacity(vehicle, result.minimum_capacity_wh - 1.0),
    )

    assert minimum_estimate.energy is not None
    assert below_estimate.energy is not None
    assert (
        minimum_estimate.energy.reserve_at_landing_wh
        >= minimum_estimate.energy.reserve_threshold_wh
    )
    assert (
        below_estimate.energy.reserve_at_landing_wh
        < below_estimate.energy.reserve_threshold_wh
    )


def test_oversized_battery_reports_current_feasible() -> None:
    mission, vehicle = _pipeline_inputs()

    result = compute_minimum_battery_capacity(mission, vehicle)

    assert result.is_current_feasible is True
    assert result.current_capacity_wh > result.minimum_capacity_wh


def test_markdown_contains_recommendation_line() -> None:
    mission, vehicle = _pipeline_inputs()
    vehicle = _vehicle_with_capacity(vehicle, 45.0)
    result = compute_minimum_battery_capacity(mission, vehicle, tolerance_wh=0.05)

    rendered = render_battery_sizing_markdown(
        result,
        mission_id=mission.mission_id,
        safety_margins=[10],
    )

    assert "Recommendation: use >=" in rendered
    assert "Status: SIZED" in rendered


def test_markdown_shows_safety_margin_recommendations() -> None:
    mission, vehicle = _pipeline_inputs()
    vehicle = _vehicle_with_capacity(vehicle, 45.0)
    result = compute_minimum_battery_capacity(mission, vehicle, tolerance_wh=0.05)

    rendered = render_battery_sizing_markdown(
        result,
        mission_id=mission.mission_id,
        safety_margins=[10, 20, 30],
    )

    assert "With 10 % safety margin:" in rendered
    assert "With 20 % safety margin:" in rendered
    assert "With 30 % safety margin:" in rendered


def test_size_battery_cli_success_fixture_exits_zero() -> None:
    result = runner.invoke(
        app,
        ["size-battery", str(MISSION_PATH), str(VEHICLE_PATH)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Status: FEASIBLE" in result.output


def test_size_battery_cli_infeasible_fixture_outputs_minimum_capacity() -> None:
    result = runner.invoke(
        app,
        ["size-battery", str(INFEASIBLE_MISSION_PATH), str(INFEASIBLE_VEHICLE_PATH)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Minimum feasible capacity:" in result.output
    assert "Status: SIZED" in result.output


def test_size_battery_json_matches_golden_fixture() -> None:
    result = runner.invoke(
        app,
        [
            "size-battery",
            str(SUCCESS_MISSION_PATH),
            str(SUCCESS_VEHICLE_PATH),
            "--format",
            "json",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert json.loads(result.output)["schema_version"] == "battery-sizing-report.v1"
    assert result.output == BATTERY_SIZING_GOLDEN.read_text(encoding="utf-8")
