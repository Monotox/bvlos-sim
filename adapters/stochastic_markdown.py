"""Markdown rendering for stochastic propagation reports."""

import math

from adapters.stochastic_envelope import StochasticResultEnvelope
from schemas.stochastic import PropagationTimelinePoint


def _fmt(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _timeline_points(
    envelope: StochasticResultEnvelope,
) -> list[PropagationTimelinePoint]:
    points = envelope.result.timeline
    if len(points) <= 20:
        return points
    stride = math.ceil(len(points) / 20)
    return points[::stride][:20]


def render_stochastic_markdown(envelope: StochasticResultEnvelope) -> str:
    r = envelope.result
    lines: list[str] = []

    lines.append(f"# Stochastic Propagation Report: {r.propagation_id}")
    lines.append("")
    lines.append(f"**Schema Version:** {envelope.schema_version}  ")
    lines.append(f"**Tool Version:** {envelope.tool_version}  ")
    lines.append(f"**Seed:** {r.seed}  ")
    lines.append(f"**Samples:** {r.sample_count}  ")
    lines.append(f"**dt_s:** {_fmt(r.dt_s)}  ")
    lines.append(f"**Feasibility Rate:** {r.feasibility_rate * 100:.1f}%  ")

    lines.append("")
    lines.append("## Timeline")
    lines.append("")
    lines.append(
        "| Elapsed (s) | Energy Mean (Wh) | Energy Std | P(reserve violation) |"
    )
    lines.append("|-------------|------------------|------------|----------------------|")
    for point in _timeline_points(envelope):
        lines.append(
            f"| {_fmt(point.elapsed_time_s)} "
            f"| {_fmt(point.energy_remaining_wh.mean)} "
            f"| {_fmt(point.energy_remaining_wh.std)} "
            f"| {_fmt(point.p_reserve_violation, 3)} |"
        )

    lines.append("")
    lines.append("## Baseline (Deterministic)")
    lines.append("")
    b = r.baseline
    lines.append(f"**Status:** {b.status}  ")
    lines.append(f"**Total Time:** {_fmt(b.total_time_s)} s  ")
    if b.energy is not None:
        lines.append(
            f"**Reserve at Landing:** {_fmt(b.energy.reserve_at_landing_wh)} Wh "
            f"({_fmt(b.energy.reserve_at_landing_percent)}%)  "
        )
    else:
        lines.append("**Reserve at Landing:** n/a  ")

    lines.append("")
    return "\n".join(lines)
