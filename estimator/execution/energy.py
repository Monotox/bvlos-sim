"""Deterministic mission energy feasibility evaluation."""

from collections.abc import Callable
from dataclasses import dataclass
import math

from estimator.core.enums import (
    EnergyPowerSource,
    FailureCode,
    FailureKind,
    LegPhase,
    WarningCode,
)
from estimator.core.results import (
    EnergyEstimate,
    EnergyLegEstimate,
    EstimatorContextValue,
    EstimatorFailure,
    EstimatorWarning,
    LegEstimate,
    RthReserveTimelinePoint,
)
from estimator.environment.wind import TimeVaryingWindProvider, WindProvider
from estimator.execution.runtime import EstimationContext
from estimator.math.atmosphere import isa_air_density_kgm3
from estimator.math.dubins import (
    DubinsPathSegment,
    dubins_path_to_point,
    sample_dubins_path,
)
from estimator.math.wind_triangle import solve_wind_triangle
from schemas.vehicle import VehicleProfile
from schemas.vehicle_energy import EnergyModel

SECONDS_PER_HOUR = 3600.0

_TRANSIT_POWER_PHASES = frozenset(
    {
        LegPhase.TRANSIT,
        LegPhase.TURN_ARC,
        LegPhase.LOITER_TRANSIT,
        LegPhase.RTL_TRANSIT,
    }
)
_INDUCED_POWER_SOURCES = frozenset(
    {
        EnergyPowerSource.HOVER_POWER,
        EnergyPowerSource.CLIMB_POWER,
        EnergyPowerSource.DESCENT_POWER,
    }
)
_CRUISE_MASS_EXPONENT = 0.5
# Upper bound on emergency/RTH path sample spacing, independent of the transit
# sampling option so a coarse transit setting cannot coarsen contingency energy.
_EMERGENCY_SAMPLE_LENGTH_M = 100.0


@dataclass(frozen=True)
class EnergyPower:
    power_w: float
    source: EnergyPowerSource
    mass_multiplier: float | None = None
    density_multiplier: float | None = None


@dataclass(frozen=True)
class EnergyEvaluation:
    energy: EnergyEstimate | None
    failure: EstimatorFailure | None


@dataclass(frozen=True)
class EmergencyPathEstimate:
    distance_m: float
    horizontal_time_s: float
    vertical_time_s: float
    horizontal_energy_wh: float
    vertical_energy_wh: float

    @property
    def total_energy_wh(self) -> float:
        return self.horizontal_energy_wh + self.vertical_energy_wh


def evaluate_energy_feasibility(
    context: EstimationContext,
    *,
    enforce_battery_capacity: bool = True,
    enforce_rth_reserve: bool = True,
) -> EnergyEvaluation:
    """Evaluate energy after kinematic route expansion is complete."""

    energy_model = context.vehicle.energy
    if energy_model is None:
        return EnergyEvaluation(
            energy=None,
            failure=_mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.MISSING_ENERGY_MODEL,
                message="vehicle.energy is required for deterministic energy feasibility.",
                context={},
            ),
        )

    model_failure = _validate_energy_model(energy_model)
    if model_failure is not None:
        return EnergyEvaluation(energy=None, failure=model_failure)

    if context.capabilities.hover and energy_model.hover_power_w is None:
        return EnergyEvaluation(
            energy=None,
            failure=_mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.MISSING_ENERGY_MODEL,
                message="vehicle.energy.hover_power_w is required for hover-capable vehicles.",
                context={"energy_field": "vehicle.energy.hover_power_w"},
            ),
        )

    threshold_percent, threshold_failure = _resolve_reserve_threshold_percent(context)
    if threshold_failure is not None:
        return EnergyEvaluation(energy=None, failure=threshold_failure)
    _warn_for_missing_energy_references(context, energy_model)

    hover_capable = context.capabilities.hover
    energy_legs: list[EnergyLegEstimate] = []
    for leg in context.route_legs:
        power, failure = _resolve_leg_energy(
            context, energy_model, leg, hover_capable=hover_capable
        )
        if failure is not None:
            return EnergyEvaluation(energy=None, failure=failure)

        energy_legs.append(
            EnergyLegEstimate(
                leg_index=leg.leg_index,
                route_item_index=leg.route_item_index,
                route_item_id=leg.route_item_id,
                phase=leg.phase,
                time_s=leg.time_s,
                power_w=power.power_w,
                power_source=power.source,
                energy_wh=power.power_w * leg.time_s / SECONDS_PER_HOUR,
                mass_multiplier=power.mass_multiplier,
                density_multiplier=power.density_multiplier,
            )
        )

    energy, energy_failure = _build_energy_estimate(
        context=context,
        energy_model=energy_model,
        threshold_percent=threshold_percent,
        legs=energy_legs,
    )
    if energy_failure is not None:
        return EnergyEvaluation(energy=None, failure=energy_failure)
    if energy is None:
        raise ValueError("Energy estimate construction failed without a failure.")
    failure = _build_feasibility_failure(energy) if enforce_battery_capacity else None
    if failure is None and enforce_rth_reserve:
        failure = _build_rth_reserve_failure(context, energy)
    return EnergyEvaluation(energy=energy, failure=failure)


def _validate_energy_model(energy_model: EnergyModel) -> EstimatorFailure | None:
    checks: tuple[tuple[float | None, str], ...] = (
        (
            energy_model.battery_capacity_wh,
            "battery_capacity_wh",
        ),
        (energy_model.cruise_power_w, "cruise_power_w"),
    )
    for value, field_name in checks:
        if value is None:
            return _mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.MISSING_ENERGY_MODEL,
                message=f"vehicle.energy.{field_name} is required.",
                context={"energy_field": f"vehicle.energy.{field_name}"},
            )
        if value <= 0:
            return _mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_ENERGY_MODEL,
                message=f"vehicle.energy.{field_name} must be greater than zero.",
                context={
                    "energy_field": f"vehicle.energy.{field_name}",
                    "value": value,
                },
            )

    return None


def _warn_for_missing_energy_references(
    context: EstimationContext,
    energy_model: EnergyModel,
) -> None:
    missing: list[str] = []
    if context.vehicle.mass.operating_mass_kg is None:
        return
    if energy_model.reference_mass_kg is None:
        missing.append("vehicle.energy.reference_mass_kg")
    if energy_model.reference_density_kgm3 is None:
        missing.append("vehicle.energy.reference_density_kgm3")
    if not missing:
        return

    context.warnings.append(
        EstimatorWarning(
            code=WarningCode.ENERGY_REFERENCE_CONDITIONS_MISSING,
            message=(
                "vehicle.mass.operating_mass_kg is configured but "
                f"{', '.join(missing)} is missing; energy scaling falls back to "
                "unadjusted phase power where reference data is unavailable."
            ),
            leg_index=None,
            route_item_index=None,
            route_item_id=None,
        )
    )


def _resolve_reserve_threshold_percent(
    context: EstimationContext,
) -> tuple[float, EstimatorFailure | None]:
    mission_threshold = context.mission.constraints.min_landing_reserve_percent
    if mission_threshold is not None:
        return _validate_reserve_threshold_percent(
            mission_threshold,
            field_name="mission.constraints.min_landing_reserve_percent",
        )

    reserve_default = context.vehicle.energy.reserve_percent_default
    if reserve_default is None:
        return (
            0.0,
            _mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.MISSING_ENERGY_MODEL,
                message="vehicle.energy.reserve_percent_default is required.",
                context={"energy_field": "vehicle.energy.reserve_percent_default"},
            ),
        )

    return _validate_reserve_threshold_percent(
        reserve_default,
        field_name="vehicle.energy.reserve_percent_default",
    )


def _validate_reserve_threshold_percent(
    value: float,
    *,
    field_name: str,
) -> tuple[float, EstimatorFailure | None]:
    if 0 <= value <= 100:
        return value, None

    return (
        value,
        _mission_energy_failure(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_ENERGY_POLICY,
            message=f"{field_name} must be between 0 and 100.",
            context={"reserve_threshold_percent": value},
        ),
    )


LegPowerResolver = Callable[
    [EnergyModel, LegEstimate], tuple[EnergyPower, EstimatorFailure | None]
]


def _resolve_vertical_takeoff_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    power_w = energy_model.climb_power_w
    if power_w is not None:
        return _validate_leg_power(power_w, EnergyPowerSource.CLIMB_POWER, leg)
    return _resolve_cruise_power(energy_model, leg)


def _resolve_climb_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    power_w = energy_model.climb_power_w
    if power_w is not None:
        return _validate_leg_power(power_w, EnergyPowerSource.CLIMB_POWER, leg)
    return _resolve_cruise_power(energy_model, leg)


def _resolve_descent_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    power_w = energy_model.descent_power_w
    if power_w is not None:
        return _validate_leg_power(power_w, EnergyPowerSource.DESCENT_POWER, leg)
    return _resolve_cruise_power(energy_model, leg)


def _resolve_hover_loiter_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    return _require_leg_power(
        energy_model.hover_power_w, EnergyPowerSource.HOVER_POWER, leg
    )


def _resolve_fixed_wing_loiter_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    return _resolve_cruise_power(energy_model, leg)


def _resolve_landing_transit_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    if leg.vertical_delta_m < 0:
        return _resolve_descent_power(energy_model, leg)
    return _resolve_cruise_power(energy_model, leg)


def _resolve_cruise_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    return _validate_leg_power(
        energy_model.cruise_power_w,
        EnergyPowerSource.CRUISE_POWER,
        leg,
    )


_CRUISE_POWER_RESOLVERS: dict[LegPhase, LegPowerResolver] = {
    phase: _resolve_cruise_power for phase in _TRANSIT_POWER_PHASES
}
_HOVER_LOITER_POWER_RESOLVERS: dict[bool, LegPowerResolver] = {
    True: _resolve_hover_loiter_power,
    False: _resolve_fixed_wing_loiter_power,
}
_LEG_POWER_RESOLVERS: dict[LegPhase, LegPowerResolver] = {
    **_CRUISE_POWER_RESOLVERS,
    LegPhase.VERTICAL_TAKEOFF: _resolve_vertical_takeoff_power,
    LegPhase.LANDING_TRANSIT: _resolve_landing_transit_power,
}


def _resolve_leg_power(
    energy_model: EnergyModel,
    leg: LegEstimate,
    *,
    hover_capable: bool,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    if leg.phase == LegPhase.LOITER_DWELL:
        return _HOVER_LOITER_POWER_RESOLVERS[hover_capable](energy_model, leg)

    # Resolve the power of the leg's vertical work. Route actions may combine
    # horizontal and vertical motion in one leg; _resolve_leg_energy costs the
    # two portions separately, so this covers only the climb/descent share.
    if leg.vertical_delta_m > 0.0:
        return _resolve_climb_power(energy_model, leg)
    if leg.vertical_delta_m < 0.0:
        return _resolve_descent_power(energy_model, leg)

    resolver = _LEG_POWER_RESOLVERS.get(leg.phase)
    if resolver is not None:
        return resolver(energy_model, leg)

    return _unsupported_phase_energy_failure(leg)


def _resolve_leg_energy(
    context: EstimationContext,
    energy_model: EnergyModel,
    leg: LegEstimate,
    *,
    hover_capable: bool,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    """Resolve a leg's time-averaged power, splitting mixed legs by phase.

    A route action may climb or descend while also covering ground. Charging
    the whole leg at the vertical power understates energy whenever descent
    power is below cruise, so that supplying descent_power_w could *raise*
    reported endurance. The vertical and horizontal portions are therefore
    costed separately, each adjusted for its own reference conditions, and
    recombined into the effective power that the leg's duration implies.
    """

    vertical_base, failure = _resolve_leg_power(
        energy_model, leg, hover_capable=hover_capable
    )
    if failure is not None:
        return vertical_base, failure
    vertical_power = _apply_energy_fidelity(context, leg, vertical_base)

    if (
        leg.phase == LegPhase.LOITER_DWELL
        or leg.vertical_delta_m == 0.0
        or leg.horizontal_distance_m <= 0.0
        or leg.time_s <= 0.0
    ):
        return vertical_power, None

    cruise_base, cruise_failure = _resolve_cruise_power(energy_model, leg)
    if cruise_failure is not None:
        return vertical_power, cruise_failure
    cruise_power = _apply_energy_fidelity(context, leg, cruise_base)

    profile = leg.timing_profile
    if profile is None:
        # Phase durations are unknown without the estimator's timing split.
        # Never understate: charge the whole leg at the costlier phase power.
        return (
            max(vertical_power, cruise_power, key=lambda power: power.power_w),
            None,
        )

    vertical_time_s = min(max(profile.vertical_time_s, 0.0), leg.time_s)
    horizontal_time_s = leg.time_s - vertical_time_s
    if horizontal_time_s <= 0.0:
        return vertical_power, None
    if vertical_time_s <= 0.0:
        return cruise_power, None

    effective_power_w = (
        vertical_power.power_w * vertical_time_s
        + cruise_power.power_w * horizontal_time_s
    ) / leg.time_s
    return (
        EnergyPower(
            power_w=effective_power_w,
            source=vertical_power.source,
            mass_multiplier=_blend_leg_multiplier(
                vertical_power.mass_multiplier,
                cruise_power.mass_multiplier,
                vertical_time_s=vertical_time_s,
                horizontal_time_s=horizontal_time_s,
            ),
            density_multiplier=_blend_leg_multiplier(
                vertical_power.density_multiplier,
                cruise_power.density_multiplier,
                vertical_time_s=vertical_time_s,
                horizontal_time_s=horizontal_time_s,
            ),
        ),
        None,
    )


def _blend_leg_multiplier(
    vertical_multiplier: float | None,
    cruise_multiplier: float | None,
    *,
    vertical_time_s: float,
    horizontal_time_s: float,
) -> float | None:
    """Time-weight the two phases' reference-condition factors.

    Reported for diagnostics only; the effective power is already blended.
    """

    if vertical_multiplier is None and cruise_multiplier is None:
        return None
    total_time_s = vertical_time_s + horizontal_time_s
    if total_time_s <= 0.0:
        if vertical_multiplier is not None:
            return vertical_multiplier
        return cruise_multiplier
    applied_vertical = 1.0 if vertical_multiplier is None else vertical_multiplier
    applied_cruise = 1.0 if cruise_multiplier is None else cruise_multiplier
    return (
        applied_vertical * vertical_time_s + applied_cruise * horizontal_time_s
    ) / total_time_s


def _apply_energy_fidelity(
    context: EstimationContext,
    leg: LegEstimate,
    power: EnergyPower,
) -> EnergyPower:
    return _adjust_power_for_reference_conditions(
        vehicle=context.vehicle,
        source=power.source,
        base_power_w=power.power_w,
        altitude_amsl_m=(leg.start_alt_amsl_m + leg.end_alt_amsl_m) * 0.5,
    )


def adjusted_cruise_power_w(
    context: EstimationContext,
    *,
    altitude_amsl_m: float,
) -> float:
    return adjusted_cruise_power_for_vehicle(
        context.vehicle,
        altitude_amsl_m=altitude_amsl_m,
    )


def adjusted_cruise_power_for_vehicle(
    vehicle: VehicleProfile,
    *,
    altitude_amsl_m: float,
) -> float:
    return _adjust_power_for_reference_conditions(
        vehicle=vehicle,
        source=EnergyPowerSource.CRUISE_POWER,
        base_power_w=vehicle.energy.cruise_power_w,
        altitude_amsl_m=altitude_amsl_m,
    ).power_w


def _adjust_power_for_reference_conditions(
    *,
    vehicle: VehicleProfile,
    source: EnergyPowerSource,
    base_power_w: float,
    altitude_amsl_m: float,
) -> EnergyPower:
    mass_multiplier = _mass_power_multiplier(vehicle, source)
    density_multiplier = _density_power_multiplier(
        vehicle,
        source,
        altitude_amsl_m,
    )
    if mass_multiplier is None and density_multiplier is None:
        return EnergyPower(power_w=base_power_w, source=source)

    applied_mass_multiplier = 1.0 if mass_multiplier is None else mass_multiplier
    applied_density_multiplier = (
        1.0 if density_multiplier is None else density_multiplier
    )
    return EnergyPower(
        power_w=base_power_w * applied_mass_multiplier * applied_density_multiplier,
        source=source,
        mass_multiplier=applied_mass_multiplier,
        density_multiplier=applied_density_multiplier,
    )


def _mass_power_multiplier(
    vehicle: VehicleProfile,
    source: EnergyPowerSource,
) -> float | None:
    operating_mass_kg = vehicle.mass.operating_mass_kg
    reference_mass_kg = vehicle.energy.reference_mass_kg
    if operating_mass_kg is None or reference_mass_kg is None:
        return None

    exponent = (
        vehicle.energy.induced_power_mass_exponent
        if source in _INDUCED_POWER_SOURCES
        else _CRUISE_MASS_EXPONENT
    )
    return (operating_mass_kg / reference_mass_kg) ** exponent


def _density_power_multiplier(
    vehicle: VehicleProfile,
    source: EnergyPowerSource,
    altitude_amsl_m: float,
) -> float | None:
    reference_density_kgm3 = vehicle.energy.reference_density_kgm3
    if reference_density_kgm3 is None:
        return None

    actual_density_kgm3 = isa_air_density_kgm3(altitude_amsl_m)
    density_ratio = reference_density_kgm3 / actual_density_kgm3
    if source in _INDUCED_POWER_SOURCES:
        # Momentum theory: induced rotor power varies with 1/sqrt(rho).
        return density_ratio**0.5
    # The single calibrated fixed-wing cruise number cannot separate parasite
    # (proportional to rho) and induced (inverse-rho) power. Never reduce it
    # away from the reference condition: use the larger directional factor.
    return max(density_ratio, 1.0 / density_ratio)


def _unsupported_phase_energy_failure(
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    return (
        EnergyPower(power_w=0.0, source=EnergyPowerSource.CRUISE_POWER),
        _leg_energy_failure(
            kind=FailureKind.UNSUPPORTED,
            code=FailureCode.UNSUPPORTED_PHASE_ENERGY_MODEL,
            message="No deterministic energy model is defined for this leg phase.",
            leg=leg,
            context={"phase": leg.phase.value},
        ),
    )


def _require_leg_power(
    value: float | None,
    source: EnergyPowerSource,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    if value is None:
        return (
            EnergyPower(power_w=0.0, source=source),
            _leg_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.MISSING_ENERGY_MODEL,
                message=f"{source.value} is required for deterministic energy feasibility.",
                leg=leg,
                context={
                    "phase": leg.phase.value,
                    "required_power_source": source.value,
                },
            ),
        )

    return _validate_leg_power(value, source, leg)


def _validate_leg_power(
    value: float,
    source: EnergyPowerSource,
    leg: LegEstimate,
) -> tuple[EnergyPower, EstimatorFailure | None]:
    if value > 0:
        return EnergyPower(power_w=value, source=source), None

    return (
        EnergyPower(power_w=value, source=source),
        _leg_energy_failure(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_ENERGY_MODEL,
            message=f"{source.value} must be greater than zero.",
            leg=leg,
            context={
                "phase": leg.phase.value,
                "power_source": source.value,
                "power_w": value,
            },
        ),
    )


def _build_energy_estimate(
    *,
    context: EstimationContext,
    energy_model: EnergyModel,
    threshold_percent: float,
    legs: list[EnergyLegEstimate],
) -> tuple[EnergyEstimate | None, EstimatorFailure | None]:
    total_energy_wh = sum(leg.energy_wh for leg in legs)
    reserve_threshold_wh = energy_model.battery_capacity_wh * threshold_percent / 100.0
    usable_energy_wh = _usable_energy_wh(
        energy_model,
        reserve_threshold_wh=reserve_threshold_wh,
    )
    reserve_at_landing_wh = energy_model.battery_capacity_wh - total_energy_wh
    reserve_at_landing_percent = (
        reserve_at_landing_wh / energy_model.battery_capacity_wh * 100.0
    )
    rth_timeline, failure = _build_rth_reserve_timeline(
        context=context,
        energy_model=energy_model,
        reserve_threshold_wh=reserve_threshold_wh,
        legs=legs,
    )
    if failure is not None:
        return None, failure
    return EnergyEstimate(
        is_feasible=(
            total_energy_wh <= energy_model.battery_capacity_wh
            and reserve_at_landing_wh >= reserve_threshold_wh
            and (
                energy_model.usable_capacity_curve is None
                or total_energy_wh <= usable_energy_wh
            )
        ),
        total_energy_wh=total_energy_wh,
        battery_capacity_wh=energy_model.battery_capacity_wh,
        usable_energy_wh=usable_energy_wh,
        reserve_threshold_percent=threshold_percent,
        reserve_threshold_wh=reserve_threshold_wh,
        reserve_at_landing_wh=reserve_at_landing_wh,
        reserve_at_landing_percent=reserve_at_landing_percent,
        legs=legs,
        rth_reserve_timeline=rth_timeline,
    ), None


def _deliverable_capacity_wh(energy_model: EnergyModel) -> float:
    """Energy a full pack can actually deliver, after usable-curve derating.

    Contingency checks must budget against this rather than the nameplate
    capacity, otherwise declaring a derating curve tightens the mission gate
    while leaving every RTH and divert margin untouched.
    """

    return energy_model.battery_capacity_wh * _usable_capacity_fraction_at_soc(
        energy_model, soc=1.0
    )


def _usable_energy_wh(
    energy_model: EnergyModel,
    *,
    reserve_threshold_wh: float,
) -> float:
    return _deliverable_capacity_wh(energy_model) - reserve_threshold_wh


def _usable_capacity_fraction_at_soc(
    energy_model: EnergyModel,
    *,
    soc: float,
) -> float:
    curve = energy_model.usable_capacity_curve
    if curve is None:
        return 1.0
    if soc <= curve[0].soc:
        return curve[0].usable_fraction
    for lower, upper in zip(curve, curve[1:]):
        if soc <= upper.soc:
            span = upper.soc - lower.soc
            if span <= 0.0:
                return upper.usable_fraction
            fraction = (soc - lower.soc) / span
            return (
                lower.usable_fraction
                + (upper.usable_fraction - lower.usable_fraction) * fraction
            )
    return curve[-1].usable_fraction


def _build_rth_reserve_timeline(
    *,
    context: EstimationContext,
    energy_model: EnergyModel,
    reserve_threshold_wh: float,
    legs: list[EnergyLegEstimate],
) -> tuple[list[RthReserveTimelinePoint] | None, EstimatorFailure | None]:
    home = getattr(context.mission, "planned_home", None)
    if home is None:
        return None, None

    tas_mps, failure = _resolve_rth_tas(context)
    if failure is not None:
        return None, failure

    energy_used_by_leg = _energy_used_by_leg(legs)
    deliverable_capacity_wh = _deliverable_capacity_wh(energy_model)
    timeline: list[RthReserveTimelinePoint] = []
    elapsed_time_s = 0.0
    for leg in context.route_legs:
        elapsed_time_s += leg.time_s
        rth, rth_failure = estimate_emergency_path(
            context,
            leg,
            start_lat=leg.end_lat,
            start_lon=leg.end_lon,
            start_altitude_amsl_m=leg.end_alt_amsl_m,
            start_heading_deg=leg.ground_track_deg,
            target_lat=home.lat,
            target_lon=home.lon,
            target_altitude_amsl_m=home.altitude_amsl_m,
            tas_mps=tas_mps,
            elapsed_time_s=elapsed_time_s,
        )
        if rth_failure is not None:
            return None, rth_failure
        if rth is None:
            raise ValueError("RTH kinematics failed without a structured failure.")
        rth_energy_wh = rth.total_energy_wh
        energy_remaining_wh = deliverable_capacity_wh - energy_used_by_leg.get(
            leg.leg_index, 0.0
        )
        reserve_after_rth_wh = energy_remaining_wh - rth_energy_wh
        reserve_margin_wh = reserve_after_rth_wh - reserve_threshold_wh
        timeline.append(
            RthReserveTimelinePoint(
                leg_index=leg.leg_index,
                route_item_index=leg.route_item_index,
                route_item_id=leg.route_item_id,
                rth_distance_m=rth.distance_m,
                rth_energy_wh=rth_energy_wh,
                energy_remaining_before_rth_wh=energy_remaining_wh,
                reserve_after_rth_wh=reserve_after_rth_wh,
                reserve_margin_wh=reserve_margin_wh,
                is_feasible=reserve_margin_wh >= 0.0,
            )
        )
    return timeline, None


def _active_emergency_wind_provider(
    provider: WindProvider,
    *,
    elapsed_time_s: float,
) -> tuple[WindProvider, float | None]:
    next_change_s: float | None = None
    active = provider
    while isinstance(active, TimeVaryingWindProvider):
        candidate = active.next_change_after(elapsed_time_s)
        if candidate is not None and (
            next_change_s is None or candidate < next_change_s
        ):
            next_change_s = candidate
        active = active.provider_for_elapsed_time(elapsed_time_s)
    return active, next_change_s


def _emergency_wind_solution_failure(
    context: EstimationContext,
    leg: LegEstimate,
    *,
    solution,
    failure_context: dict[str, EstimatorContextValue],
    path_label: str,
) -> EstimatorFailure | None:
    if solution is None:
        return _leg_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.WIND_TRIANGLE_NO_SOLUTION,
            message=f"No wind-triangle solution exists along {path_label}.",
            leg=leg,
            context=failure_context,
        )
    if abs(solution.crab_angle_deg) > context.max_crab_angle_deg:
        return _leg_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.CRAB_ANGLE_LIMIT_EXCEEDED,
            message=f"{path_label.capitalize()} crab angle exceeds max_crab_angle_deg.",
            leg=leg,
            context=failure_context
            | {
                "crab_angle_deg": solution.crab_angle_deg,
                "max_crab_angle_deg": context.max_crab_angle_deg,
            },
        )
    if solution.groundspeed_mps <= 0.0:
        return _leg_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.GROUNDSPEED_NON_POSITIVE,
            message=f"{path_label.capitalize()} groundspeed is non-positive.",
            leg=leg,
            context=failure_context | {"groundspeed_mps": solution.groundspeed_mps},
        )
    if solution.groundspeed_mps < context.resolved_options.min_groundspeed_mps:
        return _leg_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.GROUNDSPEED_BELOW_MIN,
            message=(
                f"{path_label.capitalize()} groundspeed is below min_groundspeed_mps."
            ),
            leg=leg,
            context=failure_context
            | {
                "groundspeed_mps": solution.groundspeed_mps,
                "min_groundspeed_mps": context.resolved_options.min_groundspeed_mps,
            },
        )
    return None


def _integrate_emergency_segment_time(
    context: EstimationContext,
    leg: LegEstimate,
    *,
    segment: DubinsPathSegment,
    segment_index: int,
    n_segments: int,
    midpoint_lat: float,
    midpoint_lon: float,
    altitude_amsl_m: float,
    tas_mps: float,
    start_elapsed_time_s: float,
    total_path_distance_m: float,
    path_label: str,
) -> tuple[float | None, EstimatorFailure | None]:
    remaining_distance_m = segment.length_m
    segment_time_s = 0.0
    while remaining_distance_m > 1e-9:
        elapsed_time_s = start_elapsed_time_s + segment_time_s
        provider, next_change_s = _active_emergency_wind_provider(
            context.wind_provider,
            elapsed_time_s=elapsed_time_s,
        )
        wind = provider.wind_at(
            lat=midpoint_lat,
            lon=midpoint_lon,
            altitude_amsl_m=altitude_amsl_m,
            elapsed_time_s=elapsed_time_s,
        )
        solution = solve_wind_triangle(
            track_deg=segment.track_deg,
            tas_mps=tas_mps,
            wind_east_mps=wind.wind_east_mps,
            wind_north_mps=wind.wind_north_mps,
        )
        failure_context: dict[str, EstimatorContextValue] = {
            "track_azimuth_deg": segment.track_deg,
            "segment_index": segment_index,
            "n_segments": n_segments,
            "wind_east_mps": wind.wind_east_mps,
            "wind_north_mps": wind.wind_north_mps,
            "tas_mps": tas_mps,
            "path_distance_m": total_path_distance_m,
            "elapsed_time_s": elapsed_time_s,
        }
        failure = _emergency_wind_solution_failure(
            context,
            leg,
            solution=solution,
            failure_context=failure_context,
            path_label=path_label,
        )
        if failure is not None:
            return None, failure
        assert solution is not None
        completion_time_s = remaining_distance_m / solution.groundspeed_mps
        if next_change_s is None or elapsed_time_s + completion_time_s <= next_change_s:
            segment_time_s += completion_time_s
            remaining_distance_m = 0.0
            continue
        time_to_change_s = next_change_s - elapsed_time_s
        distance_to_change_m = solution.groundspeed_mps * time_to_change_s
        if (
            time_to_change_s <= 0.0
            or not 0.0 < distance_to_change_m < remaining_distance_m
        ):
            return None, _leg_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_GEOMETRY,
                message=f"{path_label.capitalize()} wind-event integration did not advance.",
                leg=leg,
                context=failure_context
                | {
                    "next_change_s": next_change_s,
                    "distance_to_change_m": distance_to_change_m,
                },
            )
        remaining_distance_m -= distance_to_change_m
        segment_time_s += time_to_change_s
    return segment_time_s, None


def _emergency_path_segments(
    context: EstimationContext,
    leg: LegEstimate,
    *,
    start_lat: float,
    start_lon: float,
    start_heading_deg: float | None,
    target_lat: float,
    target_lon: float,
) -> tuple[tuple[DubinsPathSegment, ...] | None, float, EstimatorFailure | None]:
    track_deg, _, geodesic_distance_m = context.geod.inv(
        start_lon,
        start_lat,
        target_lon,
        target_lat,
    )
    if geodesic_distance_m <= 0.0:
        return (), 0.0, None

    track_rad = math.radians(track_deg)
    target_east_m = geodesic_distance_m * math.sin(track_rad)
    target_north_m = geodesic_distance_m * math.cos(track_rad)
    # The contingency path is integrated at least as finely as the transit
    # default; a coarser transit setting must never coarsen the RTH estimate.
    sample_length_m = min(
        context.resolved_options.max_segment_length_m or _EMERGENCY_SAMPLE_LENGTH_M,
        _EMERGENCY_SAMPLE_LENGTH_M,
    )
    turn_radius_m = context.vehicle.performance.turn_radius_m
    if start_heading_deg is not None and turn_radius_m is not None:
        path = dubins_path_to_point(
            0.0,
            0.0,
            math.radians(start_heading_deg),
            target_east_m,
            target_north_m,
            turn_radius_m,
        )
        if path is None:
            return (
                None,
                0.0,
                _leg_energy_failure(
                    kind=FailureKind.INFEASIBLE,
                    code=FailureCode.INVALID_GEOMETRY,
                    message="No materializable Dubins emergency path exists.",
                    leg=leg,
                    context={
                        "entry_heading_deg": start_heading_deg,
                        "turn_radius_m": turn_radius_m,
                        "geodesic_distance_m": geodesic_distance_m,
                    },
                ),
            )
        return (
            sample_dubins_path(path, max_segment_length_m=sample_length_m),
            path.total_length_m,
            None,
        )

    segment_count = max(1, math.ceil(geodesic_distance_m / sample_length_m))
    return (
        tuple(
            DubinsPathSegment(
                midpoint_x=target_east_m * ((index + 0.5) / segment_count),
                midpoint_y=target_north_m * ((index + 0.5) / segment_count),
                track_deg=track_deg,
                length_m=geodesic_distance_m / segment_count,
            )
            for index in range(segment_count)
        ),
        geodesic_distance_m,
        None,
    )


def _emergency_vertical_energy(
    context: EstimationContext,
    leg: LegEstimate,
    *,
    start_altitude_amsl_m: float,
    target_altitude_amsl_m: float,
) -> tuple[float, float, EstimatorFailure | None]:
    vertical_delta_m = target_altitude_amsl_m - start_altitude_amsl_m
    if math.isclose(vertical_delta_m, 0.0):
        return 0.0, 0.0, None

    climbing = vertical_delta_m > 0.0
    rate_name = "climb_rate_mps" if climbing else "descent_rate_mps"
    rate_mps = getattr(context.vehicle.performance, rate_name)
    if rate_mps is None or not math.isfinite(rate_mps) or rate_mps <= 0.0:
        return (
            0.0,
            0.0,
            _leg_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=(
                    FailureCode.MISSING_REQUIRED_SPEED_PROFILE
                    if rate_mps is None
                    else FailureCode.INVALID_SPEED_PROFILE
                ),
                message=f"{rate_name} must be configured and positive for emergency landing.",
                leg=leg,
                context={rate_name: rate_mps},
            ),
        )

    energy_model = context.vehicle.energy
    source = (
        EnergyPowerSource.CLIMB_POWER if climbing else EnergyPowerSource.DESCENT_POWER
    )
    configured_power_w = (
        energy_model.climb_power_w if climbing else energy_model.descent_power_w
    )
    base_power_w = (
        energy_model.cruise_power_w
        if configured_power_w is None
        else configured_power_w
    )
    if not math.isfinite(base_power_w) or base_power_w <= 0.0:
        return (
            0.0,
            0.0,
            _leg_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_ENERGY_MODEL,
                message="Emergency vertical-phase power must be finite and positive.",
                leg=leg,
                context={"power_source": source.value, "power_w": base_power_w},
            ),
        )
    vertical_time_s = abs(vertical_delta_m) / rate_mps
    adjusted_power = _adjust_power_for_reference_conditions(
        vehicle=context.vehicle,
        source=source,
        base_power_w=base_power_w,
        altitude_amsl_m=(start_altitude_amsl_m + target_altitude_amsl_m) * 0.5,
    )
    return (
        vertical_time_s,
        adjusted_power.power_w * vertical_time_s / SECONDS_PER_HOUR,
        None,
    )


def estimate_emergency_path(
    context: EstimationContext,
    leg: LegEstimate,
    *,
    start_lat: float,
    start_lon: float,
    start_altitude_amsl_m: float,
    start_heading_deg: float | None,
    target_lat: float,
    target_lon: float,
    target_altitude_amsl_m: float,
    tas_mps: float,
    elapsed_time_s: float,
    path_label: str = "return-to-home",
) -> tuple[EmergencyPathEstimate | None, EstimatorFailure | None]:
    """Estimate a wind-aware horizontal emergency path plus terminal vertical phase."""

    segments, path_distance_m, failure = _emergency_path_segments(
        context,
        leg,
        start_lat=start_lat,
        start_lon=start_lon,
        start_heading_deg=start_heading_deg,
        target_lat=target_lat,
        target_lon=target_lon,
    )
    if failure is not None:
        return None, failure
    assert segments is not None

    horizontal_time_s = 0.0
    for segment_index, segment in enumerate(segments):
        midpoint_distance_m = math.hypot(segment.midpoint_x, segment.midpoint_y)
        midpoint_bearing_deg = math.degrees(
            math.atan2(segment.midpoint_x, segment.midpoint_y)
        )
        midpoint_lon, midpoint_lat, _ = context.geod.fwd(
            start_lon,
            start_lat,
            midpoint_bearing_deg,
            midpoint_distance_m,
        )
        segment_time_s, failure = _integrate_emergency_segment_time(
            context,
            leg,
            segment=segment,
            segment_index=segment_index,
            n_segments=len(segments),
            midpoint_lat=midpoint_lat,
            midpoint_lon=midpoint_lon,
            altitude_amsl_m=start_altitude_amsl_m,
            tas_mps=tas_mps,
            start_elapsed_time_s=elapsed_time_s + horizontal_time_s,
            total_path_distance_m=path_distance_m,
            path_label=path_label,
        )
        if failure is not None:
            return None, failure
        assert segment_time_s is not None
        horizontal_time_s += segment_time_s

    vertical_time_s, vertical_energy_wh, failure = _emergency_vertical_energy(
        context,
        leg,
        start_altitude_amsl_m=start_altitude_amsl_m,
        target_altitude_amsl_m=target_altitude_amsl_m,
    )
    if failure is not None:
        return None, failure
    horizontal_energy_wh = (
        adjusted_cruise_power_w(
            context,
            altitude_amsl_m=start_altitude_amsl_m,
        )
        * horizontal_time_s
        / SECONDS_PER_HOUR
    )
    return (
        EmergencyPathEstimate(
            distance_m=path_distance_m,
            horizontal_time_s=horizontal_time_s,
            vertical_time_s=vertical_time_s,
            horizontal_energy_wh=horizontal_energy_wh,
            vertical_energy_wh=vertical_energy_wh,
        ),
        None,
    )


def _energy_used_by_leg(legs: list[EnergyLegEstimate]) -> dict[int, float]:
    energy_used_wh = 0.0
    used_by_leg: dict[int, float] = {}
    for leg in legs:
        energy_used_wh += leg.energy_wh
        used_by_leg[leg.leg_index] = energy_used_wh
    return used_by_leg


def _resolve_rth_tas(
    context: EstimationContext,
) -> tuple[float, EstimatorFailure | None]:
    tas_mps = (
        context.mission.defaults.cruise_speed_mps
        if context.mission.defaults.cruise_speed_mps is not None
        else context.vehicle.performance.cruise_speed_mps
    )
    if tas_mps is None:
        return (
            0.0,
            _mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.MISSING_REQUIRED_SPEED_PROFILE,
                message="A TAS source is required for RTH reserve estimation.",
                context={},
            ),
        )
    if tas_mps <= 0:
        return (
            tas_mps,
            _mission_energy_failure(
                kind=FailureKind.INVALID_INPUT,
                code=FailureCode.INVALID_SPEED_PROFILE,
                message="RTH reserve tas_mps must be greater than zero.",
                context={"tas_mps": tas_mps},
            ),
        )
    return tas_mps, None


def cruise_energy_wh(
    *,
    distance_m: float,
    tas_mps: float,
    cruise_power_w: float,
) -> float:
    return cruise_power_w * (distance_m / tas_mps) / SECONDS_PER_HOUR


def _build_feasibility_failure(energy: EnergyEstimate) -> EstimatorFailure | None:
    context: dict[str, EstimatorContextValue] = {
        "total_energy_wh": energy.total_energy_wh,
        "battery_capacity_wh": energy.battery_capacity_wh,
        "usable_energy_wh": energy.usable_energy_wh,
        "reserve_at_landing_wh": energy.reserve_at_landing_wh,
        "reserve_at_landing_percent": energy.reserve_at_landing_percent,
        "reserve_threshold_wh": energy.reserve_threshold_wh,
        "reserve_threshold_percent": energy.reserve_threshold_percent,
    }
    if energy.total_energy_wh > energy.battery_capacity_wh:
        return _mission_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.INSUFFICIENT_ENERGY,
            message="Estimated mission energy exceeds battery capacity.",
            context=context,
        )

    if energy.reserve_at_landing_wh < energy.reserve_threshold_wh:
        return _mission_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.RESERVE_BELOW_THRESHOLD,
            message="Estimated landing reserve is below the required reserve threshold.",
            context=context,
        )

    if (
        energy.usable_energy_wh
        < energy.battery_capacity_wh - energy.reserve_threshold_wh
        and energy.total_energy_wh > energy.usable_energy_wh
    ):
        return _mission_energy_failure(
            kind=FailureKind.INFEASIBLE,
            code=FailureCode.INSUFFICIENT_ENERGY,
            message=(
                "Estimated mission energy exceeds usable battery energy after "
                "state-of-charge derating."
            ),
            context=context,
        )

    return None


def _build_rth_reserve_failure(
    context: EstimationContext,
    energy: EnergyEstimate,
) -> EstimatorFailure | None:
    if not context.mission.constraints.require_rth_reserve:
        return None
    timeline = energy.rth_reserve_timeline
    if timeline is None:
        return None
    failed_point = next((point for point in timeline if not point.is_feasible), None)
    if failed_point is None:
        return None
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=FailureCode.RTH_RESERVE_BELOW_THRESHOLD,
        message=("Return-to-home reserve is below the required reserve threshold."),
        leg_index=failed_point.leg_index,
        route_item_index=failed_point.route_item_index,
        route_item_id=failed_point.route_item_id,
        context={
            "rth_distance_m": failed_point.rth_distance_m,
            "rth_energy_wh": failed_point.rth_energy_wh,
            "energy_remaining_before_rth_wh": (
                failed_point.energy_remaining_before_rth_wh
            ),
            "reserve_after_rth_wh": failed_point.reserve_after_rth_wh,
            "reserve_margin_wh": failed_point.reserve_margin_wh,
            "reserve_threshold_wh": energy.reserve_threshold_wh,
        },
    )


def _mission_energy_failure(
    *,
    kind: FailureKind,
    code: FailureCode,
    message: str,
    context: dict[str, EstimatorContextValue],
) -> EstimatorFailure:
    return EstimatorFailure(
        kind=kind,
        code=code,
        message=message,
        context=context,
    )


def _leg_energy_failure(
    *,
    kind: FailureKind,
    code: FailureCode,
    message: str,
    leg: LegEstimate,
    context: dict[str, EstimatorContextValue],
) -> EstimatorFailure:
    return EstimatorFailure(
        kind=kind,
        code=code,
        message=message,
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
        context=context,
    )
