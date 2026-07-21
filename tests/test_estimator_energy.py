import math
from pathlib import Path

import pytest

from adapters.envelope import EnvelopeInputs, build_estimator_envelope
from adapters.io import InputDocument
from adapters.markdown import render_envelope_markdown
from estimator import (
    ConstantWindProvider,
    EnergyPowerSource,
    EstimateStatus,
    FailureCode,
    InvalidEstimatorInputError,
    LandingZone,
    LegPhase,
    WarningCode,
    WindVector,
    estimate_mission_distance_time,
    try_estimate_mission_distance_time,
)
from estimator.execution.context_builder import build_estimation_context
from estimator.execution.energy import evaluate_energy_feasibility
from estimator.execution.executors import execute_route_item
from estimator.math.atmosphere import isa_air_density_kgm3
from estimator.math.dubins import geodesic_dubins_path_to_point_m
from estimator.environment.wind import TimedWindChange, TimeVaryingWindProvider
from pyproj import Geod
from schemas import MissionAction, RouteItem, UsableCapacityPoint, VehicleProfile
from tests.helpers import make_mission, make_vehicle


def _point_zone(zone_id: str, *, lat: float, lon: float) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
            "altitude_amsl_m": 12.0,
            "geometry": {"points": [{"lat": lat, "lon": lon}]},
        }
    )


def _scaled_energy_vehicle(*, operating_mass_kg: float = 12.0) -> VehicleProfile:
    vehicle = make_vehicle()
    vehicle.mass.operating_mass_kg = operating_mass_kg
    vehicle.energy.reference_mass_kg = 10.0
    vehicle.energy.induced_power_mass_exponent = 2.0
    return vehicle


def _mission_with_intermediate_rth_breach(*, require_gate: bool = False):
    mission = make_mission()
    mission.constraints.min_landing_reserve_percent = 25.0
    mission.constraints.require_rth_reserve = require_gate
    mission.route = [
        RouteItem(
            id="far",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.05,
            altitude_m=120.0,
        ),
        RouteItem(
            id="near_far",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat + 0.001,
            lon=mission.planned_home.lon + 0.05,
            altitude_m=120.0,
        ),
    ]
    return mission


def _rth_gate_low_capacity_vehicle() -> VehicleProfile:
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 120.0
    return vehicle


def test_successful_estimate_includes_energy_breakdown_and_reserve() -> None:
    mission = make_mission()
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert len(result.energy.legs) == len(result.legs)
    assert result.energy.legs[0].power_source == EnergyPowerSource.CLIMB_POWER
    assert any(
        leg.power_source == EnergyPowerSource.HOVER_POWER
        for leg in result.energy.legs
        if leg.phase == LegPhase.LOITER_DWELL
    )
    assert math.isclose(
        result.energy.total_energy_wh,
        sum(leg.energy_wh for leg in result.energy.legs),
        rel_tol=1e-9,
    )
    assert result.energy.reserve_threshold_percent == (
        mission.constraints.min_landing_reserve_percent
    )
    assert math.isclose(
        result.energy.reserve_threshold_wh,
        vehicle.energy.battery_capacity_wh
        * result.energy.reserve_threshold_percent
        / 100.0,
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.energy.usable_energy_wh,
        vehicle.energy.battery_capacity_wh - result.energy.reserve_threshold_wh,
        rel_tol=1e-9,
    )
    assert math.isclose(
        result.energy.reserve_at_landing_wh,
        vehicle.energy.battery_capacity_wh - result.energy.total_energy_wh,
        rel_tol=1e-9,
    )


def test_energy_reserve_below_threshold_returns_complete_infeasible_result() -> None:
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 50.0

    result = try_estimate_mission_distance_time(make_mission(), vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.RESERVE_BELOW_THRESHOLD
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.energy.is_feasible is False
    assert len(result.energy.legs) == len(result.legs)
    assert result.energy.total_energy_wh <= result.energy.battery_capacity_wh
    assert result.energy.reserve_at_landing_wh < result.energy.reserve_threshold_wh


def test_vehicle_reserve_default_is_used_when_mission_has_no_override() -> None:
    mission = make_mission()
    mission.constraints.min_landing_reserve_percent = None
    vehicle = make_vehicle()
    vehicle.energy.reserve_percent_default = 30.0

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.reserve_threshold_percent == 30.0
    assert result.energy.reserve_threshold_wh == 270.0


def test_energy_capacity_exhaustion_returns_insufficient_energy() -> None:
    vehicle = make_vehicle()
    vehicle.energy.battery_capacity_wh = 30.0

    result = try_estimate_mission_distance_time(make_mission(), vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.INSUFFICIENT_ENERGY
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.energy.total_energy_wh > result.energy.battery_capacity_wh


def test_missing_hover_power_detected_before_per_leg_energy_evaluation() -> None:
    vehicle = make_vehicle()
    vehicle.energy = vehicle.energy.model_copy(update={"hover_power_w": None})

    with pytest.raises(InvalidEstimatorInputError) as exc_info:
        estimate_mission_distance_time(make_mission(), vehicle)

    error = exc_info.value
    assert error.failure.code == FailureCode.MISSING_ENERGY_MODEL
    assert "hover_power_w" in error.failure.message
    assert error.totals_are_partial is False
    assert error.energy is None
    assert len(error.partial_legs) > 0


def test_invalid_energy_policy_fails_after_kinematics_are_complete() -> None:
    mission = make_mission()
    mission.constraints.min_landing_reserve_percent = -1.0

    result = try_estimate_mission_distance_time(mission, make_vehicle())

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.INVALID_ENERGY_POLICY
    assert result.totals_are_partial is False
    assert result.energy is None
    assert len(result.legs) > 0


def test_hover_capable_vehicle_without_hover_power_fails_before_kinematics() -> None:
    vehicle = make_vehicle()
    assert vehicle.capabilities.hover is True
    vehicle.energy = vehicle.energy.model_copy(update={"hover_power_w": None})

    result = try_estimate_mission_distance_time(make_mission(), vehicle)

    assert result.status == EstimateStatus.ERROR
    assert result.failure is not None
    assert result.failure.code == FailureCode.MISSING_ENERGY_MODEL
    assert "hover_power_w" in result.failure.message


def test_rth_reserve_timeline_feasible_for_all_legs() -> None:
    result = estimate_mission_distance_time(make_mission(), make_vehicle())

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    assert len(result.energy.rth_reserve_timeline) == len(result.legs)
    assert result.rth_is_feasible is True
    assert all(point.is_feasible for point in result.energy.rth_reserve_timeline)


def test_rth_distance_uses_dubins_path_from_leg_heading() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.01,
            altitude_m=120.0,
        )
    ]

    result = estimate_mission_distance_time(mission, make_vehicle())

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    point = result.energy.rth_reserve_timeline[0]
    geod = Geod(ellps="WGS84")
    _, _, geodesic_distance_m = geod.inv(
        result.legs[0].end_lon,
        result.legs[0].end_lat,
        mission.planned_home.lon,
        mission.planned_home.lat,
    )
    expected_distance_m = geodesic_dubins_path_to_point_m(
        geod,
        start_lat=result.legs[0].end_lat,
        start_lon=result.legs[0].end_lon,
        heading_deg=result.legs[0].ground_track_deg,
        target_lat=mission.planned_home.lat,
        target_lon=mission.planned_home.lon,
        turn_radius_m=make_vehicle().performance.turn_radius_m,
    )
    assert point.rth_distance_m == pytest.approx(expected_distance_m)
    assert point.rth_distance_m > geodesic_distance_m


def test_pure_vertical_waypoint_uses_climb_power() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="vertical",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            altitude_m=220.0,
        )
    ]

    result = estimate_mission_distance_time(mission, make_vehicle())

    assert result.energy is not None
    leg = result.energy.legs[0]
    assert leg.power_source == EnergyPowerSource.CLIMB_POWER
    assert leg.power_w == pytest.approx(1500.0)
    assert leg.energy_wh == pytest.approx(30.5555555556)


def test_rtl_descent_uses_configured_descent_power() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="takeoff",
            action=MissionAction.VTOL_TAKEOFF,
            altitude_m=80.0,
        ),
        RouteItem(id="rtl", action=MissionAction.RTL),
    ]
    vehicle = make_vehicle()
    vehicle.energy.descent_power_w = 300.0

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    rtl_energy = next(
        leg for leg in result.energy.legs if leg.phase == LegPhase.RTL_TRANSIT
    )
    assert rtl_energy.power_source == EnergyPowerSource.DESCENT_POWER
    assert rtl_energy.power_w == pytest.approx(300.0)
    assert rtl_energy.energy_wh == pytest.approx(3.3333333333)


def test_rth_energy_includes_cruise_and_terminal_descent() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.01,
            altitude_m=120.0,
        )
    ]
    vehicle = make_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    point = result.energy.rth_reserve_timeline[0]
    horizontal_energy_wh = (
        vehicle.energy.cruise_power_w
        * (point.rth_distance_m / mission.defaults.cruise_speed_mps)
        / 3600.0
    )
    descent_distance_m = result.legs[0].end_alt_amsl_m - (
        mission.planned_home.altitude_amsl_m
    )
    descent_energy_wh = (
        vehicle.energy.cruise_power_w
        * (descent_distance_m / vehicle.performance.descent_rate_mps)
        / 3600.0
    )
    assert point.rth_energy_wh == pytest.approx(
        horizontal_energy_wh + descent_energy_wh
    )


def test_vertical_only_rth_still_budgets_terminal_descent_energy() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="vertical",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            altitude_m=120.0,
        )
    ]
    vehicle = make_vehicle()
    vehicle.energy.descent_power_w = 300.0

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    point = result.energy.rth_reserve_timeline[0]
    assert point.rth_distance_m == 0.0
    assert point.rth_energy_wh == pytest.approx(5.0)


def test_rth_reserve_can_fail_at_intermediate_leg_without_landing_failure() -> None:
    mission = _mission_with_intermediate_rth_breach()
    vehicle = _rth_gate_low_capacity_vehicle()

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert result.rth_is_feasible is False
    assert result.energy.rth_reserve_timeline is not None
    failed_points = [
        point for point in result.energy.rth_reserve_timeline if not point.is_feasible
    ]
    assert failed_points
    assert failed_points[0].route_item_id == "far"


def test_rth_reserve_gate_opt_out_keeps_advisory_success() -> None:
    mission = _mission_with_intermediate_rth_breach(require_gate=False)
    vehicle = _rth_gate_low_capacity_vehicle()

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.SUCCESS
    assert result.failure is None
    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert result.rth_is_feasible is False


def test_rth_reserve_gate_infeasible_uses_first_failing_leg() -> None:
    mission = _mission_with_intermediate_rth_breach(require_gate=True)
    vehicle = _rth_gate_low_capacity_vehicle()

    result = try_estimate_mission_distance_time(mission, vehicle)

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.RTH_RESERVE_BELOW_THRESHOLD
    assert result.failure.leg_index == 0
    assert result.failure.route_item_index == 0
    assert result.failure.route_item_id == "far"
    assert result.failure.context["reserve_margin_wh"] < 0.0
    assert result.failure.context["reserve_threshold_wh"] == pytest.approx(30.0)
    assert result.totals_are_partial is False
    assert result.energy is not None
    assert result.energy.is_feasible is True
    assert result.rth_is_feasible is False
    assert result.metadata["require_rth_reserve"] is True


def test_rth_reserve_gate_feasible_allows_success() -> None:
    mission = make_mission()
    mission.constraints.require_rth_reserve = True
    mission.route = [
        RouteItem(
            id="home_hold",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            altitude_m=80.0,
        )
    ]

    result = try_estimate_mission_distance_time(mission, make_vehicle())

    assert result.status == EstimateStatus.SUCCESS
    assert result.failure is None
    assert result.rth_is_feasible is True
    assert result.metadata["require_rth_reserve"] is True


def test_rth_reserve_failure_code_is_public_export() -> None:
    assert (
        FailureCode.RTH_RESERVE_BELOW_THRESHOLD.value == "RTH_RESERVE_BELOW_THRESHOLD"
    )


def test_rth_reserve_short_mission_is_feasible() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="home_hold",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            altitude_m=80.0,
        )
    ]

    result = estimate_mission_distance_time(mission, make_vehicle())

    assert result.rth_is_feasible is True
    assert result.energy is not None
    assert result.energy.rth_reserve_timeline is not None
    assert result.energy.rth_reserve_timeline[0].rth_distance_m == 0.0
    assert result.energy.rth_reserve_timeline[0].is_feasible is True


def test_rth_reserve_timeline_is_none_when_home_is_missing() -> None:
    mission = make_mission()
    context = build_estimation_context(mission, make_vehicle())
    for route_item_index, item in enumerate(context.mission.route):
        execute_route_item(context, item, route_item_index=route_item_index)
    context.mission = mission.model_copy(update={"planned_home": None})

    evaluation = evaluate_energy_feasibility(context)

    assert evaluation.failure is None
    assert evaluation.energy is not None
    assert evaluation.energy.rth_reserve_timeline is None


def test_isa_air_density_matches_reference_values() -> None:
    assert math.isclose(isa_air_density_kgm3(0.0), 1.225, rel_tol=1e-3)
    assert math.isclose(isa_air_density_kgm3(1_000.0), 1.1116, rel_tol=1e-3)
    assert math.isclose(isa_air_density_kgm3(2_000.0), 1.0065, rel_tol=1e-3)
    assert isa_air_density_kgm3(1_000.0, temperature_offset_c=15.0) < (
        isa_air_density_kgm3(1_000.0)
    )


def test_default_energy_model_omits_power_scaling_fields() -> None:
    result = estimate_mission_distance_time(make_mission(), make_vehicle())

    assert result.energy is not None
    assert all(leg.mass_multiplier is None for leg in result.energy.legs)
    assert all(leg.density_multiplier is None for leg in result.energy.legs)
    assert "mass_multiplier" not in result.energy.legs[0].model_dump(mode="json")
    assert "density_multiplier" not in result.energy.legs[0].model_dump(mode="json")


def test_operating_mass_increases_induced_leg_energy() -> None:
    base_vehicle = _scaled_energy_vehicle(operating_mass_kg=10.0)
    heavy_vehicle = _scaled_energy_vehicle(operating_mass_kg=12.0)

    base = estimate_mission_distance_time(make_mission(), base_vehicle)
    heavy = estimate_mission_distance_time(make_mission(), heavy_vehicle)

    assert base.energy is not None
    assert heavy.energy is not None
    base_takeoff = base.energy.legs[0]
    heavy_takeoff = heavy.energy.legs[0]
    assert base_takeoff.power_source == EnergyPowerSource.CLIMB_POWER
    assert heavy_takeoff.mass_multiplier == pytest.approx(1.44)
    assert heavy_takeoff.energy_wh > base_takeoff.energy_wh


def test_lower_air_density_increases_power_at_altitude() -> None:
    low_mission = make_mission()
    high_mission = make_mission()
    high_mission.planned_home.altitude_amsl_m = 2_000.0
    vehicle = make_vehicle()
    vehicle.energy.reference_density_kgm3 = isa_air_density_kgm3(0.0)

    low = estimate_mission_distance_time(low_mission, vehicle)
    high = estimate_mission_distance_time(high_mission, vehicle)

    assert low.energy is not None
    assert high.energy is not None
    assert high.energy.total_energy_wh > low.energy.total_energy_wh
    assert high.energy.legs[0].density_multiplier is not None
    assert high.energy.legs[0].density_multiplier > 1.0


def test_usable_capacity_curve_derates_usable_energy_not_reserve_threshold() -> None:
    mission = make_mission()
    vehicle = make_vehicle()
    vehicle.energy.usable_capacity_curve = [
        UsableCapacityPoint(soc=0.0, usable_fraction=0.0),
        UsableCapacityPoint(soc=1.0, usable_fraction=0.8),
    ]

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    assert result.energy.reserve_threshold_wh == pytest.approx(225.0)
    assert result.energy.usable_energy_wh == pytest.approx(495.0)


def test_missing_energy_reference_conditions_warns() -> None:
    vehicle = make_vehicle()
    vehicle.mass.operating_mass_kg = 11.0

    result = estimate_mission_distance_time(make_mission(), vehicle)

    assert any(
        warning.code == WarningCode.ENERGY_REFERENCE_CONDITIONS_MISSING
        for warning in result.warnings
    )


def test_rth_energy_uses_adjusted_cruise_power() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.01,
            altitude_m=120.0,
        )
    ]

    base = estimate_mission_distance_time(mission, make_vehicle())
    scaled = estimate_mission_distance_time(mission, _scaled_energy_vehicle())

    assert base.energy is not None
    assert scaled.energy is not None
    assert base.energy.rth_reserve_timeline is not None
    assert scaled.energy.rth_reserve_timeline is not None
    assert (
        scaled.energy.rth_reserve_timeline[0].rth_energy_wh
        > base.energy.rth_reserve_timeline[0].rth_energy_wh
    )


def test_landing_zone_divert_energy_uses_adjusted_cruise_power() -> None:
    mission = make_mission()
    mission.route = [mission.route[0]]
    mission.constraints.min_distance_to_landing_zone_m = 10_000.0
    zone = _point_zone("distant_lz", lat=52.045, lon=4.0)

    base = estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
    )
    scaled = estimate_mission_distance_time(
        mission,
        _scaled_energy_vehicle(),
        landing_zones=[zone],
    )

    assert base.landing_zone is not None
    assert scaled.landing_zone is not None
    assert base.landing_zone.states[0].divert_energy_wh is not None
    assert scaled.landing_zone.states[0].divert_energy_wh is not None
    assert (
        scaled.landing_zone.states[0].divert_energy_wh
        > base.landing_zone.states[0].divert_energy_wh
    )


def test_markdown_report_includes_energy_power_factors() -> None:
    result = estimate_mission_distance_time(
        make_mission(),
        _scaled_energy_vehicle(),
    )
    fake_doc = InputDocument(
        path=Path("/fake/input.yaml"), format="yaml", sha256="0" * 64
    )
    envelope = build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(mission=fake_doc, vehicle=fake_doc),
    )

    output = render_envelope_markdown(envelope)

    assert "| Leg | ID | Mass factor | Density factor |" in output


def test_induced_phase_density_scaling_uses_inverse_square_root() -> None:
    mission = make_mission()
    mission.route = [
        RouteItem(
            id="vertical",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon,
            altitude_m=220.0,
        )
    ]
    vehicle = make_vehicle()
    midpoint_altitude_m = mission.planned_home.altitude_amsl_m + 110.0
    vehicle.energy.reference_density_kgm3 = 2.0 * isa_air_density_kgm3(
        midpoint_altitude_m
    )

    result = estimate_mission_distance_time(mission, vehicle)

    assert result.energy is not None
    climb = result.energy.legs[0]
    assert climb.power_source == EnergyPowerSource.CLIMB_POWER
    assert climb.density_multiplier == pytest.approx(math.sqrt(2.0))


def _single_eastbound_waypoint_mission():
    mission = make_mission()
    mission.constraints.max_wind_mps = None
    mission.constraints.require_rth_reserve = False
    mission.route = [
        RouteItem(
            id="east",
            action=MissionAction.WAYPOINT,
            lat=mission.planned_home.lat,
            lon=mission.planned_home.lon + 0.01,
            altitude_m=120.0,
        )
    ]
    return mission


class _NorthernWindProvider:
    def wind_at(
        self,
        *,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        del lon, altitude_amsl_m, elapsed_time_s
        # Keep the nearly constant-latitude outbound route calm while loading
        # the materially north-going initial RTH turn.
        return WindVector(
            wind_east_mps=0.0,
            wind_north_mps=12.0 if lat > 52.00001 else 0.0,
        )


def test_rth_energy_integrates_headwind_along_dubins_return_path() -> None:
    mission = _single_eastbound_waypoint_mission()
    calm_vehicle = make_vehicle()
    windy_vehicle = make_vehicle()
    calm_vehicle.performance.max_crab_angle_deg = 89.0
    windy_vehicle.performance.max_crab_angle_deg = 89.0
    calm = estimate_mission_distance_time(
        mission,
        calm_vehicle,
        wind_provider=ConstantWindProvider(0.0, 0.0),
    )
    windy = estimate_mission_distance_time(
        mission,
        windy_vehicle,
        wind_provider=ConstantWindProvider(15.0, 0.0),
    )

    assert calm.energy is not None and calm.energy.rth_reserve_timeline is not None
    assert windy.energy is not None and windy.energy.rth_reserve_timeline is not None
    calm_rth = calm.energy.rth_reserve_timeline[0]
    windy_rth = windy.energy.rth_reserve_timeline[0]
    assert windy_rth.rth_distance_m == pytest.approx(calm_rth.rth_distance_m)
    descent_energy_wh = (
        calm_vehicle.energy.cruise_power_w
        * (
            (calm.legs[0].end_alt_amsl_m - mission.planned_home.altitude_amsl_m)
            / calm_vehicle.performance.descent_rate_mps
        )
        / 3600.0
    )
    assert (
        windy_rth.rth_energy_wh - descent_energy_wh
        > (calm_rth.rth_energy_wh - descent_energy_wh) * 4.5
    )


def test_rth_integrates_time_varying_wind_change_during_return() -> None:
    mission = _single_eastbound_waypoint_mission()
    vehicle = make_vehicle()
    vehicle.performance.turn_radius_m = None
    vehicle.performance.max_crab_angle_deg = 89.0
    calm = estimate_mission_distance_time(
        mission,
        vehicle,
        wind_provider=ConstantWindProvider(0.0, 0.0),
    )
    change_time_s = calm.legs[0].time_s + 5.0
    provider = TimeVaryingWindProvider(
        ConstantWindProvider(0.0, 0.0),
        [
            TimedWindChange(
                effective_elapsed_time_s=change_time_s,
                provider=ConstantWindProvider(15.0, 0.0),
            )
        ],
    )

    changed = estimate_mission_distance_time(
        mission,
        vehicle,
        wind_provider=provider,
    )

    assert calm.energy is not None and calm.energy.rth_reserve_timeline is not None
    assert (
        changed.energy is not None and changed.energy.rth_reserve_timeline is not None
    )
    assert (
        changed.energy.rth_reserve_timeline[0].rth_energy_wh
        > calm.energy.rth_reserve_timeline[0].rth_energy_wh * 2.0
    )


def test_rth_fails_closed_when_headwind_makes_return_segment_impossible() -> None:
    vehicle = make_vehicle()
    vehicle.performance.max_crab_angle_deg = 89.0
    result = try_estimate_mission_distance_time(
        _single_eastbound_waypoint_mission(),
        vehicle,
        wind_provider=ConstantWindProvider(18.0, 0.0),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code in {
        FailureCode.GROUNDSPEED_NON_POSITIVE,
        FailureCode.GROUNDSPEED_BELOW_MIN,
    }
    assert result.failure.context["segment_index"] > 0


def test_rth_checks_crosswind_on_initial_dubins_turn() -> None:
    mission = _single_eastbound_waypoint_mission()
    vehicle = make_vehicle()
    vehicle.performance.max_crab_angle_deg = 20.0

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        wind_provider=_NorthernWindProvider(),
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.CRAB_ANGLE_LIMIT_EXCEEDED
    assert result.failure.context["segment_index"] == 0
