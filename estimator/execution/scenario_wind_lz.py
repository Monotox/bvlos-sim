"""Timeline construction, wind scheduling, and LZ availability for scenario runner."""

from collections.abc import Sequence
from typing import cast

from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.options import EstimationOptions
from estimator.core.results import LegEstimate, MissionEstimate
from estimator.core.scenario import TimelinePoint
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import (
    ConstantWindProvider,
    LayeredWindProvider,
    TimedWindChange,
    TimeVaryingWindProvider,
    WindLayer,
    WindProvider,
)
from estimator.execution.engine import try_estimate_mission_distance_time
from schemas.mission import MissionPlan, WindLayerConfig
from schemas.scenario import (
    ScenarioEvent,
    ScenarioEventKind,
    ScenarioPlan,
    ScenarioTriggerKind,
)
from schemas.vehicle import VehicleProfile

_WIND_CHANGE_CONVERGENCE_TOLERANCE_S = 1e-6
_WIND_CHANGE_MAX_EXTRA_ITERATIONS = 3


# ---------------------------------------------------------------------------
# Timeline construction
# ---------------------------------------------------------------------------


def build_home_point(mission: MissionPlan) -> TimelinePoint:
    home = mission.planned_home
    return TimelinePoint(
        index=0,
        elapsed_time_s=0.0,
        lat=home.lat,
        lon=home.lon,
        altitude_amsl_m=home.altitude_amsl_m,
    )


def _leg_to_timeline_point(
    leg: LegEstimate, index: int, elapsed_s: float
) -> TimelinePoint:
    return TimelinePoint(
        index=index,
        elapsed_time_s=elapsed_s,
        lat=leg.end_lat,
        lon=leg.end_lon,
        altitude_amsl_m=leg.end_alt_amsl_m,
        leg_index=leg.leg_index,
        route_item_index=leg.route_item_index,
        route_item_id=leg.route_item_id,
    )


def build_timeline(
    mission: MissionPlan, estimate: MissionEstimate
) -> list[TimelinePoint]:
    points: list[TimelinePoint] = [build_home_point(mission)]
    elapsed_s = 0.0
    for leg in estimate.legs:
        elapsed_s += leg.time_s
        points.append(
            _leg_to_timeline_point(leg, index=len(points), elapsed_s=elapsed_s)
        )
    return points


# ---------------------------------------------------------------------------
# Wind provider construction from scenario initial conditions
# ---------------------------------------------------------------------------


def _build_layered_wind_provider(
    layers: Sequence[WindLayerConfig],
) -> LayeredWindProvider:
    return LayeredWindProvider(
        [
            WindLayer(
                altitude_m=layer.altitude_m,
                wind_east_mps=layer.wind_east_mps,
                wind_north_mps=layer.wind_north_mps,
            )
            for layer in layers
        ]
    )


def _build_initial_layered_wind_provider(
    scenario: ScenarioPlan,
) -> LayeredWindProvider | None:
    layers = scenario.initial_conditions.wind_layers
    if layers is None:
        return None
    return _build_layered_wind_provider(layers)


def build_initial_wind_provider(scenario: ScenarioPlan) -> WindProvider:
    layered_provider = _build_initial_layered_wind_provider(scenario)
    if layered_provider is not None:
        return layered_provider
    ic = scenario.initial_conditions
    return ConstantWindProvider(
        wind_east_mps=ic.wind_east_mps,
        wind_north_mps=ic.wind_north_mps,
    )


def _has_explicit_initial_wind(scenario: ScenarioPlan) -> bool:
    return bool(
        {
            "wind_east_mps",
            "wind_north_mps",
            "wind_layers",
        }
        & scenario.initial_conditions.model_fields_set
    )


def resolve_base_wind_provider(
    scenario: ScenarioPlan,
    wind_provider: WindProvider | None,
) -> WindProvider | None:
    if _has_explicit_initial_wind(scenario):
        return build_initial_wind_provider(scenario)
    return wind_provider


def _build_event_wind_provider(event: ScenarioEvent) -> WindProvider:
    if event.wind_layers is not None:
        return _build_layered_wind_provider(event.wind_layers)
    return ConstantWindProvider(
        wind_east_mps=cast(float, event.wind_east_mps),
        wind_north_mps=cast(float, event.wind_north_mps),
    )


# ---------------------------------------------------------------------------
# Trigger index resolution (shared with event processing)
# ---------------------------------------------------------------------------


def resolve_at_route_item(
    timeline: list[TimelinePoint], route_item_id: str
) -> int | None:
    for point in timeline:
        if point.route_item_id == route_item_id:
            return point.index
    return None


def resolve_at_elapsed_time(timeline: list[TimelinePoint], elapsed_s: float) -> int:
    for point in timeline:
        if point.elapsed_time_s >= elapsed_s:
            return point.index
    return timeline[-1].index


def resolve_trigger_index(
    event: ScenarioEvent, timeline: list[TimelinePoint]
) -> int | None:
    if event.trigger == ScenarioTriggerKind.AT_MISSION_START:
        return 0
    if event.trigger == ScenarioTriggerKind.AT_MISSION_END:
        return timeline[-1].index
    if event.trigger == ScenarioTriggerKind.AT_ROUTE_ITEM:
        return resolve_at_route_item(timeline, cast(str, event.trigger_route_item_id))
    if event.trigger == ScenarioTriggerKind.AT_ELAPSED_TIME:
        return resolve_at_elapsed_time(
            timeline, cast(float, event.trigger_elapsed_time_s)
        )
    return None


# ---------------------------------------------------------------------------
# Wind change scheduling
# ---------------------------------------------------------------------------


def _wind_change_events(events: list[ScenarioEvent]) -> list[ScenarioEvent]:
    return [event for event in events if event.kind == ScenarioEventKind.WIND_CHANGE]


def _resolve_wind_change_schedule(
    events: list[ScenarioEvent],
    timeline: list[TimelinePoint],
) -> list[TimedWindChange]:
    schedule: list[TimedWindChange] = []
    for event in events:
        trigger_index = resolve_trigger_index(event, timeline)
        if trigger_index is None:
            continue
        schedule.append(
            TimedWindChange(
                effective_elapsed_time_s=timeline[trigger_index].elapsed_time_s,
                provider=_build_event_wind_provider(event),
            )
        )
    return schedule


def _same_wind_change_schedule(
    left: list[TimedWindChange],
    right: list[TimedWindChange],
) -> bool:
    if len(left) != len(right):
        return False
    return all(
        abs(a.effective_elapsed_time_s - b.effective_elapsed_time_s)
        <= _WIND_CHANGE_CONVERGENCE_TOLERANCE_S
        for a, b in zip(left, right, strict=True)
    )


def _record_wind_change_metadata(
    estimate: MissionEstimate,
    *,
    iterations: int,
    schedule_count: int,
) -> MissionEstimate:
    estimate.metadata["scenario_wind_change_iterations"] = iterations
    estimate.metadata["scenario_wind_change_count"] = schedule_count
    return estimate


def _wind_provider_for_schedule(
    base_wind_provider: WindProvider,
    schedule: list[TimedWindChange],
) -> WindProvider:
    if not schedule:
        return base_wind_provider
    return TimeVaryingWindProvider(base_wind_provider, schedule)


def _estimate_for_wind_provider(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    options: EstimationOptions,
    wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> MissionEstimate:
    return try_estimate_mission_distance_time(
        mission,
        vehicle,
        options=options,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )


def estimate_with_wind_changes(
    scenario: ScenarioPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    options: EstimationOptions,
    base_wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> MissionEstimate:
    wind_events = _wind_change_events(scenario.events)
    if not wind_events:
        return _estimate_for_wind_provider(
            mission,
            vehicle,
            options=options,
            wind_provider=base_wind_provider,
            terrain_provider=terrain_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )

    resolved_base_wind_provider = base_wind_provider or build_initial_wind_provider(
        scenario
    )
    estimate = _estimate_for_wind_provider(
        mission,
        vehicle,
        options=options,
        wind_provider=resolved_base_wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )
    previous_schedule = _resolve_wind_change_schedule(
        wind_events,
        build_timeline(mission, estimate),
    )
    if not previous_schedule:
        return _record_wind_change_metadata(
            estimate,
            iterations=0,
            schedule_count=0,
        )

    max_iterations = len(wind_events) + _WIND_CHANGE_MAX_EXTRA_ITERATIONS

    for iteration in range(1, max_iterations + 1):
        estimate = _estimate_for_wind_provider(
            mission,
            vehicle,
            options=options,
            wind_provider=_wind_provider_for_schedule(
                resolved_base_wind_provider,
                previous_schedule,
            ),
            terrain_provider=terrain_provider,
            geofences=geofences,
            landing_zones=landing_zones,
        )
        timeline = build_timeline(mission, estimate)
        schedule = _resolve_wind_change_schedule(wind_events, timeline)
        if _same_wind_change_schedule(previous_schedule, schedule):
            return _record_wind_change_metadata(
                estimate,
                iterations=iteration,
                schedule_count=len(schedule),
            )

        previous_schedule = schedule
    return _record_wind_change_metadata(
        estimate,
        iterations=max_iterations,
        schedule_count=len(previous_schedule),
    )


# ---------------------------------------------------------------------------
# Dynamic landing-zone availability
# ---------------------------------------------------------------------------


def _lz_unavailable_events(events: list[ScenarioEvent]) -> list[ScenarioEvent]:
    return [e for e in events if e.kind == ScenarioEventKind.LANDING_ZONE_UNAVAILABLE]


def _build_lz_unavailability_schedule(
    lz_events: list[ScenarioEvent],
    timeline: list[TimelinePoint],
    state_count: int,
) -> list[frozenset[str]]:
    """Return per-state unavailable zone ID sets (cumulative, monotone)."""
    schedule: list[frozenset[str]] = [frozenset() for _ in range(state_count)]
    for event in lz_events:
        trigger_index = resolve_trigger_index(event, timeline)
        if trigger_index is None:
            continue
        zone_ids = frozenset(event.unavailable_zone_ids or [])
        first_state = max(0, trigger_index - 1)
        for i in range(first_state, state_count):
            schedule[i] = schedule[i] | zone_ids
    return schedule


def apply_lz_unavailability(
    scenario: ScenarioPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    estimate: MissionEstimate,
    *,
    options: EstimationOptions,
    wind_provider: WindProvider | None,
    terrain_provider: TerrainProvider | None,
    geofences: Sequence[GeofenceZone] | None,
    landing_zones: Sequence[LandingZone] | None,
) -> MissionEstimate:
    lz_events = _lz_unavailable_events(scenario.events)
    if not lz_events or not landing_zones:
        return estimate

    timeline = build_timeline(mission, estimate)
    schedule = _build_lz_unavailability_schedule(
        lz_events, timeline, len(estimate.legs)
    )
    if not any(schedule):
        return estimate

    result = try_estimate_mission_distance_time(
        mission,
        vehicle,
        options=options,
        wind_provider=wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
        lz_unavailability=schedule,
    )
    result.metadata["scenario_lz_unavailability_event_count"] = len(lz_events)
    return result
