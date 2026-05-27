"""Deterministic scenario runner execution engine (scenario.v1)."""

from collections.abc import Sequence

from estimator.core.enums import FidelityMode
from estimator.core.options import EstimationOptions
from estimator.core.results import EnergyEstimate, LegEstimate
from estimator.core.geofence import GeofenceZone
from estimator.core.landing_zone import LandingZone
from estimator.core.scenario import (
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    ScenarioResult,
    TimelinePoint,
)
from estimator.environment.terrain import TerrainProvider
from estimator.environment.wind import WindProvider
from estimator.execution.divert import compute_divert_estimate
from estimator.execution.scenario_assertions import (
    determine_scenario_status,
    evaluate_assertion,
)
from estimator.execution.scenario_wind_lz import (
    apply_lz_unavailability,
    build_timeline,
    estimate_with_wind_changes,
    resolve_at_elapsed_time,
    resolve_trigger_index,
    resolve_base_wind_provider,
)
from schemas.mission import MissionPlan
from schemas.scenario import (
    LostLinkAction,
    LostLinkPolicy,
    ScenarioEvent,
    ScenarioEventKind,
    ScenarioPlan,
)
from schemas.vehicle import VehicleProfile


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------


def _build_options(scenario: ScenarioPlan) -> EstimationOptions:
    ic = scenario.initial_conditions
    explicit_fidelity = (
        FidelityMode(ic.fidelity) if "fidelity" in ic.model_fields_set else None
    )
    return EstimationOptions(
        wind_east_mps=ic.wind_east_mps,
        wind_north_mps=ic.wind_north_mps,
        max_segment_length_m=ic.max_segment_length_m,
        min_groundspeed_mps=ic.min_groundspeed_mps,
        fidelity=explicit_fidelity,
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
# Event processing
# ---------------------------------------------------------------------------


def _fired_event_outcome(
    event: ScenarioEvent, timeline_index: int
) -> ScenarioEventOutcome:
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
    wind_provider: WindProvider | None = None,
) -> CommsLinkPolicyOutcome:
    trigger_point = timeline[trigger_index]
    action_elapsed_s = trigger_point.elapsed_time_s + policy.loiter_s
    action_index = resolve_at_elapsed_time(timeline, action_elapsed_s)
    action_point = timeline[action_index]

    divert_estimate = None
    if policy.action == LostLinkAction.DIVERT and policy.divert_target_id is not None:
        entry_heading_deg = _entry_heading_at_index(legs, action_index)
        wind_east = 0.0
        wind_north = 0.0
        wind_corrected = False
        if wind_provider is not None:
            wind_vec = wind_provider.wind_at(
                action_point.lat,
                action_point.lon,
                action_point.altitude_amsl_m,
                action_elapsed_s,
            )
            wind_east = wind_vec.wind_east_mps
            wind_north = wind_vec.wind_north_mps
            wind_corrected = True
        divert_estimate = compute_divert_estimate(
            action_lat=action_point.lat,
            action_lon=action_point.lon,
            action_at_timeline_index=action_index,
            target_zone_id=policy.divert_target_id,
            landing_zones=landing_zones or [],
            energy=energy,
            mission=mission,
            vehicle=vehicle,
            entry_heading_deg=entry_heading_deg,
            wind_east_mps=wind_east,
            wind_north_mps=wind_north,
            wind_corrected=wind_corrected,
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
    wind_provider: WindProvider | None = None,
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
            wind_provider=wind_provider,
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
    wind_provider: WindProvider | None = None,
) -> ScenarioEventOutcome:
    trigger_index = resolve_trigger_index(event, timeline)
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
            wind_provider=wind_provider,
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
    wind_provider: WindProvider | None = None,
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
            wind_provider=wind_provider,
        )
        for event in events
    ]


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
    resolved_wind_provider = resolve_base_wind_provider(scenario, wind_provider)
    estimate, effective_wind_provider = estimate_with_wind_changes(
        scenario,
        mission,
        vehicle,
        options,
        resolved_wind_provider,
        terrain_provider,
        geofences,
        landing_zones,
    )
    estimate = apply_lz_unavailability(
        scenario,
        mission,
        vehicle,
        estimate,
        options=options,
        wind_provider=effective_wind_provider,
        terrain_provider=terrain_provider,
        geofences=geofences,
        landing_zones=landing_zones,
    )

    timeline = build_timeline(mission, estimate)
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
        wind_provider=effective_wind_provider,
    )
    assertion_results: list[ScenarioAssertionResult] = [
        evaluate_assertion(assertion, estimate, event_outcomes)
        for assertion in scenario.assertions
    ]
    status = determine_scenario_status(assertion_results)

    return ScenarioResult(
        scenario_id=scenario.scenario_id,
        status=status,
        deterministic=True,
        timeline=timeline,
        event_outcomes=event_outcomes,
        assertion_results=assertion_results,
        estimate=estimate,
    )
