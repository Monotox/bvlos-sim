"""Deterministic flight phase segmentation over normalized traces."""

from __future__ import annotations

from schemas.flight_log import FlightTraceRecord, NormalizedFlightTrace
from schemas.phase_segment import (
    PHASE_SEGMENT_SCHEMA_VERSION,
    PhaseSegment,
    PhaseSegmentResult,
    SegmentationMetadata,
    TracePhase,
)

# ---------------------------------------------------------------------------
# Algorithm identifier
# ---------------------------------------------------------------------------

SEGMENTATION_METHOD = "flight_mode_priority"

# ---------------------------------------------------------------------------
# Flight mode → TracePhase (direct mappings)
#
# Keys cover both mode vocabularies the ingestion adapters emit into
# FlightTraceRecord.flight_mode:
#   - ArduPilot DataFlash MODE message names (TAKEOFF, RTL, LAND, ...)
#   - PX4 nav_state names produced by the ULog adapter's _PX4_NAV_STATES
#     table (AUTO_RTL, AUTO_LAND, AUTO_LOITER, ...)
# Fail-closed: any mode absent from both this map and the kinematic dispatch
# set below segments as UNKNOWN — manual/acro/stabilized flight, flight
# termination, external modes, and unrecognized nav_state numbers
# (NAV_STATE_<n>) are never guessed into a phase.
# ---------------------------------------------------------------------------

_MODE_PHASE_MAP: dict[str, TracePhase] = {
    # ArduPilot
    "TAKEOFF": TracePhase.TAKEOFF,
    "RTL": TracePhase.RTL,
    "SMART_RTL": TracePhase.RTL,
    "LAND": TracePhase.LANDING,
    "LOITER": TracePhase.LOITER,
    "LOITER_UNLIMITED": TracePhase.LOITER,
    "LOITER_TO_ALT": TracePhase.LOITER,
    "POSHOLD": TracePhase.LOITER,
    # PX4 nav_state names
    "AUTO_TAKEOFF": TracePhase.TAKEOFF,
    "AUTO_VTOL_TAKEOFF": TracePhase.TAKEOFF,
    "AUTO_RTL": TracePhase.RTL,
    "AUTO_LAND": TracePhase.LANDING,
    "AUTO_PRECLAND": TracePhase.LANDING,
    # PX4 Descend failsafe: controlled descent to touchdown without a
    # position setpoint — a landing, not free flight.
    "DESCEND": TracePhase.LANDING,
    "AUTO_LOITER": TracePhase.LOITER,
    "ORBIT": TracePhase.LOITER,
}

# Modes that have no direct phase but delegate to kinematic rules: the vehicle
# flies an arbitrary trajectory, so the phase depends on its actual motion.
# ArduPilot: AUTO (mission) and GUIDED. PX4: AUTO_MISSION (mission),
# OFFBOARD (companion-computer guidance), AUTO_FOLLOW_TARGET (target tracking).
_KINEMATIC_DISPATCH_MODES: frozenset[str] = frozenset(
    {
        "AUTO",
        "GUIDED",
        "GUIDED_NOGPS",
        "AUTO_MISSION",
        "OFFBOARD",
        "AUTO_FOLLOW_TARGET",
    }
)

# ---------------------------------------------------------------------------
# Estimator LegPhase mapping (string values, no estimator import required)
# ---------------------------------------------------------------------------

_ESTIMATOR_PHASE_MAP: dict[TracePhase, str] = {
    TracePhase.TAKEOFF: "vertical_takeoff",
    TracePhase.TRANSIT: "transit",
    TracePhase.LOITER: "loiter_dwell",
    TracePhase.LANDING: "landing_transit",
    TracePhase.RTL: "rtl_transit",
}

# ---------------------------------------------------------------------------
# Kinematic thresholds
# ---------------------------------------------------------------------------

# Vertical rate (m/s) above which a record is classified as climbing or descending.
CLIMB_VERT_RATE_MPS: float = 0.5
# Groundspeed (m/s) below which a record is classified as loitering / hovering.
LOITER_SPEED_MPS: float = 1.5
# Groundspeed (m/s) at or above which a record is classified as transiting.
TRANSIT_SPEED_MPS: float = 3.0


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def segment_trace(trace: NormalizedFlightTrace) -> PhaseSegmentResult:
    """Segment a normalized flight trace into contiguous flight phases.

    Phase assignment is deterministic: same input always produces the same output.
    Records that cannot be classified are reported with TracePhase.UNKNOWN.
    """
    records = trace.records

    if not records:
        return PhaseSegmentResult(
            schema_version=PHASE_SEGMENT_SCHEMA_VERSION,
            trace_id=trace.trace_id,
            segments=[],
            metadata=SegmentationMetadata(
                method=SEGMENTATION_METHOD,
                source_fields_used=[],
                unknown_record_count=0,
            ),
        )

    vert_rates = _compute_vert_rates(records)
    phases = [
        _assign_phase(record, vert_rate)
        for record, vert_rate in zip(records, vert_rates, strict=True)
    ]
    phases = _smooth(phases)

    segments = _encode_segments(records, phases)
    unknown_count = sum(1 for p in phases if p == TracePhase.UNKNOWN)

    return PhaseSegmentResult(
        schema_version=PHASE_SEGMENT_SCHEMA_VERSION,
        trace_id=trace.trace_id,
        segments=segments,
        metadata=SegmentationMetadata(
            method=SEGMENTATION_METHOD,
            source_fields_used=_source_fields(records),
            unknown_record_count=unknown_count,
        ),
    )


# ---------------------------------------------------------------------------
# Phase assignment
# ---------------------------------------------------------------------------


def _assign_phase(record: FlightTraceRecord, vert_rate: float | None) -> TracePhase:
    mode = record.flight_mode
    if mode is not None:
        if mode in _MODE_PHASE_MAP:
            return _MODE_PHASE_MAP[mode]
        if mode not in _KINEMATIC_DISPATCH_MODES:
            return TracePhase.UNKNOWN
    return _kinematic_phase(record, vert_rate)


def _kinematic_phase(record: FlightTraceRecord, vert_rate: float | None) -> TracePhase:
    speed = record.groundspeed_mps

    if vert_rate is not None and abs(vert_rate) >= CLIMB_VERT_RATE_MPS:
        slow = speed is None or speed < LOITER_SPEED_MPS
        if vert_rate > 0:
            return TracePhase.TAKEOFF if slow else TracePhase.CLIMB
        return TracePhase.LANDING if slow else TracePhase.DESCENT

    if speed is not None:
        # Below the loiter ceiling → loiter; at or above it → transit. The
        # ambiguous band between LOITER_SPEED_MPS and TRANSIT_SPEED_MPS is split at
        # its midpoint so steady slow movement is never left unclassified.
        loiter_transit_boundary = (LOITER_SPEED_MPS + TRANSIT_SPEED_MPS) / 2.0
        if speed < loiter_transit_boundary:
            return TracePhase.LOITER
        return TracePhase.TRANSIT

    return TracePhase.UNKNOWN


# ---------------------------------------------------------------------------
# Vertical rate computation (finite differences)
# ---------------------------------------------------------------------------


def _compute_vert_rates(records: list[FlightTraceRecord]) -> list[float | None]:
    n = len(records)
    rates: list[float | None] = [None] * n
    if n < 2:
        return rates

    # Forward difference for the first record.
    r0, r1 = records[0], records[1]
    if r0.alt_amsl_m is not None and r1.alt_amsl_m is not None:
        dt = r1.timestamp_s - r0.timestamp_s
        if dt > 0:
            rates[0] = (r1.alt_amsl_m - r0.alt_amsl_m) / dt

    # Central difference for interior records.
    for i in range(1, n - 1):
        prev, nxt = records[i - 1], records[i + 1]
        if prev.alt_amsl_m is not None and nxt.alt_amsl_m is not None:
            dt = nxt.timestamp_s - prev.timestamp_s
            if dt > 0:
                rates[i] = (nxt.alt_amsl_m - prev.alt_amsl_m) / dt

    # Backward difference for the last record.
    rm1, rn = records[-2], records[-1]
    if rm1.alt_amsl_m is not None and rn.alt_amsl_m is not None:
        dt = rn.timestamp_s - rm1.timestamp_s
        if dt > 0:
            rates[-1] = (rn.alt_amsl_m - rm1.alt_amsl_m) / dt

    return rates


# ---------------------------------------------------------------------------
# Smoothing and segment encoding
# ---------------------------------------------------------------------------


def _smooth(phases: list[TracePhase]) -> list[TracePhase]:
    """Absorb single-record phase blips into their surrounding phase.

    A lone record that differs from its two neighbours is replaced with the
    neighbour phase, eliminating spurious one-sample transitions from sensor noise.
    """
    if len(phases) < 3:
        return phases
    result = list(phases)
    for i in range(1, len(result) - 1):
        if result[i - 1] == result[i + 1] and result[i] != result[i - 1]:
            result[i] = result[i - 1]
    return result


def _encode_segments(
    records: list[FlightTraceRecord],
    phases: list[TracePhase],
) -> list[PhaseSegment]:
    segments: list[PhaseSegment] = []
    start = 0
    for i in range(1, len(phases)):
        if phases[i] != phases[start]:
            segments.append(_make_segment(records, phases, start, i - 1))
            start = i
    segments.append(_make_segment(records, phases, start, len(phases) - 1))
    return segments


def _make_segment(
    records: list[FlightTraceRecord],
    phases: list[TracePhase],
    start: int,
    end: int,
) -> PhaseSegment:
    phase = phases[start]
    return PhaseSegment(
        phase=phase,
        start_index=start,
        end_index=end,
        start_time_s=records[start].timestamp_s,
        end_time_s=records[end].timestamp_s,
        record_count=end - start + 1,
        estimator_leg_phase=_ESTIMATOR_PHASE_MAP.get(phase),
    )


# ---------------------------------------------------------------------------
# Source-field detection
# ---------------------------------------------------------------------------


def _source_fields(records: list[FlightTraceRecord]) -> list[str]:
    fields: set[str] = set()
    for record in records:
        if record.flight_mode is not None:
            fields.add("flight_mode")
        if record.groundspeed_mps is not None:
            fields.add("groundspeed_mps")
        if record.alt_amsl_m is not None:
            fields.add("alt_amsl_m")
    return sorted(fields)


__all__ = [
    "CLIMB_VERT_RATE_MPS",
    "LOITER_SPEED_MPS",
    "SEGMENTATION_METHOD",
    "TRANSIT_SPEED_MPS",
    "segment_trace",
]
