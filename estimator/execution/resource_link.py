"""Deterministic resource and communication-link feasibility evaluation."""

from dataclasses import dataclass
from enum import StrEnum

from estimator.core.enums import FailureCode, FailureKind
from estimator.core.results import (
    EnergyEstimate,
    EstimatorContextValue,
    EstimatorFailure,
    LinkEstimate,
    LinkSystemEstimate,
    ResourceEstimate,
    ResourceSystemEstimate,
)
from estimator.execution.runtime import EstimationContext
from schemas.resource_link import (
    LinkAvailability,
    LinkSystemConfig,
    ResourceSystemConfig,
    ResourceSystemKind,
)


class ResourceLimitingReason(StrEnum):
    UNSUPPORTED_RESOURCE_SYSTEM = "unsupported_resource_system"
    POWER_LIMIT_EXCEEDED = "power_limit_exceeded"
    ROUTE_DISTANCE_LIMIT_EXCEEDED = "route_distance_limit_exceeded"
    ROUTE_TIME_LIMIT_EXCEEDED = "route_time_limit_exceeded"
    TETHER_LENGTH_EXCEEDED = "tether_length_exceeded"
    RESOURCE_ENERGY_EXHAUSTED = "resource_energy_exhausted"
    RESOURCE_RESERVE_BELOW_THRESHOLD = "resource_reserve_below_threshold"


class LinkLimitingReason(StrEnum):
    LINK_UNAVAILABLE = "link_unavailable"
    LINK_RANGE_EXCEEDED = "link_range_exceeded"


@dataclass(frozen=True)
class ResourceEvaluation:
    resource: ResourceEstimate | None
    failure: EstimatorFailure | None


@dataclass(frozen=True)
class LinkEvaluation:
    link: LinkEstimate | None
    failure: EstimatorFailure | None


@dataclass(frozen=True)
class _RouteMetrics:
    route_distance_m: float
    route_time_s: float
    max_observed_home_distance_m: float


def evaluate_resource_feasibility(
    context: EstimationContext,
    energy: EnergyEstimate | None,
) -> ResourceEvaluation:
    """Evaluate configured vehicle resource systems after route expansion."""

    if not context.vehicle.resource_systems:
        return ResourceEvaluation(resource=None, failure=None)
    if energy is None:
        return ResourceEvaluation(resource=None, failure=None)

    metrics = _route_metrics(context)
    systems = [
        _evaluate_resource_system(system, energy, metrics)
        for system in context.vehicle.resource_systems
    ]
    selected = _selected_feasible_resource(systems)
    resource = ResourceEstimate(
        is_feasible=selected is not None,
        selected_resource_id=selected.resource_id if selected is not None else None,
        total_demand_wh=energy.total_energy_wh,
        peak_power_w=_peak_power_w(energy),
        route_distance_m=metrics.route_distance_m,
        route_time_s=metrics.route_time_s,
        max_observed_home_distance_m=metrics.max_observed_home_distance_m,
        systems=systems,
    )
    if resource.is_feasible:
        return ResourceEvaluation(resource=resource, failure=None)
    return ResourceEvaluation(
        resource=resource,
        failure=_resource_failure(resource),
    )


def evaluate_link_feasibility(context: EstimationContext) -> LinkEvaluation:
    """Evaluate configured mission communication-link systems after route expansion."""

    if not context.mission.link_systems:
        return LinkEvaluation(link=None, failure=None)

    metrics = _route_metrics(context)
    systems = [
        _evaluate_link_system(system, metrics)
        for system in context.mission.link_systems
    ]
    required_systems = [system for system in systems if system.required]
    feasible_required = [system for system in required_systems if system.is_feasible]
    feasible_systems = [system for system in systems if system.is_feasible]
    selected = _selected_feasible_link(feasible_required or feasible_systems)
    is_feasible = bool(feasible_required) if required_systems else True
    link = LinkEstimate(
        is_feasible=is_feasible,
        selected_link_id=selected.link_id if selected is not None else None,
        required_link_count=len(required_systems),
        available_link_count=sum(1 for system in systems if system.is_feasible),
        max_observed_range_m=metrics.max_observed_home_distance_m,
        systems=systems,
    )
    if link.is_feasible:
        return LinkEvaluation(link=link, failure=None)
    return LinkEvaluation(
        link=link,
        failure=_link_failure(link),
    )


def _route_metrics(context: EstimationContext) -> _RouteMetrics:
    return _RouteMetrics(
        route_distance_m=sum(leg.path_distance_m for leg in context.route_legs),
        route_time_s=sum(leg.time_s for leg in context.route_legs),
        max_observed_home_distance_m=_max_observed_home_distance_m(context),
    )


def _max_observed_home_distance_m(context: EstimationContext) -> float:
    home = context.mission.planned_home
    distances = [0.0]
    for leg in context.route_legs:
        for lat, lon in ((leg.start_lat, leg.start_lon), (leg.end_lat, leg.end_lon)):
            _, _, distance_m = context.geod.inv(home.lon, home.lat, lon, lat)
            distances.append(distance_m)
    return max(distances)


def _peak_power_w(energy: EnergyEstimate) -> float:
    return max((leg.power_w for leg in energy.legs), default=0.0)


def _route_constraint_reason(
    system: ResourceSystemConfig,
    metrics: _RouteMetrics,
) -> ResourceLimitingReason | None:
    if (
        system.max_route_distance_m is not None
        and metrics.route_distance_m > system.max_route_distance_m
    ):
        return ResourceLimitingReason.ROUTE_DISTANCE_LIMIT_EXCEEDED
    if (
        system.max_route_time_s is not None
        and metrics.route_time_s > system.max_route_time_s
    ):
        return ResourceLimitingReason.ROUTE_TIME_LIMIT_EXCEEDED
    if (
        system.max_tether_length_m is not None
        and metrics.max_observed_home_distance_m > system.max_tether_length_m
    ):
        return ResourceLimitingReason.TETHER_LENGTH_EXCEEDED
    return None


def _battery_capacity(system: ResourceSystemConfig, energy: EnergyEstimate) -> float:
    return (
        system.battery_capacity_wh
        if system.battery_capacity_wh is not None
        else energy.battery_capacity_wh
    )


def _reserve_threshold_percent(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
) -> float:
    return (
        system.reserve_percent
        if system.reserve_percent is not None
        else energy.reserve_threshold_percent
    )


def _battery_resource_estimate(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
    metrics: _RouteMetrics,
) -> ResourceSystemEstimate:
    capacity_wh = _battery_capacity(system, energy)
    threshold_wh = capacity_wh * _reserve_threshold_percent(system, energy) / 100.0
    reserve_after_wh = capacity_wh - energy.total_energy_wh
    limiting_reason = _route_constraint_reason(system, metrics)
    if limiting_reason is None and energy.total_energy_wh > capacity_wh:
        limiting_reason = ResourceLimitingReason.RESOURCE_ENERGY_EXHAUSTED
    if limiting_reason is None and reserve_after_wh < threshold_wh:
        limiting_reason = ResourceLimitingReason.RESOURCE_RESERVE_BELOW_THRESHOLD
    return _resource_system_estimate(
        system,
        energy,
        metrics,
        available_energy_wh=capacity_wh,
        reserve_threshold_wh=threshold_wh,
        reserve_after_resource_wh=reserve_after_wh,
        available_power_w=None,
        limiting_reason=limiting_reason,
    )


def _external_resource_estimate(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
    metrics: _RouteMetrics,
) -> ResourceSystemEstimate:
    peak_power_w = _peak_power_w(energy)
    limiting_reason = _route_constraint_reason(system, metrics)
    if limiting_reason is None and system.continuous_power_w is not None:
        if peak_power_w > system.continuous_power_w:
            limiting_reason = ResourceLimitingReason.POWER_LIMIT_EXCEEDED
    return _resource_system_estimate(
        system,
        energy,
        metrics,
        available_energy_wh=None,
        reserve_threshold_wh=None,
        reserve_after_resource_wh=None,
        available_power_w=system.continuous_power_w,
        limiting_reason=limiting_reason,
    )


def _hybrid_residual_energy_wh(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
) -> float:
    external_power_w = system.continuous_power_w or 0.0
    return sum(
        max(0.0, leg.power_w - external_power_w) * leg.time_s / 3600.0
        for leg in energy.legs
    )


def _hybrid_resource_estimate(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
    metrics: _RouteMetrics,
) -> ResourceSystemEstimate:
    residual_energy_wh = _hybrid_residual_energy_wh(system, energy)
    capacity_wh = _battery_capacity(system, energy)
    threshold_wh = capacity_wh * _reserve_threshold_percent(system, energy) / 100.0
    reserve_after_wh = capacity_wh - residual_energy_wh
    limiting_reason = _route_constraint_reason(system, metrics)
    if limiting_reason is None and residual_energy_wh > capacity_wh:
        limiting_reason = ResourceLimitingReason.RESOURCE_ENERGY_EXHAUSTED
    if limiting_reason is None and reserve_after_wh < threshold_wh:
        limiting_reason = ResourceLimitingReason.RESOURCE_RESERVE_BELOW_THRESHOLD
    return _resource_system_estimate(
        system,
        energy,
        metrics,
        available_energy_wh=capacity_wh,
        reserve_threshold_wh=threshold_wh,
        reserve_after_resource_wh=reserve_after_wh,
        available_power_w=system.continuous_power_w,
        limiting_reason=limiting_reason,
        demand_energy_wh=residual_energy_wh,
    )


def _unsupported_resource_estimate(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
    metrics: _RouteMetrics,
) -> ResourceSystemEstimate:
    return _resource_system_estimate(
        system,
        energy,
        metrics,
        available_energy_wh=None,
        reserve_threshold_wh=None,
        reserve_after_resource_wh=None,
        available_power_w=system.continuous_power_w,
        limiting_reason=ResourceLimitingReason.UNSUPPORTED_RESOURCE_SYSTEM,
    )


def _evaluate_resource_system(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
    metrics: _RouteMetrics,
) -> ResourceSystemEstimate:
    if system.kind == ResourceSystemKind.ONBOARD_BATTERY:
        return _battery_resource_estimate(system, energy, metrics)
    if system.kind == ResourceSystemKind.EXTERNAL_POWER:
        return _external_resource_estimate(system, energy, metrics)
    if system.kind == ResourceSystemKind.HYBRID:
        return _hybrid_resource_estimate(system, energy, metrics)
    return _unsupported_resource_estimate(system, energy, metrics)


def _resource_system_estimate(
    system: ResourceSystemConfig,
    energy: EnergyEstimate,
    metrics: _RouteMetrics,
    *,
    available_energy_wh: float | None,
    reserve_threshold_wh: float | None,
    reserve_after_resource_wh: float | None,
    available_power_w: float | None,
    limiting_reason: ResourceLimitingReason | None,
    demand_energy_wh: float | None = None,
) -> ResourceSystemEstimate:
    return ResourceSystemEstimate(
        resource_id=system.resource_id,
        kind=system.kind.value,
        priority=system.priority,
        is_feasible=limiting_reason is None,
        demand_energy_wh=energy.total_energy_wh
        if demand_energy_wh is None
        else demand_energy_wh,
        available_energy_wh=available_energy_wh,
        reserve_threshold_wh=reserve_threshold_wh,
        reserve_after_resource_wh=reserve_after_resource_wh,
        peak_power_w=_peak_power_w(energy),
        available_power_w=available_power_w,
        route_distance_m=metrics.route_distance_m,
        max_route_distance_m=system.max_route_distance_m,
        route_time_s=metrics.route_time_s,
        max_route_time_s=system.max_route_time_s,
        max_observed_home_distance_m=metrics.max_observed_home_distance_m,
        max_tether_length_m=system.max_tether_length_m,
        limiting_reason=limiting_reason.value if limiting_reason is not None else None,
    )


def _selected_feasible_resource(
    systems: list[ResourceSystemEstimate],
) -> ResourceSystemEstimate | None:
    feasible_systems = [system for system in systems if system.is_feasible]
    if not feasible_systems:
        return None
    return min(
        feasible_systems, key=lambda system: (system.priority, system.resource_id)
    )


def _resource_failure(resource: ResourceEstimate) -> EstimatorFailure:
    system = resource.systems[0] if resource.systems else None
    reason = system.limiting_reason if system is not None else None
    kind = (
        FailureKind.UNSUPPORTED
        if reason == ResourceLimitingReason.UNSUPPORTED_RESOURCE_SYSTEM.value
        else FailureKind.INFEASIBLE
    )
    context: dict[str, EstimatorContextValue] = {
        "resource_system_count": len(resource.systems),
        "resource_failure_reason": reason,
        "total_demand_wh": resource.total_demand_wh,
        "peak_power_w": resource.peak_power_w,
    }
    if system is not None:
        context.update(
            {
                "resource_id": system.resource_id,
                "resource_kind": system.kind,
            }
        )
    return EstimatorFailure(
        kind=kind,
        code=FailureCode.RESOURCE_FEASIBILITY_FAILED,
        message="No configured resource system can support the mission.",
        context=context,
    )


def _evaluate_link_system(
    system: LinkSystemConfig,
    metrics: _RouteMetrics,
) -> LinkSystemEstimate:
    limiting_reason = None
    if system.availability == LinkAvailability.UNAVAILABLE:
        limiting_reason = LinkLimitingReason.LINK_UNAVAILABLE
    if (
        limiting_reason is None
        and system.max_range_m is not None
        and metrics.max_observed_home_distance_m > system.max_range_m
    ):
        limiting_reason = LinkLimitingReason.LINK_RANGE_EXCEEDED
    return LinkSystemEstimate(
        link_id=system.link_id,
        kind=system.kind.value,
        required=system.required,
        priority=system.priority,
        is_feasible=limiting_reason is None,
        availability=system.availability.value,
        max_range_m=system.max_range_m,
        max_observed_range_m=metrics.max_observed_home_distance_m,
        limiting_reason=limiting_reason.value if limiting_reason is not None else None,
    )


def _selected_feasible_link(
    systems: list[LinkSystemEstimate],
) -> LinkSystemEstimate | None:
    if not systems:
        return None
    return min(systems, key=lambda system: (system.priority, system.link_id))


def _link_failure(link: LinkEstimate) -> EstimatorFailure:
    system = next((candidate for candidate in link.systems if candidate.required), None)
    context: dict[str, EstimatorContextValue] = {
        "required_link_count": link.required_link_count,
        "available_link_count": link.available_link_count,
        "max_observed_range_m": link.max_observed_range_m,
        "link_failure_reason": system.limiting_reason if system is not None else None,
    }
    if system is not None:
        context.update(
            {
                "link_id": system.link_id,
                "link_kind": system.kind,
            }
        )
    return EstimatorFailure(
        kind=FailureKind.INFEASIBLE,
        code=FailureCode.LINK_FEASIBILITY_FAILED,
        message="No required communication-link system can support the mission.",
        context=context,
    )
