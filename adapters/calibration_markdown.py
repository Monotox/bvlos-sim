"""Calibration profile Markdown report renderer."""

from __future__ import annotations

from schemas.calibration import CalibrationProfile


def render_calibration_markdown(profile: CalibrationProfile) -> str:
    """Render a calibration profile as a Markdown document."""
    lines: list[str] = []
    lines.append(f"# Calibration Profile: {profile.calibration_id}")
    lines.append("")
    lines.append(f"- Base vehicle: `{profile.base_vehicle_id}`")
    lines.append(f"- Dataset: `{profile.provenance.calibration_dataset_version}`")
    lines.append(f"- Source traces: {_join(profile.provenance.source_trace_ids)}")
    if profile.provenance.validation_report_ids:
        lines.append(
            f"- Validation reports: {_join(profile.provenance.validation_report_ids)}"
        )
    lines.append(f"- Tool version: {profile.provenance.tool_version}")
    lines.append("")

    lines.append("## Fitted parameters")
    lines.append("")
    if profile.parameters:
        lines.append("| Parameter | Fitted | Unit | Range | Spread | Samples |")
        lines.append("|---|---|---|---|---|---|")
        for record in profile.parameters:
            value_range = f"{record.confidence_low:.2f}–{record.confidence_high:.2f}"
            lines.append(
                f"| {record.parameter.value} | {record.fitted_value:.2f} "
                f"| {record.unit} | {value_range} "
                f"| {record.spread:.2f} | {record.sample_count} |"
            )
        lines.append("")
        lines.append("### Derivation and conditions")
        lines.append("")
        for record in profile.parameters:
            conditions = (
                "; ".join(record.applicable_conditions)
                if record.applicable_conditions
                else "—"
            )
            lines.append(
                f"- `{record.parameter.value}`: {record.derivation} "
                f"(conditions: {conditions})"
            )
        lines.append("")
    else:
        lines.append("No parameters could be fit from the supplied traces.")
        lines.append("")

    if profile.notes:
        lines.append("## Notes")
        lines.append("")
        for note in profile.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _join(values: list[str]) -> str:
    return ", ".join(f"`{value}`" for value in values) if values else "—"


__all__ = ["render_calibration_markdown"]
