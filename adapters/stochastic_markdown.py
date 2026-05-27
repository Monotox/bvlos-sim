"""Markdown rendering for stochastic propagation reports."""

import math

from adapters.stochastic_envelope import StochasticResultEnvelope
from schemas.stochastic import (
    CrossTrackStats,
    EstimationErrorTimelinePoint,
    PropagationTimelinePoint,
)


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


def _estimation_error_points(
    envelope: StochasticResultEnvelope,
) -> list[EstimationErrorTimelinePoint]:
    points = envelope.result.estimation_error_timeline
    if len(points) <= 20:
        return points
    stride = math.ceil(len(points) / 20)
    return points[::stride][:20]


def _cross_track_points(
    envelope: StochasticResultEnvelope,
) -> list[CrossTrackStats]:
    points = envelope.result.cross_track_timeline
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
    if r.failed_sample_count > 0:
        lines.append(f"**Failed Samples:** {r.failed_sample_count}  ")
    if r.spatial_infeasible_count > 0:
        lines.append(f"**Spatially Infeasible Samples:** {r.spatial_infeasible_count}  ")
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

    if r.estimation_error_timeline:
        lines.append("")
        lines.append("## Estimation Error Timeline")
        lines.append("")
        lines.append(
            "| Elapsed (s) | Pos Error Mean (m) | Pos Error Std | Energy Error Mean (Wh) |"
        )
        lines.append(
            "|-------------|---------------------|---------------|------------------------|"
        )
        for point in _estimation_error_points(envelope):
            lines.append(
                f"| {_fmt(point.elapsed_time_s)} "
                f"| {_fmt(point.position_error_m.mean)} "
                f"| {_fmt(point.position_error_m.std)} "
                f"| {_fmt(point.energy_error_wh.mean)} |"
            )

    if r.cross_track_timeline:
        lines.append("")
        lines.append("## Cross-Track Timeline")
        lines.append("")
        lines.append(
            "| Elapsed (s) | XTE Mean (m) | XTE Std | Path Excess Mean (m) |"
        )
        lines.append(
            "|-------------|--------------|---------|----------------------|"
        )
        for point in _cross_track_points(envelope):
            lines.append(
                f"| {_fmt(point.elapsed_time_s)} "
                f"| {_fmt(point.cross_track_error_m.mean)} "
                f"| {_fmt(point.cross_track_error_m.std)} "
                f"| {_fmt(point.path_length_excess_m.mean)} |"
            )

    if r.reserve_at_landing_wh is not None:
        s = r.reserve_at_landing_wh
        lines.append("")
        lines.append("## Reserve at Landing Distribution (Wh)")
        lines.append("")
        lines.append("| Stat | Value (Wh) |")
        lines.append("|------|------------|")
        lines.append(f"| min  | {_fmt(s.min)} |")
        lines.append(f"| p5   | {_fmt(s.p5)} |")
        lines.append(f"| p50  | {_fmt(s.p50)} |")
        lines.append(f"| mean | {_fmt(s.mean)} |")
        lines.append(f"| p95  | {_fmt(s.p95)} |")
        lines.append(f"| max  | {_fmt(s.max)} |")
        lines.append(f"| std  | {_fmt(s.std)} |")

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
