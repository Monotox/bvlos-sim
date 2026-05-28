"""Markdown rendering for stochastic propagation reports."""

import math
from collections.abc import Sequence
from typing import TypeVar

from adapters.stochastic_envelope import StochasticResultEnvelope
from schemas.stochastic import (
    CrossTrackStats,
    EstimationErrorTimelinePoint,
    PropagationTimelinePoint,
    StochasticPropagationResult,
)

T = TypeVar("T")
Lines = list[str]


def _fmt(value: float, decimals: int = 2) -> str:
    return f"{value:.{decimals}f}"


def _fmt_duration(total_s: float) -> str:
    minutes = int(total_s // 60)
    seconds = int(total_s % 60)
    return f"{minutes}m {seconds:02d}s ({_fmt(total_s)} s)"


def _sample_points(points: Sequence[T]) -> list[T]:
    if len(points) <= 20:
        return list(points)
    stride = math.ceil(len(points) / 20)
    return list(points[::stride][:20])


def _timeline_points(
    envelope: StochasticResultEnvelope,
) -> list[PropagationTimelinePoint]:
    return _sample_points(envelope.result.timeline)


def _estimation_error_points(
    envelope: StochasticResultEnvelope,
) -> list[EstimationErrorTimelinePoint]:
    return _sample_points(envelope.result.estimation_error_timeline)


def _cross_track_points(
    envelope: StochasticResultEnvelope,
) -> list[CrossTrackStats]:
    return _sample_points(envelope.result.cross_track_timeline)


def _render_header(envelope: StochasticResultEnvelope) -> Lines:
    r = envelope.result
    lines = [
        f"# Stochastic Propagation Report: {r.propagation_id}",
        "",
        f"**Schema Version:** {envelope.schema_version}  ",
        f"**Tool Version:** {envelope.tool_version}  ",
        f"**Seed:** {r.seed}  ",
        f"**Samples:** {r.sample_count}  ",
    ]
    if r.failed_sample_count > 0:
        lines.append(f"**Failed Samples:** {r.failed_sample_count}  ")
    if r.spatial_infeasible_count > 0:
        lines.append(f"**Spatially Infeasible Samples:** {r.spatial_infeasible_count}  ")
    lines.append(f"**dt_s:** {_fmt(r.dt_s)}  ")
    lines.append(f"**Feasibility Rate:** {r.feasibility_rate * 100:.1f}%  ")
    return lines


def _render_timeline(envelope: StochasticResultEnvelope) -> Lines:
    lines = [
        "",
        "## Timeline",
        "",
        "| Elapsed (s) | Energy Mean (Wh) | Energy Std | P(reserve violation) |",
        "|-------------|------------------|------------|----------------------|",
    ]
    for point in _timeline_points(envelope):
        lines.append(
            f"| {_fmt(point.elapsed_time_s)} "
            f"| {_fmt(point.energy_remaining_wh.mean)} "
            f"| {_fmt(point.energy_remaining_wh.std)} "
            f"| {_fmt(point.p_reserve_violation, 3)} |"
        )
    return lines


def _render_estimation_error_timeline(envelope: StochasticResultEnvelope) -> Lines:
    if not envelope.result.estimation_error_timeline:
        return []

    lines = [
        "",
        "## Estimation Error Timeline",
        "",
        "| Elapsed (s) | Pos Error Mean (m) | Pos Error Std | Energy Error Mean (Wh) |",
        "|-------------|---------------------|---------------|------------------------|",
    ]
    for point in _estimation_error_points(envelope):
        lines.append(
            f"| {_fmt(point.elapsed_time_s)} "
            f"| {_fmt(point.position_error_m.mean)} "
            f"| {_fmt(point.position_error_m.std)} "
            f"| {_fmt(point.energy_error_wh.mean)} |"
        )
    return lines


def _render_cross_track_timeline(envelope: StochasticResultEnvelope) -> Lines:
    if not envelope.result.cross_track_timeline:
        return []

    lines = [
        "",
        "## Cross-Track Timeline",
        "",
        "| Elapsed (s) | XTE Mean (m) | XTE Std | Path Excess Mean (m) |",
        "|-------------|--------------|---------|----------------------|",
    ]
    for point in _cross_track_points(envelope):
        lines.append(
            f"| {_fmt(point.elapsed_time_s)} "
            f"| {_fmt(point.cross_track_error_m.mean)} "
            f"| {_fmt(point.cross_track_error_m.std)} "
            f"| {_fmt(point.path_length_excess_m.mean)} |"
        )
    return lines


def _render_reserve_distribution(result: StochasticPropagationResult) -> Lines:
    if result.reserve_at_landing_wh is None:
        return []

    s = result.reserve_at_landing_wh
    return [
        "",
        "## Reserve at Landing Distribution (Wh)",
        "",
        "| Stat | Value (Wh) |",
        "|------|------------|",
        f"| min  | {_fmt(s.min)} |",
        f"| p5   | {_fmt(s.p5)} |",
        f"| p50  | {_fmt(s.p50)} |",
        f"| mean | {_fmt(s.mean)} |",
        f"| p95  | {_fmt(s.p95)} |",
        f"| max  | {_fmt(s.max)} |",
        f"| std  | {_fmt(s.std)} |",
    ]


def _render_baseline(result: StochasticPropagationResult) -> Lines:
    baseline = result.baseline
    lines = [
        "",
        "## Baseline (Deterministic)",
        "",
        f"**Status:** {baseline.status}  ",
        f"**Total Time:** {_fmt_duration(baseline.total_time_s)}  ",
    ]
    if baseline.energy is not None:
        lines.append(
            f"**Reserve at Landing:** {_fmt(baseline.energy.reserve_at_landing_wh)} Wh "
            f"({_fmt(baseline.energy.reserve_at_landing_percent)}%)  "
        )
    else:
        lines.append("**Reserve at Landing:** n/a  ")
    return lines


def render_stochastic_markdown(envelope: StochasticResultEnvelope) -> str:
    lines = _render_header(envelope)
    lines.extend(_render_timeline(envelope))
    lines.extend(_render_estimation_error_timeline(envelope))
    lines.extend(_render_cross_track_timeline(envelope))
    lines.extend(_render_reserve_distribution(envelope.result))
    lines.extend(_render_baseline(envelope.result))
    lines.append("")
    return "\n".join(lines)
