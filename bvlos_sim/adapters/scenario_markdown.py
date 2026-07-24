"""Markdown rendering adapter for scenario result envelopes."""

from collections.abc import Callable

from bvlos_sim.adapters.scenario_envelope import ScenarioResultEnvelope
from bvlos_sim.estimator.core.scenario import (
    AssertionOutcome,
    CommsLinkPolicyOutcome,
    ScenarioAssertionResult,
    ScenarioEventOutcome,
    TimelinePoint,
)

# ---------------------------------------------------------------------------
# Generic section helpers
# ---------------------------------------------------------------------------

Lines = list[str]
SectionRenderer = Callable[[ScenarioResultEnvelope], Lines]


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _section(title: str, body: Lines) -> Lines:
    return ["", f"## {title}", "", *body]


def _empty_section(title: str) -> Lines:
    return _section(title, ["- None"])


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _fmt_point(point: TimelinePoint) -> str:
    tag = f" [{point.route_item_id}]" if point.route_item_id is not None else ""
    return (
        f"- [{point.index}] t={point.elapsed_time_s:.2f}s"
        f" ({point.lat:.5f}, {point.lon:.5f})"
        f" alt={point.altitude_amsl_m:.1f}m{tag}"
    )


def _fmt_policy_outcome(policy: CommsLinkPolicyOutcome) -> Lines:
    lines: Lines = [
        f"  - Policy: `{policy.action}` after `{policy.loiter_s:.1f}s` loiter"
        f" at t=`{policy.action_at_elapsed_s:.2f}s`"
        f" ({policy.action_lat:.5f}, {policy.action_lon:.5f})"
        f" alt=`{policy.action_altitude_amsl_m:.1f}m`"
    ]
    if policy.divert_estimate is not None:
        de = policy.divert_estimate
        lines.append(
            f"  - Divert to `{de.target_zone_id}`: "
            f"{de.distance_m:.0f}m, {de.time_s:.1f}s, "
            f"feasible=`{str(de.is_feasible).lower()}`"
        )
        if not de.is_feasible and de.infeasible_reason:
            lines.append(f"  - Divert infeasible: {de.infeasible_reason}")
        for w in de.warnings:
            lines.append(f"  - Divert warning: `{w}`")
    return lines


def _fmt_event_outcome(outcome: ScenarioEventOutcome) -> Lines:
    if outcome.unsupported:
        return [
            f"- `{outcome.event_id}` ({outcome.kind}):"
            f" unsupported — {outcome.unsupported_reason}"
        ]
    if outcome.fired:
        lines: Lines = [
            f"- `{outcome.event_id}` ({outcome.kind}):"
            f" fired at timeline[{outcome.timeline_index}]"
        ]
        if outcome.policy_outcome is not None:
            lines.extend(_fmt_policy_outcome(outcome.policy_outcome))
        return lines
    if outcome.not_fired_reason:
        return [f"- `{outcome.event_id}` ({outcome.kind}): not fired — {outcome.not_fired_reason}"]
    return [f"- `{outcome.event_id}` ({outcome.kind}): not fired"]


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------


def _render_assertion_results(envelope: ScenarioResultEnvelope) -> Lines:
    if not envelope.assertion_results:
        return _empty_section("Assertion Results")
    body = [
        f"- `{r.assertion_id}` `{r.outcome}`: {r.message}"
        for r in envelope.assertion_results
    ]
    return _section("Assertion Results", body)


def _render_timeline(envelope: ScenarioResultEnvelope) -> Lines:
    if not envelope.timeline:
        return _empty_section("Timeline")
    return _section("Timeline", [_fmt_point(p) for p in envelope.timeline])


def _render_event_outcomes(envelope: ScenarioResultEnvelope) -> Lines:
    if not envelope.event_outcomes:
        return _empty_section("Event Outcomes")
    body: Lines = []
    for o in envelope.event_outcomes:
        body.extend(_fmt_event_outcome(o))
    return _section("Event Outcomes", body)


def _render_determinism(envelope: ScenarioResultEnvelope) -> Lines:
    dm = envelope.determinism_metadata
    body = [
        f"- Deterministic: `{str(dm.deterministic).lower()}`",
        f"- External network access used: `{str(dm.external_network_access_used).lower()}`",
    ]
    return _section("Determinism", body)


def _render_provenance(envelope: ScenarioResultEnvelope) -> Lines:
    prov = envelope.provenance
    body = [f"- Scenario runner API: `{prov.scenario_runner_api}`"]
    body += [
        f"- {name}: `{inp.format}` sha256 `{inp.sha256}`"
        for name, inp in prov.inputs.items()
    ]
    return _section("Provenance", body)


def _render_energy_section(envelope: ScenarioResultEnvelope) -> Lines:
    energy = envelope.estimate.energy if envelope.estimate else None
    if energy is None:
        return []
    body = [
        f"- Feasible: `{str(energy.is_feasible).lower()}`",
        f"- Total energy Wh: `{_fmt(energy.total_energy_wh)}`",
        f"- Battery capacity Wh: `{_fmt(energy.battery_capacity_wh)}`",
        f"- Usable energy Wh: `{_fmt(energy.usable_energy_wh)}`",
        f"- Reserve threshold percent: `{_fmt(energy.reserve_threshold_percent)}`",
        f"- Reserve threshold Wh: `{_fmt(energy.reserve_threshold_wh)}`",
        f"- Reserve at landing Wh: `{_fmt(energy.reserve_at_landing_wh)}`",
        f"- Reserve at landing percent: `{_fmt(energy.reserve_at_landing_percent)}`",
        f"- Energy legs: `{len(energy.legs)}`",
    ]
    return _section("Energy Feasibility", body)


def _render_resource_section(envelope: ScenarioResultEnvelope) -> Lines:
    resource = envelope.estimate.resource if envelope.estimate else None
    if resource is None:
        return []
    body = [
        f"- Feasible: `{str(resource.is_feasible).lower()}`",
        f"- Selected resource: `{resource.selected_resource_id}`",
        f"- Total demand Wh: `{_fmt(resource.total_demand_wh)}`",
        f"- Peak power W: `{_fmt(resource.peak_power_w)}`",
        f"- Systems: `{len(resource.systems)}`",
    ]
    return _section("Resource Feasibility", body)


def _render_link_section(envelope: ScenarioResultEnvelope) -> Lines:
    link = envelope.estimate.link if envelope.estimate else None
    if link is None:
        return []
    body = [
        f"- Feasible: `{str(link.is_feasible).lower()}`",
        f"- Selected link: `{link.selected_link_id}`",
        f"- Required links: `{link.required_link_count}`",
        f"- Available links: `{link.available_link_count}`",
        f"- Systems: `{len(link.systems)}`",
    ]
    return _section("Link Feasibility", body)


def _render_geofence_section(envelope: ScenarioResultEnvelope) -> Lines:
    geofence = envelope.estimate.geofence if envelope.estimate else None
    if geofence is None:
        return []
    body = [
        f"- Feasible: `{str(geofence.is_feasible).lower()}`",
        f"- Checked zones: `{geofence.checked_zone_count}`",
        f"- Checked legs: `{geofence.checked_leg_count}`",
        f"- Conflicts: `{len(geofence.conflicts)}`",
    ]
    return _section("Geofence Feasibility", body)


def _render_landing_zone_section(envelope: ScenarioResultEnvelope) -> Lines:
    landing_zone = envelope.estimate.landing_zone if envelope.estimate else None
    if landing_zone is None:
        return []
    body = [
        f"- Feasible: `{str(landing_zone.is_feasible).lower()}`",
        f"- Checked zones: `{landing_zone.checked_zone_count}`",
        f"- Checked states: `{landing_zone.checked_state_count}`",
        f"- Max allowed distance m: `{_fmt(landing_zone.max_allowed_distance_m) if landing_zone.max_allowed_distance_m is not None else 'none'}`",
        f"- Reserve threshold Wh: `{_fmt(landing_zone.reserve_threshold_wh)}`",
    ]
    return _section("Landing-Zone Reachability", body)


def _fmt_duration(total_s: float) -> str:
    minutes = int(total_s // 60)
    seconds = int(total_s % 60)
    return f"{minutes}m {seconds:02d}s ({_fmt(total_s)} s)"


def _render_estimate_summary(envelope: ScenarioResultEnvelope) -> Lines:
    estimate = envelope.estimate
    if estimate is None:
        return []
    body = [
        f"- Horizontal distance m: `{_fmt(estimate.total_horizontal_distance_m)}`",
        f"- Vertical distance m: `{_fmt(estimate.total_vertical_distance_m)}`",
        f"- Path distance m: `{_fmt(estimate.total_path_distance_m)}`",
        f"- Time: `{_fmt_duration(estimate.total_time_s)}`",
        f"- Legs: `{len(estimate.legs)}`",
    ]
    return _section("Estimate Summary", body)


def _render_warnings_section(envelope: ScenarioResultEnvelope) -> Lines:
    warnings = envelope.estimate.warnings if envelope.estimate is not None else []
    if not warnings:
        return []
    body = [f"- `{w.code}`: {w.message}" for w in warnings]
    return _section("Warnings", body)


_SECTION_RENDERERS: list[SectionRenderer] = [
    _render_assertion_results,
    _render_timeline,
    _render_event_outcomes,
    _render_determinism,
    _render_provenance,
    _render_estimate_summary,
    _render_energy_section,
    _render_resource_section,
    _render_link_section,
    _render_geofence_section,
    _render_landing_zone_section,
    _render_warnings_section,
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _assertion_counts(results: list[ScenarioAssertionResult]) -> str:
    n_pass = sum(1 for r in results if r.outcome == AssertionOutcome.PASSED)
    n_fail = sum(1 for r in results if r.outcome == AssertionOutcome.FAILED)
    n_skip = sum(1 for r in results if r.outcome == AssertionOutcome.SKIPPED)
    n_unsupported = sum(1 for r in results if r.outcome == AssertionOutcome.UNSUPPORTED)
    parts = [f"{n_pass} passed", f"{n_fail} failed", f"{n_skip} skipped"]
    if n_unsupported:
        parts.append(f"{n_unsupported} unsupported")
    return ", ".join(parts)


def render_scenario_markdown(envelope: ScenarioResultEnvelope) -> str:
    """Render a scenario result envelope as a human-readable Markdown report."""
    assertion_summary = _assertion_counts(envelope.assertion_results)
    header: Lines = [
        "# Scenario Report",
        "",
        f"- Scenario: `{envelope.scenario_id}`",
        f"- Status: `{envelope.status}`",
        f"- Assertions: {assertion_summary}",
        f"- Envelope schema: `{envelope.schema_version}`",
        f"- Tool version: `{envelope.tool_version}`",
    ]

    body: Lines = []
    for renderer in _SECTION_RENDERERS:
        body.extend(renderer(envelope))

    return "\n".join([*header, *body, ""])
