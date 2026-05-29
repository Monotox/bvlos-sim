"""Deterministic mission energy feasibility evaluation."""

from collections.abc import Callable
from dataclasses import dataclass

from estimator.core.enums import EnergyPowerSource, FailureCode, FailureKind, LegPhase
from estimator.core.results import (
    EnergyEstimate,
    EnergyLegEstimate,
    EstimatorContextValue,
    EstimatorFailure,
    LegEstimate,
    RthReserveTimelinePoint,
)
from estimator.execution.runtime import EstimationContext
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


@dataclass(frozen=True)
class EnergyPower:
    power_w: float
    source: EnergyPowerSource


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

    hover_capable = context.capabilities.hover
    energy_legs: list[EnergyLegEstimate] = []
    for leg in context.route_legs:
        power, failure = _resolve_leg_power(
            energy_model, leg, hover_capable=hover_capable
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
    return EnergyEvaluation(
        energy=energy,
        failure=_build_feasibility_failure(energy)
        if enforce_battery_capacity
        else None,
    )


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
        ),
        total_energy_wh=total_energy_wh,
        battery_capacity_wh=energy_model.battery_capacity_wh,
        usable_energy_wh=energy_model.battery_capacity_wh - reserve_threshold_wh,
        reserve_threshold_percent=threshold_percent,
        reserve_threshold_wh=reserve_threshold_wh,
        reserve_at_landing_wh=reserve_at_landing_wh,
        reserve_at_landing_percent=reserve_at_landing_percent,
        legs=legs,
        rth_reserve_timeline=rth_timeline,
    ), None


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
            cruise_power_w=energy_model.cruise_power_w,
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

    return None


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
