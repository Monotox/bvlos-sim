"""Deterministic mission energy feasibility evaluation."""

from collections.abc import Callable
from dataclasses import dataclass

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
from estimator.execution.runtime import EstimationContext
from estimator.math.atmosphere import isa_air_density_kgm3
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
    }
)
_CRUISE_MASS_EXPONENT = 0.5


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


def evaluate_energy_feasibility(
    context: EstimationContext,
    *,
    enforce_battery_capacity: bool = True,
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
        base_power, failure = _resolve_leg_power(
            energy_model, leg, hover_capable=hover_capable
        )
        if failure is not None:
            return EnergyEvaluation(energy=None, failure=failure)
        power = _apply_energy_fidelity(context, leg, base_power)

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
    failure = (
        _build_feasibility_failure(energy) if enforce_battery_capacity else None
    )
    if failure is None:
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
    power_w = energy_model.descent_power_w
    if leg.vertical_delta_m < 0 and power_w is not None:
        return _validate_leg_power(power_w, EnergyPowerSource.DESCENT_POWER, leg)
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

    resolver = _LEG_POWER_RESOLVERS.get(leg.phase)
    if resolver is not None:
        return resolver(energy_model, leg)

    return _unsupported_phase_energy_failure(leg)


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
    density_multiplier = _density_power_multiplier(vehicle, altitude_amsl_m)
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
    altitude_amsl_m: float,
) -> float | None:
    reference_density_kgm3 = vehicle.energy.reference_density_kgm3
    if reference_density_kgm3 is None:
        return None

    actual_density_kgm3 = isa_air_density_kgm3(altitude_amsl_m)
    return reference_density_kgm3 / actual_density_kgm3


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


def _usable_energy_wh(
    energy_model: EnergyModel,
    *,
    reserve_threshold_wh: float,
) -> float:
    if energy_model.usable_capacity_curve is None:
        return energy_model.battery_capacity_wh - reserve_threshold_wh
    return (
        energy_model.battery_capacity_wh
        * _usable_capacity_fraction_at_soc(energy_model, soc=1.0)
        - reserve_threshold_wh
    )


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
            return lower.usable_fraction + (
                upper.usable_fraction - lower.usable_fraction
            ) * fraction
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
    timeline: list[RthReserveTimelinePoint] = []
    for leg in context.route_legs:
        _, _, rth_distance_m = context.geod.inv(
            leg.end_lon,
            leg.end_lat,
            home.lon,
            home.lat,
        )
        rth_energy_wh = cruise_energy_wh(
            distance_m=rth_distance_m,
            tas_mps=tas_mps,
            cruise_power_w=adjusted_cruise_power_w(
                context,
                altitude_amsl_m=leg.end_alt_amsl_m,
            ),
        )
        energy_remaining_wh = (
            energy_model.battery_capacity_wh
            - energy_used_by_leg.get(leg.leg_index, 0.0)
        )
        reserve_after_rth_wh = energy_remaining_wh - rth_energy_wh
        reserve_margin_wh = reserve_after_rth_wh - reserve_threshold_wh
        timeline.append(
            RthReserveTimelinePoint(
                leg_index=leg.leg_index,
                route_item_index=leg.route_item_index,
                route_item_id=leg.route_item_id,
                rth_distance_m=rth_distance_m,
                rth_energy_wh=rth_energy_wh,
                energy_remaining_before_rth_wh=energy_remaining_wh,
                reserve_after_rth_wh=reserve_after_rth_wh,
                reserve_margin_wh=reserve_margin_wh,
                is_feasible=reserve_margin_wh >= 0.0,
            )
        )
    return timeline, None


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
        energy.usable_energy_wh < energy.battery_capacity_wh - energy.reserve_threshold_wh
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
        message=(
            "Return-to-home reserve is below the required reserve threshold."
        ),
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
