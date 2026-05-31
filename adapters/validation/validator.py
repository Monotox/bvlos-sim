"""Deterministic predicted-vs-observed validation metrics.

Bridges an estimator ``MissionEstimate`` (predicted) with a normalized flight
trace and its phase segmentation (observed). The phase bridge is the
``estimator_leg_phase`` value already attached to each ``PhaseSegment``: predicted
legs are grouped by ``LegEstimate.phase`` and observed segments by their mapped
estimator leg phase, so the two sides line up on identical keys.
"""

from __future__ import annotations

from collections import defaultdict

from pyproj import Geod

from estimator.core.results import LegEstimate, MissionEstimate
from schemas.flight_log import FlightTraceRecord, NormalizedFlightTrace
from schemas.phase_segment import PhaseSegment, PhaseSegmentResult
from schemas.validation import (
    VALIDATION_REPORT_SCHEMA_VERSION,
    MetricComparison,
    MissionValidationMetrics,
    PhaseValidation,
    ValidationReport,
)

# Same WGS-84 geodesic model the estimator uses for route distances.
_GEOD = Geod(ellps="WGS84")


def build_validation_report(
    *,
    estimate: MissionEstimate,
    trace: NormalizedFlightTrace,
    segments: PhaseSegmentResult,
    validation_id: str,
    tool_version: str,
) -> ValidationReport:
    """Compare a predicted mission estimate against an observed flight trace.

    Raises ValueError if the trace and segmentation describe different traces.
    """
    if segments.trace_id != trace.trace_id:
        raise ValueError(
            f"segmentation trace_id ({segments.trace_id}) does not match "
            f"trace_id ({trace.trace_id})"
        )

    records = trace.records
    notes: list[str] = []

    mission_metrics = _mission_metrics(estimate, records, notes)
    phase_validations = _phase_validations(estimate, records, segments, notes)

    return ValidationReport(
        schema_version=VALIDATION_REPORT_SCHEMA_VERSION,
        validation_id=validation_id,
        tool_version=tool_version,
        trace_id=trace.trace_id,
        mission_ref=trace.mission_ref,
        observed_record_count=len(records),
        mission_metrics=mission_metrics,
        phase_validations=phase_validations,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# Mission-level metrics
# ---------------------------------------------------------------------------


def _mission_metrics(
    estimate: MissionEstimate,
    records: list[FlightTraceRecord],
    notes: list[str],
) -> MissionValidationMetrics:
    observed_time = _observed_duration_s(records)
    observed_distance = _observed_horizontal_distance_m(records)
    observed_speed = _mean(
        [
            record.groundspeed_mps
            for record in records
            if record.groundspeed_mps is not None
        ]
    )
    observed_reserve = records[-1].battery_remaining_pct if records else None

    predicted_speed = _time_weighted_groundspeed(estimate.legs)
    predicted_reserve = (
        estimate.energy.reserve_at_landing_percent
        if estimate.energy is not None
        else None
    )

    if observed_speed is None:
        notes.append(
            "Observed mean groundspeed unavailable: no groundspeed in trace records."
        )
    if observed_reserve is None:
        notes.append(
            "Observed reserve unavailable: no battery-remaining percent in trace."
        )
    if predicted_reserve is None:
        notes.append("Predicted reserve unavailable: estimate has no energy model.")

    return MissionValidationMetrics(
        time_s=MetricComparison.build(estimate.total_time_s, observed_time),
        horizontal_distance_m=MetricComparison.build(
            estimate.total_horizontal_distance_m, observed_distance
        ),
        mean_groundspeed_mps=MetricComparison.build(predicted_speed, observed_speed),
        reserve_percent=MetricComparison.build(predicted_reserve, observed_reserve),
    )


# ---------------------------------------------------------------------------
# Per-phase metrics
# ---------------------------------------------------------------------------


def _phase_validations(
    estimate: MissionEstimate,
    records: list[FlightTraceRecord],
    segments: PhaseSegmentResult,
    notes: list[str],
) -> list[PhaseValidation]:
    predicted = _predicted_by_phase(estimate.legs)
    observed = _observed_by_phase(records, segments.segments)
    _note_unmapped_observed(segments.segments, notes)

    validations: list[PhaseValidation] = []
    for phase in sorted(predicted.keys() | observed.keys()):
        pred = predicted.get(phase)
        obs = observed.get(phase)
        validations.append(
            PhaseValidation(
                phase=phase,
                time_s=MetricComparison.build(
                    pred.time_s if pred else None,
                    obs.time_s if obs else None,
                ),
                mean_groundspeed_mps=MetricComparison.build(
                    pred.mean_groundspeed_mps if pred else None,
                    obs.mean_groundspeed_mps if obs else None,
                ),
                predicted_leg_count=pred.count if pred else 0,
                observed_segment_count=obs.count if obs else 0,
            )
        )
    return validations


class _PhaseAggregate:
    """Accumulated time, weighted speed, and count for one phase."""

    __slots__ = ("time_s", "_speed_weight", "_speed_sum", "count")

    def __init__(self) -> None:
        self.time_s = 0.0
        self._speed_weight = 0.0
        self._speed_sum = 0.0
        self.count = 0

    def add_speed_sample(self, speed: float, weight: float) -> None:
        self._speed_sum += speed * weight
        self._speed_weight += weight

    @property
    def mean_groundspeed_mps(self) -> float | None:
        if self._speed_weight == 0.0:
            return None
        return self._speed_sum / self._speed_weight


def _predicted_by_phase(legs: list[LegEstimate]) -> dict[str, _PhaseAggregate]:
    by_phase: dict[str, _PhaseAggregate] = defaultdict(_PhaseAggregate)
    for leg in legs:
        agg = by_phase[leg.phase.value]
        agg.time_s += leg.time_s
        agg.count += 1
        if leg.groundspeed_mps is not None:
            agg.add_speed_sample(leg.groundspeed_mps, leg.time_s)
    return dict(by_phase)


def _observed_by_phase(
    records: list[FlightTraceRecord],
    segments: list[PhaseSegment],
) -> dict[str, _PhaseAggregate]:
    by_phase: dict[str, _PhaseAggregate] = defaultdict(_PhaseAggregate)
    for segment in segments:
        if segment.estimator_leg_phase is None:
            continue
        agg = by_phase[segment.estimator_leg_phase]
        agg.time_s += segment.end_time_s - segment.start_time_s
        agg.count += 1
        for record in records[segment.start_index : segment.end_index + 1]:
            if record.groundspeed_mps is not None:
                agg.add_speed_sample(record.groundspeed_mps, 1.0)
    return dict(by_phase)


def _note_unmapped_observed(segments: list[PhaseSegment], notes: list[str]) -> None:
    unmapped: dict[str, float] = defaultdict(float)
    for segment in segments:
        if segment.estimator_leg_phase is None:
            unmapped[segment.phase.value] += segment.end_time_s - segment.start_time_s
    for phase in sorted(unmapped):
        notes.append(
            f"Observed phase '{phase}' has no estimator counterpart "
            f"({unmapped[phase]:.1f} s excluded from per-phase comparison)."
        )


# ---------------------------------------------------------------------------
# Observed-quantity helpers
# ---------------------------------------------------------------------------


def _observed_duration_s(records: list[FlightTraceRecord]) -> float | None:
    if len(records) < 2:
        return None
    return records[-1].timestamp_s - records[0].timestamp_s


def _observed_horizontal_distance_m(records: list[FlightTraceRecord]) -> float | None:
    if len(records) < 2:
        return None
    total = 0.0
    for prev, nxt in zip(records, records[1:], strict=False):
        _, _, step_m = _GEOD.inv(prev.lon_deg, prev.lat_deg, nxt.lon_deg, nxt.lat_deg)
        total += step_m
    return total


def _time_weighted_groundspeed(legs: list[LegEstimate]) -> float | None:
    weight = 0.0
    total = 0.0
    for leg in legs:
        if leg.groundspeed_mps is not None and leg.time_s > 0.0:
            total += leg.groundspeed_mps * leg.time_s
            weight += leg.time_s
    return total / weight if weight > 0.0 else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


__all__ = ["build_validation_report"]
