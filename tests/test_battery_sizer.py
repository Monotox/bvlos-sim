import json
from dataclasses import replace
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bvlos_sim.adapters.battery_sizer import (
    _vehicle_with_capacity as _sized_vehicle,
    battery_capacity_recommendations,
    compute_minimum_battery_capacity,
    render_battery_sizing_markdown,
)
from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.adapters.io import load_mission, load_vehicle
from bvlos_sim.estimator import (
    EstimateStatus,
    EstimatorFailure,
    FailureCode,
    FailureKind,
    GeofenceKind,
    GeofenceZone,
    MissionEstimate,
    try_estimate_mission_distance_time,
)
from bvlos_sim.estimator.core.obstacle import Obstacle
from bvlos_sim.estimator.environment.obstacle import ListObstacleProvider
from bvlos_sim.schemas import VehicleProfile

REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION_PATH = REPO_ROOT / "examples" / "missions" / "pipeline_demo_001.yaml"
VEHICLE_PATH = REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"
INFEASIBLE_MISSION_PATH = (
    REPO_ROOT / "examples" / "real_world" / "alpine_infeasible.yaml"
)
INFEASIBLE_VEHICLE_PATH = (
    REPO_ROOT / "examples" / "real_world" / "quadplane_small_battery_sizing.yaml"
)
GOLDEN_ROOT = REPO_ROOT / "tests" / "fixtures" / "golden"
SUCCESS_MISSION_PATH = GOLDEN_ROOT / "success" / "mission.yaml"
SUCCESS_VEHICLE_PATH = GOLDEN_ROOT / "battery_sizing" / "vehicle.yaml"
BATTERY_SIZING_GOLDEN = GOLDEN_ROOT / "battery_sizing" / "envelope.json"

runner = CliRunner()


def _pipeline_inputs():
    mission, _ = load_mission(MISSION_PATH)
    vehicle, _ = load_vehicle(VEHICLE_PATH)
    payload = vehicle.model_dump(mode="python")
    payload["energy"].update(
        {
            "battery_specific_energy_wh_per_kg": 225.0,
            "battery_excluded_operating_mass_kg": 8.0,
        }
    )
    return mission, VehicleProfile.model_validate(payload)


def _vehicle_with_capacity(
    vehicle: VehicleProfile, capacity_wh: float
) -> VehicleProfile:
    return _sized_vehicle(vehicle, capacity_wh)


def test_search_reports_energy_at_minimum_capacity() -> None:
    mission, vehicle = _pipeline_inputs()

    result = compute_minimum_battery_capacity(
        mission,
        vehicle,
        tolerance_wh=0.05,
    )
    estimate = try_estimate_mission_distance_time(
        mission,
        _vehicle_with_capacity(vehicle, result.minimum_capacity_wh),
    )

    assert estimate.energy is not None
    assert result.mission_energy_wh == pytest.approx(estimate.energy.total_energy_wh)
    assert result.reserve_threshold_wh == pytest.approx(
        estimate.energy.reserve_threshold_wh
    )


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


def test_battery_sizing_fails_closed_without_capacity_mass_inputs() -> None:
    mission, vehicle = _pipeline_inputs()
    vehicle = vehicle.model_copy(
        update={
            "energy": vehicle.energy.model_copy(
                update={"battery_specific_energy_wh_per_kg": None}
            )
        }
    )

    with pytest.raises(ValueError, match="capacity-mass feedback inputs"):
        compute_minimum_battery_capacity(mission, vehicle)


def test_battery_sizing_stops_at_mtow_when_no_capacity_is_feasible() -> None:
    mission, vehicle = _pipeline_inputs()
    payload = vehicle.model_dump(mode="python")
    payload["energy"]["battery_capacity_wh"] = 30.0
    payload["mass"].update(
        {
            "max_payload_kg": 0.0,
            "max_takeoff_kg": 8.14,
        }
    )
    constrained = VehicleProfile.model_validate(payload)

    with pytest.raises(ValueError, match="max_takeoff_kg"):
        compute_minimum_battery_capacity(mission, constrained)


def test_battery_sizing_finds_narrow_non_monotone_feasible_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission, vehicle = _pipeline_inputs()
    template = try_estimate_mission_distance_time(mission, vehicle)
    assert template.energy is not None

    reserve_fraction = 0.25
    induced_exponent = 6.0
    specific_energy_wh_per_kg = 225.0
    battery_excluded_mass_kg = 8.0
    peak_capacity_wh = 500.0
    peak_mass_kg = battery_excluded_mass_kg + (
        peak_capacity_wh / specific_energy_wh_per_kg
    )
    induced_coefficient = (
        (1.0 - reserve_fraction)
        * specific_energy_wh_per_kg
        / (induced_exponent * peak_mass_kg ** (induced_exponent - 1.0))
    )
    unoffset_peak_margin_wh = (
        1.0 - reserve_fraction
    ) * peak_capacity_wh - induced_coefficient * peak_mass_kg**induced_exponent
    fixed_energy_wh = unoffset_peak_margin_wh - 0.02

    def energy_margin_wh(capacity_wh: float) -> float:
        operating_mass_kg = battery_excluded_mass_kg + (
            capacity_wh / specific_energy_wh_per_kg
        )
        mission_energy_wh = (
            fixed_energy_wh + induced_coefficient * operating_mass_kg**induced_exponent
        )
        return (1.0 - reserve_fraction) * capacity_wh - mission_energy_wh

    def fake_estimate_at_capacity(
        _mission: object,
        _vehicle: VehicleProfile,
        battery_capacity_wh: float,
        **_kwargs: object,
    ) -> MissionEstimate:
        margin_wh = energy_margin_wh(battery_capacity_wh)
        mission_energy_wh = (1.0 - reserve_fraction) * battery_capacity_wh - margin_wh
        feasible = margin_wh >= 0.0
        energy = template.energy.model_copy(
            update={
                "is_feasible": feasible,
                "total_energy_wh": mission_energy_wh,
                "battery_capacity_wh": battery_capacity_wh,
                "usable_energy_wh": ((1.0 - reserve_fraction) * battery_capacity_wh),
                "reserve_threshold_percent": reserve_fraction * 100.0,
                "reserve_threshold_wh": reserve_fraction * battery_capacity_wh,
                "reserve_at_landing_wh": battery_capacity_wh - mission_energy_wh,
                "reserve_at_landing_percent": (
                    (battery_capacity_wh - mission_energy_wh)
                    / battery_capacity_wh
                    * 100.0
                ),
                "rth_reserve_timeline": None,
            }
        )
        failure = None
        if not feasible:
            failure = EstimatorFailure(
                kind=FailureKind.INFEASIBLE,
                code=FailureCode.RESERVE_BELOW_THRESHOLD,
                message="Synthetic superlinear mass-feedback reserve failure.",
            )
        return template.model_copy(
            update={
                "status": (
                    EstimateStatus.SUCCESS if feasible else EstimateStatus.INFEASIBLE
                ),
                "energy": energy,
                "failure": failure,
            }
        )

    monkeypatch.setattr(
        "bvlos_sim.adapters.battery_sizer._estimate_at_capacity",
        fake_estimate_at_capacity,
    )

    result = compute_minimum_battery_capacity(
        mission,
        vehicle,
        tolerance_wh=0.25,
    )

    assert result.is_current_feasible is False
    assert result.minimum_capacity_wh == pytest.approx(495.0397613, abs=1e-6)
    assert result.maximum_feasible_capacity_wh == pytest.approx(
        504.9460164,
        abs=1e-6,
    )
    assert energy_margin_wh(result.minimum_capacity_wh) >= 0.0
    assert energy_margin_wh(result.minimum_capacity_wh - 0.25) < 0.0
    recommendation = battery_capacity_recommendations(
        result,
        safety_margins=[10],
    )[0]
    assert recommendation.recommended_capacity_wh is None
    assert recommendation.unavailable_reason is not None


def test_battery_sizing_rejects_non_energy_blocker() -> None:
    mission, vehicle = _pipeline_inputs()
    forbidden_zone = GeofenceZone.model_validate(
        {
            "id": "blocked-route",
            "kind": GeofenceKind.FORBIDDEN,
            "geometry": {
                "polygons": [
                    {
                        "exterior": [
                            {"lat": 52.0005, "lon": 4.0015},
                            {"lat": 52.0015, "lon": 4.0015},
                            {"lat": 52.0015, "lon": 4.0025},
                            {"lat": 52.0005, "lon": 4.0025},
                            {"lat": 52.0005, "lon": 4.0015},
                        ]
                    }
                ]
            },
        }
    )

    with pytest.raises(
        ValueError,
        match="non-energy.*ROUTE_ENTERS_FORBIDDEN_ZONE",
    ):
        compute_minimum_battery_capacity(
            mission,
            vehicle,
            geofences=[forbidden_zone],
        )


def test_battery_sizing_preserves_obstacle_blocker() -> None:
    mission, vehicle = _pipeline_inputs()
    mission = mission.model_copy(
        update={
            "constraints": mission.constraints.model_copy(
                update={"min_obstacle_clearance_m": 15.0}
            )
        }
    )
    obstacle_provider = ListObstacleProvider(
        [
            Obstacle.model_validate(
                {
                    "id": "battery-sizing-blocker",
                    "geometry": {
                        "type": "point",
                        "points": [{"lat": 52.0005, "lon": 4.001}],
                    },
                    "height_m": 200.0,
                    "radius_m": 50.0,
                }
            )
        ]
    )

    with pytest.raises(
        ValueError,
        match="non-energy.*OBSTACLE_CLEARANCE_VIOLATED",
    ):
        compute_minimum_battery_capacity(
            mission,
            vehicle,
            obstacle_provider=obstacle_provider,
        )


def test_markdown_contains_recommendation_line() -> None:
    mission, vehicle = _pipeline_inputs()
    vehicle = _vehicle_with_capacity(vehicle, 25.0)
    result = compute_minimum_battery_capacity(mission, vehicle, tolerance_wh=0.05)

    rendered = render_battery_sizing_markdown(
        result,
        mission_id=mission.mission_id,
        safety_margins=[10],
    )

    assert "Recommendation: target" in rendered
    assert "do not exceed the verified" in rendered
    assert "Status: SIZED" in rendered


def test_markdown_rejects_margin_above_feasible_interval() -> None:
    mission, vehicle = _pipeline_inputs()
    result = compute_minimum_battery_capacity(mission, vehicle)
    bounded_result = replace(
        result,
        maximum_feasible_capacity_wh=result.minimum_capacity_wh * 1.05,
    )

    rendered = render_battery_sizing_markdown(
        bounded_result,
        mission_id=mission.mission_id,
        safety_margins=[10],
    )

    assert "With 10 % safety margin:" in rendered
    assert "UNAVAILABLE" in rendered
    assert "Recommendation: none" in rendered
    assert "Recommendation: target" not in rendered


def test_markdown_shows_safety_margin_recommendations() -> None:
    mission, vehicle = _pipeline_inputs()
    vehicle = _vehicle_with_capacity(vehicle, 25.0)
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
        ["size-battery", str(SUCCESS_MISSION_PATH), str(SUCCESS_VEHICLE_PATH)],
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
    payload = json.loads(result.output)
    assert payload["schema_version"] == "battery-sizing-report.v2"
    assert (
        payload["result"]["maximum_feasible_capacity_wh"]
        >= payload["result"]["minimum_capacity_wh"]
    )
    assert (
        payload["result"]["recommendations"][0]["recommended_capacity_wh"] is not None
    )
    assert result.output == BATTERY_SIZING_GOLDEN.read_text(encoding="utf-8")


def test_size_battery_json_marks_unsafe_margin_unavailable() -> None:
    result = runner.invoke(
        app,
        [
            "size-battery",
            str(SUCCESS_MISSION_PATH),
            str(SUCCESS_VEHICLE_PATH),
            "--format",
            "json",
            "--margin",
            "3000",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    recommendation = json.loads(result.output)["result"]["recommendations"][0]
    assert recommendation["requested_capacity_wh"] > 900.0
    assert recommendation["recommended_capacity_wh"] is None
    assert "verified maximum feasible capacity" in recommendation["unavailable_reason"]
