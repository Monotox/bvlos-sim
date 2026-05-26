"""Tests for computed divert routing (Ticket 036 and Ticket 062)."""

import pytest

from estimator import DivertRouteEstimate, LandingZone
from estimator.core.enums import EnergyPowerSource, LegPhase, WarningCode
from estimator.core.results import EnergyEstimate, EnergyLegEstimate
from estimator.environment.wind import ConstantWindProvider
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
        ]
        if used_wh > 0
        else [],
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
    energy = _energy(
        battery_capacity_wh=capacity_wh, reserve_percent=25.0, used_wh=leg_wh
    )

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
    energy = _energy(
        battery_capacity_wh=capacity_wh, reserve_percent=25.0, used_wh=50.0
    )

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

    result = run_scenario(
        scenario, mission, vehicle, landing_zones=[near_zone, other_zone]
    )

    lost_link_outcome = next(
        o for o in result.event_outcomes if o.event_id == "link-lost"
    )
    assert lost_link_outcome.policy_outcome is not None
    divert = lost_link_outcome.policy_outcome.divert_estimate
    assert divert is not None
    assert divert.target_zone_id == "lz-near"
    assert divert.is_feasible is True


# ---------------------------------------------------------------------------
# Wind-corrected divert estimate tests (Ticket 062)
# ---------------------------------------------------------------------------


def test_divert_estimate_no_wind_emits_tas_only_warning() -> None:
    """Without wind_corrected=True the estimate emits DIVERT_ENERGY_TAS_ONLY."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz", lat=52.1, lon=4.0)
    energy = _energy()

    result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
    )

    assert result.is_feasible is True
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY in result.warnings


def test_divert_estimate_headwind_increases_energy() -> None:
    """A direct headwind raises energy relative to no-wind TAS estimate."""
    mission = make_mission()
    vehicle = make_vehicle()
    # Target is due north of action point; headwind = south-to-north = positive north
    zone = _point_zone("lz", lat=52.1, lon=4.0)
    energy = _energy()

    no_wind_result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        wind_east_mps=0.0,
        wind_north_mps=-5.0,  # headwind (wind from north, aircraft heading north)
        wind_corrected=True,
    )

    tas_result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        wind_corrected=False,
    )

    assert no_wind_result.energy_wh > tas_result.energy_wh
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY not in no_wind_result.warnings


def test_divert_estimate_tailwind_decreases_energy() -> None:
    """A direct tailwind lowers energy relative to no-wind TAS estimate."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz", lat=52.1, lon=4.0)
    energy = _energy()

    tailwind_result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        wind_east_mps=0.0,
        wind_north_mps=5.0,  # tailwind (wind from south, aircraft heading north)
        wind_corrected=True,
    )

    tas_result = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        wind_corrected=False,
    )

    assert tailwind_result.energy_wh < tas_result.energy_wh
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY not in tailwind_result.warnings


def test_divert_estimate_zero_wind_with_corrected_flag_matches_tas() -> None:
    """Zero wind with wind_corrected=True produces same result as TAS."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz", lat=52.1, lon=4.0)
    energy = _energy()

    corrected = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        wind_east_mps=0.0,
        wind_north_mps=0.0,
        wind_corrected=True,
    )

    uncorrected = compute_divert_estimate(
        action_lat=52.0,
        action_lon=4.0,
        action_at_timeline_index=0,
        target_zone_id="lz",
        landing_zones=[zone],
        energy=energy,
        mission=mission,
        vehicle=vehicle,
        wind_corrected=False,
    )

    assert corrected.time_s == pytest.approx(uncorrected.time_s, rel=1e-6)
    assert corrected.energy_wh == pytest.approx(uncorrected.energy_wh, rel=1e-6)
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY not in corrected.warnings
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY in uncorrected.warnings


def test_divert_estimate_wind_corrected_via_scenario_runner() -> None:
    """run_scenario applies wind correction when wind provider is available."""
    mission = make_mission()
    vehicle = make_vehicle()
    zone = _point_zone("lz-near", lat=52.001, lon=4.001)

    # Scenario without explicit initial wind: no wind provider → TAS fallback
    scenario_no_wind = ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "divert-no-wind",
            "mission_file": "mission.yaml",
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "lost_link_policy": {
                    "action": "divert",
                    "loiter_s": 0.0,
                    "divert_target_id": "lz-near",
                }
            },
            "events": [
                {"event_id": "link-lost", "kind": "lost_link", "trigger": "at_mission_start"}
            ],
            "assertions": [],
        }
    )
    # Same scenario with a constant wind provider
    wind_provider = ConstantWindProvider(0.0, 0.0)

    result_no_wind = run_scenario(scenario_no_wind, mission, vehicle, landing_zones=[zone])
    result_with_wind = run_scenario(
        scenario_no_wind, mission, vehicle, landing_zones=[zone], wind_provider=wind_provider
    )

    divert_no_wind = result_no_wind.event_outcomes[0].policy_outcome.divert_estimate
    divert_with_wind = result_with_wind.event_outcomes[0].policy_outcome.divert_estimate
    assert divert_no_wind is not None
    assert divert_with_wind is not None
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY in divert_no_wind.warnings
    assert WarningCode.DIVERT_ENERGY_TAS_ONLY not in divert_with_wind.warnings
