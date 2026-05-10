"""Reusable execution-time rules and profile resolution helpers."""

from dataclasses import dataclass

from estimator.core.enums import FailureCode
from estimator.core.enums import FailureKind
from estimator.core.enums import SpeedSource
from estimator.core.enums import WarningCode
from estimator.core.results import EstimatorContextValue
from estimator.execution.runtime import EstimationContext
from schemas.mission import RouteItem


@dataclass(frozen=True)
class GlobalConstraint:
    code: FailureCode
    condition: bool
    message: str
    context_values: dict[str, EstimatorContextValue]


def validate_global_constraints(context: EstimationContext) -> None:
    """Defensive checks for programmatic callers mutating validated models."""
    checks = (
        GlobalConstraint(
            code=FailureCode.INVALID_SPEED_PROFILE,
            condition=context.resolved_options.min_groundspeed_mps <= 0,
            message="min_groundspeed_mps must be greater than zero.",
            context_values={
                "min_groundspeed_mps": context.resolved_options.min_groundspeed_mps
            },
        ),
        GlobalConstraint(
            code=FailureCode.INVALID_SPEED_PROFILE,
            condition=not 0 < context.max_crab_angle_deg < 90,
            message="max_crab_angle_deg must be greater than 0 and less than 90.",
            context_values={"max_crab_angle_deg": context.max_crab_angle_deg},
        ),
        GlobalConstraint(
            code=FailureCode.INVALID_SPEED_PROFILE,
            condition=(
                context.vehicle.performance.max_station_keep_wind_mps is not None
                and context.vehicle.performance.max_station_keep_wind_mps < 0
            ),
            message="max_station_keep_wind_mps must be non-negative.",
            context_values={
                "max_station_keep_wind_mps": (
                    context.vehicle.performance.max_station_keep_wind_mps
                )
            },
        ),
    )
    for check in checks:
        if check.condition:
            context.fail(
                kind=FailureKind.INVALID_INPUT,
                code=check.code,
                message=check.message,
                route_item_index=None,
                route_item_id=None,
                context=check.context_values,
            )


def resolve_transit_tas(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
) -> tuple[float, SpeedSource]:
    candidates = (
        (
            context.mission.defaults.cruise_speed_mps,
            SpeedSource.MISSION_DEFAULT_CRUISE_SPEED,
        ),
        (
            context.vehicle.performance.cruise_speed_mps,
            SpeedSource.VEHICLE_CRUISE_SPEED,
        ),
    )
    tas_mps, speed_source = next(
        ((value, source) for value, source in candidates if value is not None),
        (None, SpeedSource.NONE),
    )

    if tas_mps is None:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.MISSING_REQUIRED_SPEED_PROFILE,
            message="A TAS source is required for forward-flight transit.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"action": item.action.value},
        )
    if tas_mps <= 0:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_SPEED_PROFILE,
            message="tas_mps must be greater than zero.",
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"tas_mps": tas_mps},
        )
    return tas_mps, speed_source


def resolve_station_keep_authority(
    context: EstimationContext,
    *,
    route_item_index: int,
    route_item_id: str | None,
) -> tuple[float | None, list[WarningCode]]:
    leg_warnings: list[WarningCode] = []
    authority = context.vehicle.performance.max_station_keep_wind_mps
    if authority is not None:
        return authority, leg_warnings

    hover_speed = context.vehicle.performance.hover_speed_mps
    if hover_speed is not None:
        context.add_warning(
            WarningCode.HOVER_SPEED_USED_AS_STATION_KEEP_AUTHORITY,
            (
                "max_station_keep_wind_mps missing; using hover_speed_mps as "
                "station-keep wind authority fallback."
            ),
            route_item_index=route_item_index,
            route_item_id=route_item_id,
        )
        leg_warnings.append(WarningCode.HOVER_SPEED_USED_AS_STATION_KEEP_AUTHORITY)
        return hover_speed, leg_warnings

    return None, leg_warnings
