"""Markdown rendering for Monte Carlo uncertainty reports."""

from bvlos_sim.estimator.core.uncertainty import SampledOutputStats
from bvlos_sim.adapters.uncertainty_envelope import UncertaintyResultEnvelope


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

    lines.append(f"# Diagnostic Uncertainty Parameter Sweep: {r.uncertainty_id}")
    lines.append("")
    lines.append("**Operational Feasibility Assessed:** No  ")
    lines.append(
        "**Scope:** Diagnostic sampled-input sensitivity; not a landing, control, "
        "or operational-feasibility probability.  "
    )
    lines.append(
        "**Conditioning:** Summary distributions include modeled-pass samples only.  "
    )
    lines.append("")
    lines.append(f"**Schema Version:** {envelope.schema_version}  ")
    lines.append(f"**Tool Version:** {envelope.tool_version}  ")
    lines.append(f"**Seed:** {r.seed}  ")

    lines.append(f"**Requested Samples:** {r.sample_count}  ")
    lines.append(f"**Modeled-Pass Samples:** {r.modeled_pass_sample_count}  ")
    lines.append(f"**Infeasible Samples:** {r.infeasible_sample_count}  ")
    lines.append(f"**Failed Samples:** {r.failed_sample_count}  ")

    if r.modeled_constraint_pass_rate is not None:
        lines.append(
            "**Modeled Constraint Pass Rate:** "
            f"{r.modeled_constraint_pass_rate * 100:.1f}%  "
        )
    else:
        lines.append("**Modeled Constraint Pass Rate:** n/a  ")

    lines.append("")
    lines.append("## Summary Statistics")
    lines.append("")
    lines.append("| Metric | Mean | Std | Min | P5 | P50 | P95 | Max |")
    lines.append("|--------|------|-----|-----|----|-----|-----|-----|")
    lines.append(_stats_row("Conditional Mission Time (s)", r.total_time_s))
    lines.append(
        _stats_row("Conditional Mission-End Energy (Wh)", r.reserve_at_mission_end_wh)
    )
    lines.append(
        _stats_row(
            "Conditional Mission-End Energy (%)",
            r.reserve_at_mission_end_percent,
        )
    )

    lines.append("")
    lines.append("## Baseline (Deterministic)")
    lines.append("")

    def _fmt_duration(total_s: float) -> str:
        minutes = int(total_s // 60)
        seconds = int(total_s % 60)
        return f"{minutes}m {seconds:02d}s ({_fmt(total_s)} s)"

    b = r.baseline
    lines.append(f"**Status:** {b.status}  ")
    lines.append(f"**Total Time:** {_fmt_duration(b.total_time_s)}  ")
    lines.append(f"**Total Path Distance:** {_fmt(b.total_path_distance_m)} m  ")
    if b.energy is not None:
        lines.append(
            f"**Modeled Energy Check Passed:** {str(b.energy.is_feasible).lower()}  "
        )
        lines.append(
            "**Modeled Energy at Mission End:** "
            f"{_fmt(b.energy.reserve_at_landing_wh)} Wh "
            f"({_fmt(b.energy.reserve_at_landing_percent)}%)  "
        )
    else:
        lines.append("**Energy:** not available  ")

    lines.append("")
    return "\n".join(lines)
