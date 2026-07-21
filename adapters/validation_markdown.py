"""Predicted-vs-observed validation Markdown report renderer."""

from __future__ import annotations

from schemas.validation import MetricComparison, ValidationReport


def render_validation_markdown(report: ValidationReport) -> str:
    """Render a validation report as a Markdown document."""
    lines: list[str] = []
    lines.append(f"# Validation Report: {report.validation_id}")
    lines.append("")
    lines.append(f"- Trace: `{report.trace_id}`")
    lines.append(f"- Observed records: {report.observed_record_count}")
    if report.mission_ref is not None:
        lines.append(f"- Mission file: `{report.mission_ref.mission_file}`")
        if report.mission_ref.vehicle_file is not None:
            lines.append(f"- Vehicle file: `{report.mission_ref.vehicle_file}`")
    lines.append(f"- Tool version: {report.tool_version}")
    lines.append(f"- Acceptance: **{'PASS' if report.acceptance.passed else 'FAIL'}**")
    lines.append("")

    lines.append("## Acceptance gate")
    lines.append("")
    lines.append("| Metric | Error | Maximum | Result |")
    lines.append("|---|---:|---:|---|")
    for name, limit in report.acceptance.thresholds_pct.items():
        error = report.acceptance.errors_pct.get(name)
        passed = error is not None and error <= limit
        lines.append(
            f"| {name} | {_pct(error)} | {_pct(limit)} | "
            f"{'PASS' if passed else 'FAIL'} |"
        )
    lines.append("")
    for failure in report.acceptance.failures:
        lines.append(f"- {failure}")
    if report.acceptance.failures:
        lines.append("")

    lines.append("## Mission metrics")
    lines.append("")
    lines.append("| Metric | Predicted | Observed | Abs error | % error |")
    lines.append("|---|---|---|---|---|")
    metrics = report.mission_metrics
    lines.append(_metric_row("Flight time (s)", metrics.time_s))
    lines.append(_metric_row("Horizontal distance (m)", metrics.horizontal_distance_m))
    lines.append(_metric_row("Mean groundspeed (m/s)", metrics.mean_groundspeed_mps))
    lines.append(_metric_row("Reserve at landing (%)", metrics.reserve_percent))
    lines.append("")

    if report.phase_validations:
        lines.append("## Per-phase metrics")
        lines.append("")
        lines.append(
            "| Phase | Pred time (s) | Obs time (s) | "
            "Pred gs (m/s) | Obs gs (m/s) | Legs | Segments |"
        )
        lines.append("|---|---|---|---|---|---|---|")
        for phase in report.phase_validations:
            lines.append(
                f"| {phase.phase} "
                f"| {_num(phase.time_s.predicted)} | {_num(phase.time_s.observed)} "
                f"| {_num(phase.mean_groundspeed_mps.predicted)} "
                f"| {_num(phase.mean_groundspeed_mps.observed)} "
                f"| {phase.predicted_leg_count} | {phase.observed_segment_count} |"
            )
        lines.append("")

    if report.notes:
        lines.append("## Notes")
        lines.append("")
        for note in report.notes:
            lines.append(f"- {note}")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"


def _metric_row(label: str, metric: MetricComparison) -> str:
    return (
        f"| {label} | {_num(metric.predicted)} | {_num(metric.observed)} "
        f"| {_num(metric.abs_error)} | {_pct(metric.pct_error)} |"
    )


def _num(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


__all__ = ["render_validation_markdown"]
