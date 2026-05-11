"""Deterministic scenario runner execution engine (scenario.v1)."""

from collections.abc import Callable, Sequence
from typing import cast

from estimator.core.enums import AssertionOutcome, EstimateStatus, FidelityMode
from estimator.core.options import EstimationOptions
from estimator.core.results import EnergyEstimate, LegEstimate, MissionEstimate
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.scenario import (
    AssertionFieldValue,
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
    ScenarioStatus,
    TimelinePoint,
)
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import (
    ConstantWindProvider,
    LayeredWindProvider,
    TimedWindChange,
    TimeVaryingWindProvider,
    WindLayer,
    WindProvider,
)
from estimator.execution.divert import compute_divert_estimate
from estimator.execution.engine import try_estimate_mission_distance_time
from schemas.mission import MissionPlan, WindLayerConfig
from schemas.scenario import (
    FIELD_ASSERTION_KINDS,
    LostLinkAction,
    LostLinkPolicy,
    ScenarioAssertion,
    ScenarioAssertionKind,
    ScenarioEvent,
    ScenarioEventKind,
    ScenarioPlan,
    ScenarioTriggerKind,
)
from schemas.vehicle import VehicleProfile

# ---------------------------------------------------------------------------
# Supported field paths and their resolvers
# ---------------------------------------------------------------------------

_SUPPORTED_FIELD_PATHS: frozenset[str] = frozenset(
    {
        "estimate.status",
        "estimate.total_time_s",
        "estimate.total_horizontal_distance_m",
        "estimate.total_vertical_distance_m",
        "estimate.total_path_distance_m",
        "estimate.energy.is_feasible",
        "estimate.energy.reserve_at_landing_percent",
        "estimate.energy.reserve_at_landing_wh",
        "estimate.resource.is_feasible",
        "estimate.link.is_feasible",
        "estimate.geofence.is_feasible",
        "estimate.landing_zone.is_feasible",
    }
)

FieldResolver = Callable[[MissionEstimate], AssertionFieldValue | None]

_FIELD_RESOLVERS: dict[str, FieldResolver] = {
    "estimate.status": lambda e: str(e.status),
    "estimate.total_time_s": lambda e: e.total_time_s,
    "estimate.total_horizontal_distance_m": lambda e: e.total_horizontal_distance_m,
    "estimate.total_vertical_distance_m": lambda e: e.total_vertical_distance_m,
    "estimate.total_path_distance_m": lambda e: e.total_path_distance_m,
    "estimate.energy.is_feasible": lambda e: e.energy.is_feasible if e.energy is not None else None,
    "estimate.energy.reserve_at_landing_percent": lambda e: (
        e.energy.reserve_at_landing_percent if e.energy is not None else None
    ),
    "estimate.energy.reserve_at_landing_wh": lambda e: (
        e.energy.reserve_at_landing_wh if e.energy is not None else None
    ),
    "estimate.resource.is_feasible": lambda e: (
        e.resource.is_feasible if e.resource is not None else None
    ),
    "estimate.link.is_feasible": lambda e: (
        e.link.is_feasible if e.link is not None else None
    ),
    "estimate.geofence.is_feasible": lambda e: (
        e.geofence.is_feasible if e.geofence is not None else None
    ),
    "estimate.landing_zone.is_feasible": lambda e: (
        e.landing_zone.is_feasible if e.landing_zone is not None else None
    ),
}

NumericComparator = Callable[[float, float], bool]

_NUMERIC_COMPARATORS: dict[ScenarioAssertionKind, NumericComparator] = {
    ScenarioAssertionKind.FIELD_LT: lambda a, e: a < e,
    ScenarioAssertionKind.FIELD_GT: lambda a, e: a > e,
    ScenarioAssertionKind.FIELD_LE: lambda a, e: a <= e,
    ScenarioAssertionKind.FIELD_GE: lambda a, e: a >= e,
}

_WIND_CHANGE_CONVERGENCE_TOLERANCE_S = 1e-6
_WIND_CHANGE_MAX_EXTRA_ITERATIONS = 3


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


def _build_options(scenario: ScenarioPlan) -> EstimationOptions:
    ic = scenario.initial_conditions
    return EstimationOptions(
        wind_east_mps=ic.wind_east_mps,
        wind_north_mps=ic.wind_north_mps,
        max_segment_length_m=ic.max_segment_length_m,
        min_groundspeed_mps=ic.min_groundspeed_mps,
        fidelity=FidelityMode(ic.fidelity),
    )


def _build_layered_wind_provider(
    layers: Sequence[WindLayerConfig],
) -> LayeredWindProvider:
    return LayeredWindProvider([
        WindLayer(
            altitude_m=layer.altitude_m,
            wind_east_mps=layer.wind_east_mps,
            wind_north_mps=layer.wind_north_mps,
        )
        for layer in layers
    ])


def _build_initial_layered_wind_provider(
    scenario: ScenarioPlan,
) -> LayeredWindProvider | None:
    layers = scenario.initial_conditions.wind_layers
    if layers is None:
        return None
    return _build_layered_wind_provider(layers)


def _build_initial_wind_provider(scenario: ScenarioPlan) -> WindProvider:
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


def _resolve_base_wind_provider(
    scenario: ScenarioPlan,
    wind_provider: WindProvider | None,
) -> WindProvider | None:
    if _has_explicit_initial_wind(scenario):
        return _build_initial_wind_provider(scenario)
    return wind_provider


def _build_event_wind_provider(event: ScenarioEvent) -> WindProvider:
    if event.wind_layers is not None:
        return _build_layered_wind_provider(event.wind_layers)
    return ConstantWindProvider(
        wind_east_mps=cast(float, event.wind_east_mps),
        wind_north_mps=cast(float, event.wind_north_mps),
    )


def _mission_with_scenario_link_systems(
    scenario: ScenarioPlan,
    mission: MissionPlan,
) -> MissionPlan:
    link_systems = scenario.initial_conditions.link_systems
    if link_systems is None:
        return mission
    return mission.model_copy(update={"link_systems": link_systems})


# ---------------------------------------------------------------------------
# Timeline construction
# ---------------------------------------------------------------------------


def _home_point(mission: MissionPlan) -> TimelinePoint:
    home = mission.planned_home
    return TimelinePoint(
        index=0,
        elapsed_time_s=0.0,
        lat=home.lat,
        lon=home.lon,
        altitude_amsl_m=home.altitude_amsl_m,
    )


def _leg_to_timeline_point(leg: LegEstimate, index: int, elapsed_s: float) -> TimelinePoint:
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


def _build_timeline(mission: MissionPlan, estimate: MissionEstimate) -> list[TimelinePoint]:
    points: list[TimelinePoint] = [_home_point(mission)]
    elapsed_s = 0.0
    for leg in estimate.legs:
        elapsed_s += leg.time_s
        points.append(_leg_to_timeline_point(leg, index=len(points), elapsed_s=elapsed_s))
    return points


# ---------------------------------------------------------------------------
# Event trigger resolution
# ---------------------------------------------------------------------------


def _resolve_at_route_item(
    timeline: list[TimelinePoint], route_item_id: str
) -> int | None:
    """Return the first timeline index where route_item_id matches, or None."""
    for point in timeline:
        if point.route_item_id == route_item_id:
            return point.index
    return None


def _resolve_at_elapsed_time(
    timeline: list[TimelinePoint], elapsed_s: float
) -> int:
    """Return the first timeline index >= elapsed_s, or the last point."""
    for point in timeline:
        if point.elapsed_time_s >= elapsed_s:
            return point.index
    return timeline[-1].index


def _resolve_trigger_index(
    event: ScenarioEvent, timeline: list[TimelinePoint]
) -> int | None:
    if event.trigger == ScenarioTriggerKind.AT_MISSION_START:
        return 0
    if event.trigger == ScenarioTriggerKind.AT_MISSION_END:
        return timeline[-1].index
    if event.trigger == ScenarioTriggerKind.AT_ROUTE_ITEM:
        return _resolve_at_route_item(timeline, cast(str, event.trigger_route_item_id))
    if event.trigger == ScenarioTriggerKind.AT_ELAPSED_TIME:
        return _resolve_at_elapsed_time(timeline, cast(float, event.trigger_elapsed_time_s))
    return None


# ---------------------------------------------------------------------------
# Event processing
# ---------------------------------------------------------------------------


def _fired_event_outcome(event: ScenarioEvent, timeline_index: int) -> ScenarioEventOutcome:
    return ScenarioEventOutcome(
        event_id=event.event_id,
        kind=event.kind,
        fired=True,
        timeline_index=timeline_index,
    )


def _not_fired_event_outcome(event: ScenarioEvent) -> ScenarioEventOutcome:
    return ScenarioEventOutcome(
        event_id=event.event_id,
        kind=event.kind,
        fired=False,
    )


def _entry_heading_at_index(legs: list[LegEstimate], action_index: int) -> float | None:
    """Return ground_track_deg of the last leg before action_index, or None."""
    leg_index = action_index - 1
    if leg_index < 0 or leg_index >= len(legs):
        return None
    return legs[leg_index].ground_track_deg


def _build_policy_outcome(
    policy: LostLinkPolicy,
    timeline: list[TimelinePoint],
    trigger_index: int,
    *,
    energy: EnergyEstimate | None,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    landing_zones: Sequence[LandingZone] | None,
    legs: list[LegEstimate],
) -> CommsLinkPolicyOutcome:
    trigger_point = timeline[trigger_index]
    action_elapsed_s = trigger_point.elapsed_time_s + policy.loiter_s
    action_index = _resolve_at_elapsed_time(timeline, action_elapsed_s)
    action_point = timeline[action_index]

    divert_estimate = None
    if (
        policy.action == LostLinkAction.DIVERT
        and policy.divert_target_id is not None
        and landing_zones
    ):
        entry_heading_deg = _entry_heading_at_index(legs, action_index)
        divert_estimate = compute_divert_estimate(
            action_lat=action_point.lat,
            action_lon=action_point.lon,
            action_at_timeline_index=action_index,
            target_zone_id=policy.divert_target_id,
            landing_zones=landing_zones,
            energy=energy,
            mission=mission,
            vehicle=vehicle,
            entry_heading_deg=entry_heading_deg,
        )

    return CommsLinkPolicyOutcome(
        action=policy.action,
        loiter_s=policy.loiter_s,
        link_lost_at_timeline_index=trigger_index,
        link_lost_at_elapsed_s=trigger_point.elapsed_time_s,
        action_at_elapsed_s=action_elapsed_s,
        action_at_timeline_index=action_index,
        action_lat=action_point.lat,
        action_lon=action_point.lon,
        action_altitude_amsl_m=action_point.altitude_amsl_m,
        divert_target_id=policy.divert_target_id,
        divert_estimate=divert_estimate,
    )


def _process_lost_link_event(
    event: ScenarioEvent,
    timeline: list[TimelinePoint],
    policy: LostLinkPolicy | None,
    trigger_index: int,
    *,
    energy: EnergyEstimate | None,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    landing_zones: Sequence[LandingZone] | None,
    legs: list[LegEstimate],
) -> ScenarioEventOutcome:
    policy_outcome = (
        _build_policy_outcome(
            policy,
            timeline,
            trigger_index,
            energy=energy,
            mission=mission,
            vehicle=vehicle,
            landing_zones=landing_zones,
            legs=legs,
        )
        if policy is not None
        else None
    )
    return ScenarioEventOutcome(
        event_id=event.event_id,
        kind=event.kind,
        fired=True,
        timeline_index=trigger_index,
        policy_outcome=policy_outcome,
    )


def _process_event(
    event: ScenarioEvent,
    timeline: list[TimelinePoint],
    lost_link_policy: LostLinkPolicy | None,
    *,
    energy: EnergyEstimate | None,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    landing_zones: Sequence[LandingZone] | None,
    legs: list[LegEstimate],
) -> ScenarioEventOutcome:
    trigger_index = _resolve_trigger_index(event, timeline)
    if trigger_index is None:
        return _not_fired_event_outcome(event)
    if event.kind == ScenarioEventKind.LOST_LINK:
        return _process_lost_link_event(
            event,
            timeline,
            lost_link_policy,
            trigger_index,
            energy=energy,
            mission=mission,
            vehicle=vehicle,
            landing_zones=landing_zones,
            legs=legs,
        )
    return _fired_event_outcome(event, trigger_index)


def _process_events(
    events: list[ScenarioEvent],
    timeline: list[TimelinePoint],
    lost_link_policy: LostLinkPolicy | None,
    *,
    energy: EnergyEstimate | None,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    landing_zones: Sequence[LandingZone] | None,
    legs: list[LegEstimate],
) -> list[ScenarioEventOutcome]:
    return [
        _process_event(
            event,
            timeline,
            lost_link_policy,
            energy=energy,
            mission=mission,
            vehicle=vehicle,
            landing_zones=landing_zones,
            legs=legs,
        )
        for event in events
    ]


# ---------------------------------------------------------------------------
# Dynamic wind-change scheduling
# ---------------------------------------------------------------------------


def _wind_change_events(events: list[ScenarioEvent]) -> list[ScenarioEvent]:
    return [event for event in events if event.kind == ScenarioEventKind.WIND_CHANGE]


def _resolve_wind_change_schedule(
    events: list[ScenarioEvent],
    timeline: list[TimelinePoint],
) -> list[TimedWindChange]:
    schedule: list[TimedWindChange] = []
    for event in events:
        trigger_index = _resolve_trigger_index(event, timeline)
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


def _estimate_with_wind_changes(
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

    resolved_base_wind_provider = (
        base_wind_provider or _build_initial_wind_provider(scenario)
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
        _build_timeline(mission, estimate),
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
        timeline = _build_timeline(mission, estimate)
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
        trigger_index = _resolve_trigger_index(event, timeline)
        if trigger_index is None:
            continue
        zone_ids = frozenset(event.unavailable_zone_ids or [])
        first_state = max(0, trigger_index - 1)
        for i in range(first_state, state_count):
            schedule[i] = schedule[i] | zone_ids
    return schedule


def _apply_lz_unavailability(
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

    timeline = _build_timeline(mission, estimate)
    schedule = _build_lz_unavailability_schedule(lz_events, timeline, len(estimate.legs))
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


# ---------------------------------------------------------------------------
# Field resolution for assertions
# ---------------------------------------------------------------------------


def _resolve_field_value(
    field_path: str, estimate: MissionEstimate | None
) -> AssertionFieldValue | None:
    if estimate is None:
        return None
    resolver = _FIELD_RESOLVERS.get(field_path)
    if resolver is None:
        return None
    return resolver(estimate)


# ---------------------------------------------------------------------------
# Assertion result builders
# ---------------------------------------------------------------------------


def _passed(
    assertion: ScenarioAssertion,
    message: str,
    *,
    field_path: str | None = None,
    expected: AssertionFieldValue | None = None,
    actual: AssertionFieldValue | None = None,
) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.PASSED,
        message=message,
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _failed(
    assertion: ScenarioAssertion,
    message: str,
    *,
    expected: AssertionFieldValue | None = None,
    actual: AssertionFieldValue | None = None,
    field_path: str | None = None,
) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.FAILED,
        message=message,
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _skipped(assertion: ScenarioAssertion, message: str) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.SKIPPED,
        message=message,
        field_path=assertion.field_path,
        expected=assertion.expected,
    )


def _unsupported(
    assertion: ScenarioAssertion, reason: str
) -> ScenarioAssertionResult:
    return ScenarioAssertionResult(
        assertion_id=assertion.assertion_id,
        kind=assertion.kind,
        outcome=AssertionOutcome.UNSUPPORTED,
        message=f"Assertion is not supported: {reason}",
        field_path=assertion.field_path,
        unsupported_reason=reason,
    )


# ---------------------------------------------------------------------------
# Assertion evaluation
# ---------------------------------------------------------------------------


def _evaluate_estimate_succeeds(
    assertion: ScenarioAssertion, estimate: MissionEstimate | None
) -> ScenarioAssertionResult:
    if estimate is None:
        return _failed(assertion, "Estimate is None; estimation did not produce a result.")
    if estimate.status == EstimateStatus.SUCCESS:
        return _passed(assertion, f"Estimate status is '{estimate.status}' (success).")
    return _failed(
        assertion,
        f"Estimate status is '{estimate.status}', expected 'success'.",
        field_path="estimate.status",
        expected="success",
        actual=str(estimate.status),
    )


def _evaluate_estimate_fails(
    assertion: ScenarioAssertion, estimate: MissionEstimate | None
) -> ScenarioAssertionResult:
    if estimate is None:
        return _passed(assertion, "Estimate is None; estimation did not produce a result.")
    if estimate.status != EstimateStatus.SUCCESS:
        return _passed(assertion, f"Estimate status is '{estimate.status}' (not success).")
    return _failed(
        assertion,
        "Estimate status is 'success', expected a non-success status.",
        field_path="estimate.status",
        expected="<not success>",
        actual=str(estimate.status),
    )


def _is_numeric_value(value: AssertionFieldValue) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _evaluate_eq_assertion(
    assertion: ScenarioAssertion,
    actual: AssertionFieldValue,
    expected: AssertionFieldValue,
    field_path: str,
) -> ScenarioAssertionResult:
    def values_equal(a: AssertionFieldValue, e: AssertionFieldValue) -> bool:
        if isinstance(e, bool) and isinstance(a, bool):
            return a == e
        if isinstance(e, (int, float)) and isinstance(a, (int, float)):
            return a == e
        if isinstance(a, str) and isinstance(e, str):
            return a == e
        return False

    if values_equal(actual, expected):
        return _passed(
            assertion,
            f"'{field_path}' == {expected!r} (actual: {actual!r}).",
            field_path=field_path,
            expected=expected,
            actual=actual,
        )
    return _failed(
        assertion,
        f"'{field_path}' expected {expected!r} but was {actual!r}.",
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _evaluate_numeric_assertion(
    assertion: ScenarioAssertion,
    actual: AssertionFieldValue,
    expected: AssertionFieldValue,
    field_path: str,
) -> ScenarioAssertionResult:
    if not _is_numeric_value(actual):
        reason = (
            f"Field '{field_path}' has a non-numeric value; "
            f"cannot apply '{assertion.kind}' comparison."
        )
        return _unsupported(assertion, reason)
    if not _is_numeric_value(expected):
        reason = (
            f"Expected value {expected!r} is not numeric; "
            f"cannot apply '{assertion.kind}' comparison."
        )
        return _unsupported(assertion, reason)

    comparator = _NUMERIC_COMPARATORS[assertion.kind]
    if comparator(cast(float, actual), cast(float, expected)):
        return _passed(
            assertion,
            f"'{field_path}' {assertion.kind} {expected!r} satisfied (actual: {actual!r}).",
            field_path=field_path,
            expected=expected,
            actual=actual,
        )
    return _failed(
        assertion,
        f"'{field_path}' {assertion.kind} {expected!r} not satisfied (actual: {actual!r}).",
        field_path=field_path,
        expected=expected,
        actual=actual,
    )


def _evaluate_field_assertion(
    assertion: ScenarioAssertion, estimate: MissionEstimate | None
) -> ScenarioAssertionResult:
    field_path = cast(str, assertion.field_path)

    if field_path not in _SUPPORTED_FIELD_PATHS:
        reason = (
            f"Field path '{field_path}' is not supported in scenario.v1. "
            "See docs for supported field paths."
        )
        return _unsupported(assertion, reason)

    actual = _resolve_field_value(field_path, estimate)
    if actual is None:
        return _skipped(
            assertion,
            f"Field '{field_path}' is not available in the estimate result.",
        )

    expected = cast(AssertionFieldValue, assertion.expected)

    if assertion.kind == ScenarioAssertionKind.FIELD_EQ:
        return _evaluate_eq_assertion(assertion, actual, expected, field_path)

    return _evaluate_numeric_assertion(assertion, actual, expected, field_path)


def _evaluate_policy_action_eq(
    assertion: ScenarioAssertion,
    event_outcomes: list[ScenarioEventOutcome],
) -> ScenarioAssertionResult:
    event_id = cast(str, assertion.event_id)
    outcome = next((o for o in event_outcomes if o.event_id == event_id), None)
    if outcome is None:
        return _skipped(
            assertion,
            f"No event with id '{event_id}' found in event outcomes.",
        )
    if not outcome.fired:
        return _skipped(assertion, f"Event '{event_id}' did not fire.")
    if outcome.policy_outcome is None:
        return _skipped(
            assertion,
            f"Event '{event_id}' has no policy outcome; no lost_link_policy configured.",
        )
    actual: AssertionFieldValue = outcome.policy_outcome.action
    expected: AssertionFieldValue = str(assertion.expected)
    if actual == expected:
        return _passed(
            assertion,
            f"Policy action for event '{event_id}' is '{actual}' as expected.",
            expected=expected,
            actual=actual,
        )
    return _failed(
        assertion,
        f"Policy action for event '{event_id}' is '{actual}', expected '{expected}'.",
        expected=expected,
        actual=actual,
    )


_ASSERTION_EVALUATORS: dict[
    ScenarioAssertionKind,
    Callable[[ScenarioAssertion, MissionEstimate | None], ScenarioAssertionResult],
] = {
    ScenarioAssertionKind.ESTIMATE_SUCCEEDS: _evaluate_estimate_succeeds,
    ScenarioAssertionKind.ESTIMATE_FAILS: _evaluate_estimate_fails,
    **{kind: _evaluate_field_assertion for kind in FIELD_ASSERTION_KINDS},
}

PolicyEvaluator = Callable[
    [ScenarioAssertion, list[ScenarioEventOutcome]], ScenarioAssertionResult
]

_POLICY_EVALUATORS: dict[ScenarioAssertionKind, PolicyEvaluator] = {
    ScenarioAssertionKind.POLICY_ACTION_EQ: _evaluate_policy_action_eq,
}


def _evaluate_assertion(
    assertion: ScenarioAssertion,
    estimate: MissionEstimate | None,
    event_outcomes: list[ScenarioEventOutcome],
) -> ScenarioAssertionResult:
    policy_evaluator = _POLICY_EVALUATORS.get(assertion.kind)
    if policy_evaluator is not None:
        return policy_evaluator(assertion, event_outcomes)
    evaluator = _ASSERTION_EVALUATORS.get(assertion.kind)
    if evaluator is None:
        return _unsupported(
            assertion,
            f"Assertion kind '{assertion.kind}' is not handled in scenario.v1.",
        )
    return evaluator(assertion, estimate)


# ---------------------------------------------------------------------------
# Status determination
# ---------------------------------------------------------------------------


def _determine_status(assertion_results: list[ScenarioAssertionResult]) -> ScenarioStatus:
    any_failed = any(r.outcome == AssertionOutcome.FAILED for r in assertion_results)
    return ScenarioStatus.FAILED if any_failed else ScenarioStatus.PASSED


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_scenario(
    scenario: ScenarioPlan,
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider: WindProvider | None = None,
    terrain_provider: TerrainProvider | None = None,
    geofences: Sequence[GeofenceZone] | None = None,
    landing_zones: Sequence[LandingZone] | None = None,
) -> ScenarioResult:
    """Execute a deterministic scenario and return a structured result.

    This function is pure and does not depend on CLI adapters or I/O.
    """
    mission = _mission_with_scenario_link_systems(scenario, mission)
    options = _build_options(scenario)
    resolved_wind_provider = _resolve_base_wind_provider(scenario, wind_provider)
    estimate = _estimate_with_wind_changes(
        scenario,
        mission,
        vehicle,
        options,
        resolved_wind_provider,
        terrain_provider,
        geofences,
        landing_zones,
    )
    estimate = _apply_lz_unavailability(
        scenario,
        mission,
        vehicle,
        estimate,
        options=options,
        wind_provider=resolved_wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )

    timeline = _build_timeline(mission, estimate)
    lost_link_policy = scenario.initial_conditions.lost_link_policy
    event_outcomes = _process_events(
        scenario.events,
        timeline,
        lost_link_policy,
        energy=estimate.energy,
        mission=mission,
        vehicle=vehicle,
        landing_zones=landing_zones,
        legs=list(estimate.legs),
    )
    assertion_results = [
        _evaluate_assertion(assertion, estimate, event_outcomes)
        for assertion in scenario.assertions
    ]
    status = _determine_status(assertion_results)

    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        status=status,
        deterministic=True,
        timeline=timeline,
        event_outcomes=event_outcomes,
        assertion_results=assertion_results,
        estimate=estimate,
    )
