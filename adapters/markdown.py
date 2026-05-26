"""Markdown rendering adapter for estimator result envelopes."""

from adapters.canonical_json import format_canonical_float
from adapters.envelope import EstimatorResultEnvelope


def _fmt(value: float) -> str:
    return format_canonical_float(value)


def render_envelope_markdown(envelope: EstimatorResultEnvelope) -> str:
    lines: list[str] = [
        "# Estimator Report",
        "",
        f"- Status: `{envelope.status}`",
        f"- Envelope schema: `{envelope.schema_version}`",
        f"- Tool version: `{envelope.tool_version}`",
        "",
        "## Result Validity",
        "",
        f"- Complete: `{str(envelope.result_validity.is_complete).lower()}`",
        f"- Partial: `{str(envelope.result_validity.is_partial).lower()}`",
        f"- Valid for full mission: `{str(envelope.result_validity.is_valid_for_full_mission).lower()}`",
        f"- Scope: `{envelope.result_validity.scope}`",
    ]

    if envelope.result_validity.invalidated_fields:
        lines.extend(
            [
                "",
                "### Invalidated Fields",
                "",
                *[
                    f"- `{field}`"
                    for field in envelope.result_validity.invalidated_fields
                ],
            ]
        )
    if envelope.result_validity.unavailable_fields:
        lines.extend(
            [
                "",
                "### Unavailable Fields",
                "",
                *[
                    f"- `{field}`"
                    for field in envelope.result_validity.unavailable_fields
                ],
            ]
        )

    lines.extend(["", "## Diagnostics", ""])
    if envelope.diagnostics:
        for diagnostic in envelope.diagnostics:
            lines.append(
                f"- `{diagnostic.level}` `{diagnostic.code}`: {diagnostic.message}"
            )
    else:
        lines.append("- None")

    lines.extend(["", "## Assumptions", ""])
    lines.extend(f"- {assumption}" for assumption in envelope.assumptions)

    lines.extend(["", "## Provenance", ""])
    lines.append(f"- Estimator API: `{envelope.provenance.estimator_api}`")
    for name, input_provenance in envelope.provenance.inputs.items():
        lines.append(
            f"- {name}: `{input_provenance.format}` sha256 `{input_provenance.sha256}`"
        )

    lines.extend(["", "## Determinism", ""])
    lines.append(
        f"- Deterministic: `{str(envelope.determinism_metadata.deterministic).lower()}`"
    )
    lines.append(
        "- External network access used: "
        f"`{str(envelope.determinism_metadata.external_network_access_used).lower()}`"
    )

    if envelope.result is not None:
        lines.extend(
            [
                "",
                "## Estimate Summary",
                "",
                f"- Horizontal distance m: `{_fmt(envelope.result.total_horizontal_distance_m)}`",
                f"- Vertical distance m: `{_fmt(envelope.result.total_vertical_distance_m)}`",
                f"- Path distance m: `{_fmt(envelope.result.total_path_distance_m)}`",
                f"- Time s: `{_fmt(envelope.result.total_time_s)}`",
                f"- Legs: `{len(envelope.result.legs)}`",
            ]
        )

        if envelope.result.energy is not None:
            energy = envelope.result.energy
            lines.extend(
                [
                    "",
                    "## Energy Feasibility",
                    "",
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
            )

        if envelope.result.resource is not None:
            resource = envelope.result.resource
            lines.extend(
                [
                    "",
                    "## Resource Feasibility",
                    "",
                    f"- Feasible: `{str(resource.is_feasible).lower()}`",
                    f"- Selected resource: `{resource.selected_resource_id}`",
                    f"- Total demand Wh: `{_fmt(resource.total_demand_wh)}`",
                    f"- Peak power W: `{_fmt(resource.peak_power_w)}`",
                    f"- Systems: `{len(resource.systems)}`",
                ]
            )

        if envelope.result.link is not None:
            link = envelope.result.link
            lines.extend(
                [
                    "",
                    "## Link Feasibility",
                    "",
                    f"- Feasible: `{str(link.is_feasible).lower()}`",
                    f"- Selected link: `{link.selected_link_id}`",
                    f"- Required links: `{link.required_link_count}`",
                    f"- Available links: `{link.available_link_count}`",
                    f"- Systems: `{len(link.systems)}`",
                ]
            )

        if envelope.result.geofence is not None:
            geofence = envelope.result.geofence
            lines.extend(
                [
                    "",
                    "## Geofence Feasibility",
                    "",
                    f"- Feasible: `{str(geofence.is_feasible).lower()}`",
                    f"- Checked zones: `{geofence.checked_zone_count}`",
                    f"- Checked legs: `{geofence.checked_leg_count}`",
                    f"- Conflicts: `{len(geofence.conflicts)}`",
                ]
            )

        if envelope.result.landing_zone is not None:
            landing_zone = envelope.result.landing_zone
            lines.extend(
                [
                    "",
                    "## Landing-Zone Reachability",
                    "",
                    f"- Feasible: `{str(landing_zone.is_feasible).lower()}`",
                    f"- Checked zones: `{landing_zone.checked_zone_count}`",
                    f"- Checked states: `{landing_zone.checked_state_count}`",
                    f"- Max allowed distance m: `{_fmt(landing_zone.max_allowed_distance_m) if landing_zone.max_allowed_distance_m is not None else 'none'}`",
                    f"- Reserve threshold Wh: `{_fmt(landing_zone.reserve_threshold_wh)}`",
                ]
            )

    lines.append("")
    return "\n".join(lines)
