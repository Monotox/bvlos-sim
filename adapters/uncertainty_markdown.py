"""Markdown rendering for Monte Carlo uncertainty reports."""

from estimator.core.uncertainty import SampledOutputStats
from adapters.uncertainty_envelope import UncertaintyResultEnvelope


def _fmt(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _stats_row(label: str, stats: SampledOutputStats | None) -> str:
    if stats is None:
        return f"| {label} | — | — | — | — | — | — | — |"
    return (
        f"| {label} "
        f"| {_fmt(stats.mean)} "
        f"| {_fmt(stats.std)} "
        f"| {_fmt(stats.min)} "
        f"| {_fmt(stats.p5)} "
        f"| {_fmt(stats.p50)} "
        f"| {_fmt(stats.p95)} "
        f"| {_fmt(stats.max)} |"
    )


def render_uncertainty_markdown(envelope: UncertaintyResultEnvelope) -> str:
    r = envelope.result
    lines: list[str] = []

    lines.append(f"# Uncertainty Report: {r.uncertainty_id}")
    lines.append("")
    lines.append(f"**Schema Version:** {envelope.schema_version}  ")
    lines.append(f"**Tool Version:** {envelope.tool_version}  ")
    lines.append(f"**Seed:** {r.seed}  ")

    completed_str = f"{r.completed_sample_count} completed"
    if r.failed_sample_count > 0:
        completed_str += f", {r.failed_sample_count} failed"
    lines.append(f"**Samples:** {r.sample_count} ({completed_str})  ")

    if r.feasibility_rate is not None:
        lines.append(f"**Energy Feasibility Rate:** {r.feasibility_rate * 100:.1f}%  ")
    else:
        lines.append("**Energy Feasibility Rate:** n/a  ")

    lines.append("")
    lines.append("## Summary Statistics")
    lines.append("")
    lines.append("| Metric | Mean | Std | Min | P5 | P50 | P95 | Max |")
    lines.append("|--------|------|-----|-----|----|-----|-----|-----|")
    lines.append(_stats_row("Total Time (s)", r.total_time_s))
    lines.append(_stats_row("Reserve at Landing (Wh)", r.reserve_at_landing_wh))
    lines.append(_stats_row("Reserve at Landing (%)", r.reserve_at_landing_percent))

    lines.append("")
    lines.append("## Baseline (Deterministic)")
    lines.append("")
    b = r.baseline
    lines.append(f"**Status:** {b.status}  ")
    lines.append(f"**Total Time:** {_fmt(b.total_time_s)} s  ")
    lines.append(f"**Total Path Distance:** {_fmt(b.total_path_distance_m)} m  ")
    if b.energy is not None:
        lines.append(f"**Energy Feasible:** {str(b.energy.is_feasible).lower()}  ")
        lines.append(
            f"**Reserve at Landing:** {_fmt(b.energy.reserve_at_landing_wh)} Wh "
            f"({_fmt(b.energy.reserve_at_landing_percent)}%)  "
        )
    else:
        lines.append("**Energy:** not available  ")

    lines.append("")
    return "\n".join(lines)
