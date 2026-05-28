"""Markdown rendering adapter for estimator result envelopes."""

from adapters.envelope import EstimatorResultEnvelope
from estimator.core.results import (
    EnergyEstimate,
    GeofenceEstimate,
    LandingZoneEstimate,
    LinkEstimate,
    MissionEstimate,
    ResourceEstimate,
)

Lines = list[str]
_MISSING = "\u2014"


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _fmt_bool(value: bool) -> str:
    return str(value).lower()


def _fmt_duration(total_s: float) -> str:
    minutes = int(total_s // 60)
    seconds = int(total_s % 60)
    return f"{minutes}m {seconds:02d}s ({_fmt(total_s)} s)"


def _fmt_optional_float(value: float | None) -> str:
    if value is None:
        return _MISSING
    return _fmt(value)


def _section(title: str) -> Lines:
    return ["", f"## {title}", ""]


def _render_report_header(envelope: EstimatorResultEnvelope) -> Lines:
    return [
        "# Estimator Report",
        "",
        f"- Status: `{envelope.status}`",
        f"- Envelope schema: `{envelope.schema_version}`",
        f"- Tool version: `{envelope.tool_version}`",
        "",
    ]


def _render_result_validity(envelope: EstimatorResultEnvelope) -> Lines:
    validity = envelope.result_validity
    lines: Lines = [
        "## Result Validity",
        "",
        f"- Complete: `{_fmt_bool(validity.is_complete)}`",
        f"- Partial: `{_fmt_bool(validity.is_partial)}`",
        f"- Valid for full mission: `{_fmt_bool(validity.is_valid_for_full_mission)}`",
        f"- Scope: `{validity.scope}`",
    ]
    lines.extend(_render_field_list("Invalidated Fields", validity.invalidated_fields))
    lines.extend(_render_field_list("Unavailable Fields", validity.unavailable_fields))
    return lines


def _render_field_list(title: str, fields: list[str]) -> Lines:
    if not fields:
        return []
    return ["", f"### {title}", "", *[f"- `{field}`" for field in fields]]


def _render_diagnostics(envelope: EstimatorResultEnvelope) -> Lines:
    lines = _section("Diagnostics")
    if not envelope.diagnostics:
        lines.append("- None")
        return lines

    for diagnostic in envelope.diagnostics:
        lines.append(f"- `{diagnostic.level}` `{diagnostic.code}`: {diagnostic.message}")
    return lines


def _render_assumptions(envelope: EstimatorResultEnvelope) -> Lines:
    lines = _section("Assumptions")
    lines.extend(f"- {assumption}" for assumption in envelope.assumptions)
    return lines


def _render_provenance(envelope: EstimatorResultEnvelope) -> Lines:
    lines = _section("Provenance")
    lines.append(f"- Estimator API: `{envelope.provenance.estimator_api}`")
    for name, input_provenance in envelope.provenance.inputs.items():
        lines.append(
            f"- {name}: `{input_provenance.format}` sha256 "
            f"`{input_provenance.sha256}`"
        )
    return lines


def _render_determinism(envelope: EstimatorResultEnvelope) -> Lines:
    return [
        "",
        "## Determinism",
        "",
        f"- Deterministic: `{_fmt_bool(envelope.determinism_metadata.deterministic)}`",
        "- External network access used: "
        f"`{_fmt_bool(envelope.determinism_metadata.external_network_access_used)}`",
    ]


def _render_estimate_summary(result: MissionEstimate) -> Lines:
    return [
        "",
        "## Estimate Summary",
        "",
        f"- Horizontal distance m: `{_fmt(result.total_horizontal_distance_m)}`",
        f"- Vertical distance m: `{_fmt(result.total_vertical_distance_m)}`",
        f"- Path distance m: `{_fmt(result.total_path_distance_m)}`",
        f"- Time: `{_fmt_duration(result.total_time_s)}`",
        f"- Legs: `{len(result.legs)}`",
    ]


def _energy_by_leg(energy: EnergyEstimate | None) -> dict[int, float]:
    if energy is None:
        return {}
    return {el.leg_index: el.energy_wh for el in energy.legs}


def _render_leg_breakdown(result: MissionEstimate) -> Lines:
    if not result.legs:
        return []

    energy_by_leg = _energy_by_leg(result.energy)
    lines = _section("Leg Breakdown")
    lines.append(
        "| # | ID | Action | Dist m | Time s | Alt m | GS m/s | Wind m/s | Energy Wh |"
    )
    lines.append(
        "|---|-----|--------|-------:|-------:|------:|-------:|---------:|----------:|"
    )
    for leg in result.legs:
        energy_wh = energy_by_leg.get(leg.leg_index)
        energy_str = _fmt(energy_wh) if energy_wh is not None else _MISSING
        leg_id = leg.route_item_id or _MISSING
        lines.append(
            f"| {leg.leg_index} | {leg_id} | {leg.action} "
            f"| {_fmt(leg.path_distance_m)} | {_fmt(leg.time_s)} "
            f"| {_fmt(leg.end_alt_amsl_m)} "
            f"| {_fmt_optional_float(leg.groundspeed_mps)} "
            f"| {_fmt_optional_float(leg.wind_speed_mps)} | {energy_str} |"
        )
    return lines


def _render_energy_feasibility(energy: EnergyEstimate | None) -> Lines:
    if energy is None:
        return []
    return [
        "",
        "## Energy Feasibility",
        "",
        f"- Feasible: `{_fmt_bool(energy.is_feasible)}`",
        f"- Total energy Wh: `{_fmt(energy.total_energy_wh)}`",
        f"- Battery capacity Wh: `{_fmt(energy.battery_capacity_wh)}`",
        f"- Usable energy Wh: `{_fmt(energy.usable_energy_wh)}`",
        f"- Reserve threshold percent: `{_fmt(energy.reserve_threshold_percent)}`",
        f"- Reserve threshold Wh: `{_fmt(energy.reserve_threshold_wh)}`",
        f"- Reserve at landing Wh: `{_fmt(energy.reserve_at_landing_wh)}`",
        f"- Reserve at landing percent: `{_fmt(energy.reserve_at_landing_percent)}`",
        f"- Energy legs: `{len(energy.legs)}`",
    ]


def _render_resource_feasibility(resource: ResourceEstimate | None) -> Lines:
    if resource is None:
        return []
    return [
        "",
        "## Resource Feasibility",
        "",
        f"- Feasible: `{_fmt_bool(resource.is_feasible)}`",
        f"- Selected resource: `{resource.selected_resource_id}`",
        f"- Total demand Wh: `{_fmt(resource.total_demand_wh)}`",
        f"- Peak power W: `{_fmt(resource.peak_power_w)}`",
        f"- Systems: `{len(resource.systems)}`",
    ]


def _render_link_feasibility(link: LinkEstimate | None) -> Lines:
    if link is None:
        return []
    return [
        "",
        "## Link Feasibility",
        "",
        f"- Feasible: `{_fmt_bool(link.is_feasible)}`",
        f"- Selected link: `{link.selected_link_id}`",
        f"- Required links: `{link.required_link_count}`",
        f"- Available links: `{link.available_link_count}`",
        f"- Systems: `{len(link.systems)}`",
    ]


def _render_geofence_feasibility(geofence: GeofenceEstimate | None) -> Lines:
    if geofence is None:
        return []
    return [
        "",
        "## Geofence Feasibility",
        "",
        f"- Feasible: `{_fmt_bool(geofence.is_feasible)}`",
        f"- Checked zones: `{geofence.checked_zone_count}`",
        f"- Checked legs: `{geofence.checked_leg_count}`",
        f"- Conflicts: `{len(geofence.conflicts)}`",
    ]


def _render_landing_zone_reachability(
    landing_zone: LandingZoneEstimate | None,
) -> Lines:
    if landing_zone is None:
        return []
    max_allowed_distance = (
        _fmt(landing_zone.max_allowed_distance_m)
        if landing_zone.max_allowed_distance_m is not None
        else "none"
    )
    return [
        "",
        "## Landing-Zone Reachability",
        "",
        f"- Feasible: `{_fmt_bool(landing_zone.is_feasible)}`",
        f"- Checked zones: `{landing_zone.checked_zone_count}`",
        f"- Checked states: `{landing_zone.checked_state_count}`",
        f"- Max allowed distance m: `{max_allowed_distance}`",
        f"- Reserve threshold Wh: `{_fmt(landing_zone.reserve_threshold_wh)}`",
    ]


def _render_warnings(result: MissionEstimate) -> Lines:
    if not result.warnings:
        return []

    lines = _section("Warnings")
    for warning in result.warnings:
        leg_tag = f" (leg {warning.leg_index})" if warning.leg_index is not None else ""
        lines.append(f"- `{warning.code}`{leg_tag}: {warning.message}")
    return lines


def _render_result_sections(result: MissionEstimate | None) -> Lines:
    if result is None:
        return []

    lines = _render_estimate_summary(result)
    lines.extend(_render_leg_breakdown(result))
    lines.extend(_render_energy_feasibility(result.energy))
    lines.extend(_render_resource_feasibility(result.resource))
    lines.extend(_render_link_feasibility(result.link))
    lines.extend(_render_geofence_feasibility(result.geofence))
    lines.extend(_render_landing_zone_reachability(result.landing_zone))
    lines.extend(_render_warnings(result))
    return lines


def render_envelope_markdown(envelope: EstimatorResultEnvelope) -> str:
    lines = _render_report_header(envelope)
    lines.extend(_render_result_validity(envelope))
    lines.extend(_render_diagnostics(envelope))
    lines.extend(_render_assumptions(envelope))
    lines.extend(_render_provenance(envelope))
    lines.extend(_render_determinism(envelope))
    lines.extend(_render_result_sections(envelope.result))
    lines.append("")
    return "\n".join(lines)
