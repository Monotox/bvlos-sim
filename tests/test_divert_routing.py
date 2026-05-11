"""Tests for computed divert routing (Ticket 036)."""

import pytest

from estimator import DivertRouteEstimate, LandingZone
from estimator.core.enums import EnergyPowerSource, LegPhase
from estimator.core.results import EnergyEstimate, EnergyLegEstimate
from estimator.execution.divert import compute_divert_estimate
from estimator.execution.scenario import run_scenario
from schemas.scenario import ScenarioPlan
from tests.helpers import make_mission, make_vehicle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point_zone(zone_id: str, *, lat: float, lon: float) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
            "geometry": {"points": [{"lat": lat, "lon": lon}]},
        }
    )


def _energy(
    *,
    battery_capacity_wh: float = 900.0,
    reserve_percent: float = 25.0,
    used_wh: float = 0.0,
) -> EnergyEstimate:
    reserve_threshold_wh = battery_capacity_wh * reserve_percent / 100.0
    remaining_wh = battery_capacity_wh - used_wh
    return EnergyEstimate(
        is_feasible=remaining_wh >= reserve_threshold_wh,
        total_energy_wh=used_wh,
        battery_capacity_wh=battery_capacity_wh,
        usable_energy_wh=battery_capacity_wh - reserve_threshold_wh,
        reserve_threshold_percent=reserve_percent,
        reserve_threshold_wh=reserve_threshold_wh,
        reserve_at_landing_wh=remaining_wh,
        reserve_at_landing_percent=remaining_wh / battery_capacity_wh * 100.0,
        legs=[
            EnergyLegEstimate(
                leg_index=0,
                route_item_index=0,
                route_item_id="takeoff",
                phase=LegPhase.VERTICAL_TAKEOFF,
                time_s=16.0,
                power_w=1200.0,
                power_source=EnergyPowerSource.HOVER_POWER,
                energy_wh=used_wh,
            )
        ] if used_wh > 0 else [],
    )


def _divert_scenario(
    *,
    divert_target_id: str = "lz-near",
    loiter_s: float = 0.0,
    lost_link_trigger: str = "at_mission_start",
) -> ScenarioPlan:
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "divert-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                "lost_link_policy": {
                    "action": "divert",
                    "loiter_s": loiter_s,
                    "divert_target_id": divert_target_id,
                },
            },
            "events": [
                {
                    "event_id": "link-lost",
                    "kind": "lost_link",
                    "trigger": lost_link_trigger,
                }
            ],
            "assertions": [],
        }
    )


def _rtl_scenario() -> ScenarioPlan:
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "rtl-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                "lost_link_policy": {
                    "action": "rtl",
                    "loiter_s": 0.0,
                },
            },
            "events": [
                {
                    "event_id": "link-lost",
                    "kind": "lost_link",
                    "trigger": "at_mission_start",
                }
            ],
            "assertions": [],
        }
    )


# ---------------------------------------------------------------------------
# Unit tests — compute_divert_estimate directly
# ---------------------------------------------------------------------------


def test_divert_estimate_feasible_near_zone() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    energy = _energy(battery_capacity_wh=900.0, reserve_percent=25.0, used_wh=0.0)

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert isinstance(result, DivertRouteEstimate)
    assert result.target_zone_id == "lz-near"
    assert result.distance_m > 0.0
    assert result.time_s > 0.0
    assert result.energy_wh > 0.0
    assert result.energy_remaining_at_action_wh == pytest.approx(900.0)
    assert result.reserve_threshold_wh == pytest.approx(225.0)
    assert result.reserve_after_divert_wh == pytest.approx(900.0 - result.energy_wh)
    assert result.is_feasible is True
    assert result.infeasible_reason is None


def test_divert_estimate_infeasible_insufficient_reserve() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-far", lat=52.001, lon=4.001)
    energy = _energy(battery_capacity_wh=900.0, reserve_percent=25.0, used_wh=675.5)

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=1,
        target_zone_id="lz-far",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.is_feasible is False
    assert result.infeasible_reason is not None
    assert result.reserve_after_divert_wh < result.reserve_threshold_wh


def test_divert_estimate_no_energy_returns_infeasible() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=None,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.is_feasible is False
    assert result.infeasible_reason is not None
    assert "energy" in result.infeasible_reason.lower()
    assert result.distance_m == 0.0
    assert result.time_s == 0.0


def test_divert_estimate_target_zone_not_found() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-other", lat=52.001, lon=4.001)
    energy = _energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-missing",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.target_zone_id == "lz-missing"
    assert result.is_feasible is False
    assert result.infeasible_reason is not None
    assert "lz-missing" in result.infeasible_reason


def test_divert_estimate_action_at_index_uses_legs_up_to_that_point() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    capacity_wh = 900.0
    leg_wh = 100.0
    energy = _energy(battery_capacity_wh=capacity_wh, reserve_percent=25.0, used_wh=leg_wh)

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=1,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.energy_remaining_at_action_wh == pytest.approx(capacity_wh - leg_wh)


def test_divert_estimate_at_index_zero_uses_full_battery() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    capacity_wh = 900.0
    energy = _energy(battery_capacity_wh=capacity_wh, reserve_percent=25.0, used_wh=50.0)

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.energy_remaining_at_action_wh == pytest.approx(capacity_wh)


def test_divert_estimate_uses_mission_cruise_speed_over_vehicle() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    energy = _energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-near",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    expected_time_s = result.distance_m / mission.defaults.cruise_speed_mps
    assert result.time_s == pytest.approx(expected_time_s, rel=1e-6)


def test_divert_estimate_distance_is_zero_when_inside_zone() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    zone = LandingZone.model_validate(
        {
            "id": "lz-polygon",
            "geometry": {
                "polygons": [
                    {
                        "exterior": [
                            {"lat": 52.0 - 0.01, "lon": 4.0 - 0.01},
                            {"lat": 52.0 - 0.01, "lon": 4.0 + 0.01},
                            {"lat": 52.0 + 0.01, "lon": 4.0 + 0.01},
                            {"lat": 52.0 + 0.01, "lon": 4.0 - 0.01},
                            {"lat": 52.0 - 0.01, "lon": 4.0 - 0.01},
                        ]
                    }
                ]
            },
        }
    )
    energy = _energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz-polygon",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.distance_m == pytest.approx(0.0)
    assert result.time_s == pytest.approx(0.0)
    assert result.energy_wh == pytest.approx(0.0)
    assert result.is_feasible is True


# ---------------------------------------------------------------------------
# Integration tests — run_scenario
# ---------------------------------------------------------------------------


def test_divert_estimate_populated_on_divert_policy_outcome() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _divert_scenario(divert_target_id="lz-near")
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])

    outcome = result.event_outcomes[0]
    assert outcome.policy_outcome is not None
    assert outcome.policy_outcome.divert_estimate is not None
    divert = outcome.policy_outcome.divert_estimate
    assert divert.target_zone_id == "lz-near"
    assert divert.distance_m > 0.0
    assert divert.is_feasible is True


def test_divert_estimate_none_when_no_landing_zones() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _divert_scenario(divert_target_id="lz-near")

    result = run_scenario(scenario, mission, vehicle, landing_zones=None)

    outcome = result.event_outcomes[0]
    assert outcome.policy_outcome is not None
    assert outcome.policy_outcome.divert_estimate is None


def test_divert_estimate_none_when_landing_zones_empty() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _divert_scenario(divert_target_id="lz-near")

    result = run_scenario(scenario, mission, vehicle, landing_zones=[])

    outcome = result.event_outcomes[0]
    assert outcome.policy_outcome is not None
    assert outcome.policy_outcome.divert_estimate is None


def test_non_divert_action_has_no_divert_estimate() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _rtl_scenario()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])

    outcome = result.event_outcomes[0]
    assert outcome.policy_outcome is not None
    assert outcome.policy_outcome.action == "rtl"
    assert outcome.policy_outcome.divert_estimate is None


def test_divert_estimate_infeasible_when_target_not_in_landing_zones() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _divert_scenario(divert_target_id="lz-missing")
    zone = _point_zone("lz-other", lat=52.001, lon=4.001)

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])

    outcome = result.event_outcomes[0]
    assert outcome.policy_outcome is not None
    divert = outcome.policy_outcome.divert_estimate
    assert divert is not None
    assert divert.is_feasible is False
    assert "lz-missing" in (divert.infeasible_reason or "")


def test_divert_estimate_target_id_on_policy_outcome() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _divert_scenario(divert_target_id="lz-near")
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])

    outcome = result.event_outcomes[0]
    assert outcome.policy_outcome is not None
    assert outcome.policy_outcome.divert_target_id == "lz-near"


def test_divert_estimate_reserve_after_divert_percent_sums_correctly() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = _divert_scenario(divert_target_id="lz-near")
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    result = run_scenario(scenario, mission, vehicle, landing_zones=[zone])

    divert = result.event_outcomes[0].policy_outcome.divert_estimate
    assert divert is not None
    expected_pct = divert.reserve_after_divert_wh / 900.0 * 100.0
    assert divert.reserve_after_divert_percent == pytest.approx(expected_pct, rel=1e-6)


def test_divert_estimate_combined_with_lz_unavailability_events() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    scenario = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "divert-lz-combined-test",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
                "lost_link_policy": {
                    "action": "divert",
                    "loiter_s": 0.0,
                    "divert_target_id": "lz-near",
                },
            },
            "events": [
                {
                    "event_id": "link-lost",
                    "kind": "lost_link",
                    "trigger": "at_mission_start",
                },
                {
                    "event_id": "lz-mark-unavail",
                    "kind": "landing_zone_unavailable",
                    "trigger": "at_mission_end",
                    "unavailable_zone_ids": ["lz-other"],
                },
            ],
            "assertions": [],
        }
    )
    near_zone = _point_zone("lz-near", lat=52.001, lon=4.001)
    other_zone = _point_zone("lz-other", lat=52.002, lon=4.002)

    result = run_scenario(scenario, mission, vehicle, landing_zones=[near_zone, other_zone])

    lost_link_outcome = next(
        o for o in result.event_outcomes if o.event_id == "link-lost"
    )
    assert lost_link_outcome.policy_outcome is not None
    divert = lost_link_outcome.policy_outcome.divert_estimate
    assert divert is not None
    assert divert.target_zone_id == "lz-near"
    assert divert.is_feasible is True
