"""Vertical profile resolution for transit phases."""

from dataclasses import dataclass
from math import isclose
from typing import cast

from bvlos_sim.estimator.core.enums import FailureCode, FailureKind
from bvlos_sim.estimator.execution.runtime import EstimationContext
from bvlos_sim.schemas.mission import RouteItem


@dataclass(frozen=True)
class VerticalProfile:
    delta_m: float
    distance_m: float
    time_s: float


def _resolve_vertical_rate(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    attr_name: str,
    missing_message: str,
    invalid_message: str,
    vertical_delta: float,
) -> float:
    """Read a runtime-mutated rate field defensively.

    The public API accepts already-built Pydantic models, so estimator runtime
    still guards against callers mutating validated values after construction.
    """

    rate = cast(float | None, getattr(context.vehicle.performance, attr_name))
    if rate is None:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.MISSING_REQUIRED_SPEED_PROFILE,
            message=missing_message,
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={"vertical_delta_m": vertical_delta},
        )
    if rate <= 0:
        context.fail(
            kind=FailureKind.INVALID_INPUT,
            code=FailureCode.INVALID_SPEED_PROFILE,
            message=invalid_message,
            route_item_index=route_item_index,
            route_item_id=item.id,
            context={attr_name: rate},
        )
    return rate


def compute_vertical_time(
    context: EstimationContext,
    item: RouteItem,
    *,
    route_item_index: int,
    start_alt_amsl_m: float,
    end_alt_amsl_m: float,
) -> VerticalProfile:
    vertical_delta = end_alt_amsl_m - start_alt_amsl_m
    vertical_distance = abs(vertical_delta)

    if isclose(vertical_delta, 0.0):
        return VerticalProfile(vertical_delta, vertical_distance, 0.0)

    if vertical_delta > 0:
        climb_rate = _resolve_vertical_rate(
            context,
            item,
            route_item_index=route_item_index,
            attr_name="climb_rate_mps",
            missing_message="climb_rate_mps is required for climbing legs.",
            invalid_message="climb_rate_mps must be greater than zero for climbing legs.",
            vertical_delta=vertical_delta,
        )
        return VerticalProfile(
            vertical_delta, vertical_distance, vertical_distance / climb_rate
        )

    descent_rate = _resolve_vertical_rate(
        context,
        item,
        route_item_index=route_item_index,
        attr_name="descent_rate_mps",
        missing_message="descent_rate_mps is required for descending legs.",
        invalid_message="descent_rate_mps must be greater than zero for descending legs.",
        vertical_delta=vertical_delta,
    )
    return VerticalProfile(
        vertical_delta,
        vertical_distance,
        vertical_distance / descent_rate,
    )
