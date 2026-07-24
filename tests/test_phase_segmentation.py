"""Tests for flight phase segmentation (Ticket 081)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from bvlos_sim.adapters.phase_segmentation import (
    LOITER_SPEED_MPS,
    SEGMENTATION_METHOD,
    TRANSIT_SPEED_MPS,
    load_phase_segments,
    segment_trace,
    write_phase_segments,
)
from bvlos_sim.schemas.flight_log import FlightTraceProvenance, FlightTraceRecord, NormalizedFlightTrace
from bvlos_sim.schemas.phase_segment import (
    PHASE_SEGMENT_SCHEMA_VERSION,
    PhaseSegmentResult,
    TracePhase,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_PROVENANCE = FlightTraceProvenance(
    source_format="test",
    raw_log_sha256="0" * 64,
    raw_log_filename="test.log",
    tool_version="0.0.0",
)


def _trace(*records: FlightTraceRecord) -> NormalizedFlightTrace:
    return NormalizedFlightTrace(
        schema_version="flight-trace.v1",
        trace_id="test-seg",
        provenance=_DUMMY_PROVENANCE,
        records=list(records),
    )


def _rec(
    i: int,
    *,
    mode: str | None = None,
    speed: float | None = None,
    alt: float | None = None,
) -> FlightTraceRecord:
    return FlightTraceRecord(
        timestamp_s=float(i),
        lat_deg=47.0,
        lon_deg=9.0,
        flight_mode=mode,
        groundspeed_mps=speed,
        alt_amsl_m=alt,
    )


def _phases(result: PhaseSegmentResult) -> list[TracePhase]:
    """Expand segment list back to a per-record phase list."""
    if not result.segments:
        return []
    total = result.segments[-1].end_index + 1
    out: list[TracePhase] = [TracePhase.UNKNOWN] * total
    for seg in result.segments:
        for i in range(seg.start_index, seg.end_index + 1):
            out[i] = seg.phase
    return out


# ---------------------------------------------------------------------------
# Mode-based segmentation
# ---------------------------------------------------------------------------


def test_takeoff_mode_produces_takeoff_segment() -> None:
    result = segment_trace(_trace(_rec(0, mode="TAKEOFF")))

    assert len(result.segments) == 1
    assert result.segments[0].phase == TracePhase.TAKEOFF


def test_rtl_mode_produces_rtl_segment() -> None:
    result = segment_trace(_trace(_rec(0, mode="RTL")))

    assert result.segments[0].phase == TracePhase.RTL


def test_land_mode_produces_landing_segment() -> None:
    result = segment_trace(_trace(_rec(0, mode="LAND")))

    assert result.segments[0].phase == TracePhase.LANDING


def test_loiter_mode_produces_loiter_segment() -> None:
    result = segment_trace(_trace(_rec(0, mode="LOITER")))

    assert result.segments[0].phase == TracePhase.LOITER


def test_unrecognized_mode_produces_unknown_segment() -> None:
    result = segment_trace(_trace(_rec(0, mode="STABILIZE")))

    assert result.segments[0].phase == TracePhase.UNKNOWN


# ---------------------------------------------------------------------------
# PX4 nav_state vocabulary (emitted by the ULog adapter)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("AUTO_TAKEOFF", TracePhase.TAKEOFF),
        ("AUTO_VTOL_TAKEOFF", TracePhase.TAKEOFF),
        ("AUTO_RTL", TracePhase.RTL),
        ("AUTO_LAND", TracePhase.LANDING),
        ("AUTO_PRECLAND", TracePhase.LANDING),
        ("DESCEND", TracePhase.LANDING),
        ("AUTO_LOITER", TracePhase.LOITER),
        ("ORBIT", TracePhase.LOITER),
    ],
)
def test_px4_nav_state_modes_map_directly(mode: str, expected: TracePhase) -> None:
    result = segment_trace(_trace(_rec(0, mode=mode)))

    assert result.segments[0].phase == expected


@pytest.mark.parametrize("mode", ["AUTO_MISSION", "OFFBOARD", "AUTO_FOLLOW_TARGET"])
def test_px4_autonomous_modes_dispatch_kinematically(mode: str) -> None:
    speed = TRANSIT_SPEED_MPS + 1.0
    records = [_rec(i, mode=mode, speed=speed, alt=100.0) for i in range(3)]
    result = segment_trace(_trace(*records))

    assert all(p == TracePhase.TRANSIT for p in _phases(result))


@pytest.mark.parametrize("mode", ["MANUAL", "POSCTL", "TERMINATION", "NAV_STATE_99"])
def test_px4_manual_and_unrecognized_nav_states_stay_unknown(mode: str) -> None:
    # Fail-closed: modes outside the vocabulary never fall through to kinematics,
    # even when speed and altitude data could classify the motion.
    result = segment_trace(_trace(_rec(0, mode=mode, speed=10.0, alt=100.0)))

    assert result.segments[0].phase == TracePhase.UNKNOWN


# ---------------------------------------------------------------------------
# Kinematic segmentation (AUTO mode delegates to kinematics)
# ---------------------------------------------------------------------------


def test_auto_mode_high_speed_flat_produces_transit() -> None:
    speed = TRANSIT_SPEED_MPS + 1.0
    records = [_rec(i, mode="AUTO", speed=speed, alt=100.0) for i in range(3)]
    result = segment_trace(_trace(*records))

    assert all(p == TracePhase.TRANSIT for p in _phases(result))


def test_auto_mode_ascending_high_speed_produces_climb() -> None:
    # Vertical rate at interior record: (110 - 100) / 2s = 5 m/s > threshold.
    # Speed > LOITER_SPEED → climb (not takeoff).
    speed = LOITER_SPEED_MPS + 2.0
    records = [
        _rec(0, mode="AUTO", speed=speed, alt=100.0),
        _rec(1, mode="AUTO", speed=speed, alt=105.0),
        _rec(2, mode="AUTO", speed=speed, alt=110.0),
    ]
    result = segment_trace(_trace(*records))

    assert result.segments[0].phase == TracePhase.CLIMB


def test_auto_mode_ascending_low_speed_produces_takeoff() -> None:
    # Ascending + slow → takeoff, not climb.
    speed = LOITER_SPEED_MPS - 0.5
    records = [
        _rec(0, mode="AUTO", speed=speed, alt=100.0),
        _rec(1, mode="AUTO", speed=speed, alt=105.0),
        _rec(2, mode="AUTO", speed=speed, alt=110.0),
    ]
    result = segment_trace(_trace(*records))

    assert result.segments[0].phase == TracePhase.TAKEOFF


def test_auto_mode_descending_high_speed_produces_descent() -> None:
    speed = LOITER_SPEED_MPS + 2.0
    records = [
        _rec(0, mode="AUTO", speed=speed, alt=110.0),
        _rec(1, mode="AUTO", speed=speed, alt=105.0),
        _rec(2, mode="AUTO", speed=speed, alt=100.0),
    ]
    result = segment_trace(_trace(*records))

    assert result.segments[0].phase == TracePhase.DESCENT


def test_auto_mode_descending_low_speed_produces_landing() -> None:
    speed = LOITER_SPEED_MPS - 0.5
    records = [
        _rec(0, mode="AUTO", speed=speed, alt=110.0),
        _rec(1, mode="AUTO", speed=speed, alt=105.0),
        _rec(2, mode="AUTO", speed=speed, alt=100.0),
    ]
    result = segment_trace(_trace(*records))

    assert result.segments[0].phase == TracePhase.LANDING


# ---------------------------------------------------------------------------
# Kinematic segmentation (no mode field)
# ---------------------------------------------------------------------------


def test_no_mode_high_speed_flat_produces_transit() -> None:
    speed = TRANSIT_SPEED_MPS + 1.0
    records = [_rec(i, speed=speed, alt=100.0) for i in range(3)]
    result = segment_trace(_trace(*records))

    assert all(p == TracePhase.TRANSIT for p in _phases(result))


def test_no_mode_low_speed_flat_produces_loiter() -> None:
    speed = LOITER_SPEED_MPS - 0.5
    records = [_rec(i, speed=speed, alt=100.0) for i in range(3)]
    result = segment_trace(_trace(*records))

    assert all(p == TracePhase.LOITER for p in _phases(result))


def test_kinematic_mid_band_speed_is_classified_not_unknown() -> None:
    # Speeds in the former dead zone (LOITER_SPEED..TRANSIT_SPEED) must resolve to a
    # real phase, split at the midpoint, rather than falling through to UNKNOWN.
    midpoint = (LOITER_SPEED_MPS + TRANSIT_SPEED_MPS) / 2.0
    below = [_rec(i, speed=midpoint - 0.1, alt=100.0) for i in range(3)]
    above = [_rec(i, speed=midpoint + 0.1, alt=100.0) for i in range(3)]

    assert all(p == TracePhase.LOITER for p in _phases(segment_trace(_trace(*below))))
    assert all(p == TracePhase.TRANSIT for p in _phases(segment_trace(_trace(*above))))


def test_no_mode_no_speed_no_alt_produces_unknown() -> None:
    result = segment_trace(_trace(_rec(0)))

    assert result.segments[0].phase == TracePhase.UNKNOWN


# ---------------------------------------------------------------------------
# Segment encoding and boundaries
# ---------------------------------------------------------------------------


def test_empty_trace_produces_empty_segments() -> None:
    result = segment_trace(_trace())

    assert result.segments == []
    assert result.metadata.unknown_record_count == 0


def test_contiguous_same_phase_produces_single_segment() -> None:
    speed = TRANSIT_SPEED_MPS + 1.0
    records = [_rec(i, speed=speed, alt=100.0) for i in range(5)]
    result = segment_trace(_trace(*records))

    assert len(result.segments) == 1
    assert result.segments[0].record_count == 5
    assert result.segments[0].start_index == 0
    assert result.segments[0].end_index == 4


def test_phase_transition_produces_multiple_segments() -> None:
    high_speed = TRANSIT_SPEED_MPS + 1.0
    records = [
        _rec(0, mode="TAKEOFF"),
        _rec(1, mode="TAKEOFF"),
        _rec(2, speed=high_speed, alt=100.0),
        _rec(3, speed=high_speed, alt=100.0),
        _rec(4, speed=high_speed, alt=100.0),
        _rec(5, mode="LOITER"),
    ]
    result = segment_trace(_trace(*records))

    phases = [seg.phase for seg in result.segments]
    assert phases == [TracePhase.TAKEOFF, TracePhase.TRANSIT, TracePhase.LOITER]


def test_segment_timestamps_match_records() -> None:
    records = [
        _rec(0, mode="TAKEOFF"),
        _rec(5, mode="TAKEOFF"),
        _rec(10, mode="RTL"),
        _rec(15, mode="RTL"),
    ]
    result = segment_trace(_trace(*records))

    takeoff_seg = result.segments[0]
    assert takeoff_seg.start_time_s == pytest.approx(0.0)
    assert takeoff_seg.end_time_s == pytest.approx(5.0)
    rtl_seg = result.segments[1]
    assert rtl_seg.start_time_s == pytest.approx(10.0)
    assert rtl_seg.end_time_s == pytest.approx(15.0)


# ---------------------------------------------------------------------------
# Smoothing
# ---------------------------------------------------------------------------


def test_single_record_blip_is_absorbed_into_surrounding_phase() -> None:
    high_speed = TRANSIT_SPEED_MPS + 1.0
    # Five transit records with one UNKNOWN blip (no speed, no alt) in the middle.
    records = [
        _rec(0, speed=high_speed, alt=100.0),
        _rec(1, speed=high_speed, alt=100.0),
        _rec(2),   # no data → UNKNOWN before smoothing
        _rec(3, speed=high_speed, alt=100.0),
        _rec(4, speed=high_speed, alt=100.0),
    ]
    result = segment_trace(_trace(*records))

    # After smoothing, all records should be TRANSIT.
    assert len(result.segments) == 1
    assert result.segments[0].phase == TracePhase.TRANSIT


# ---------------------------------------------------------------------------
# Estimator phase mapping
# ---------------------------------------------------------------------------


def test_estimator_leg_phase_populated_for_mapped_phases() -> None:
    mappings = {
        "TAKEOFF": "vertical_takeoff",
        "RTL": "rtl_transit",
        "LAND": "landing_transit",
        "LOITER": "loiter_dwell",
    }
    for mode, expected_leg_phase in mappings.items():
        result = segment_trace(_trace(_rec(0, mode=mode)))
        assert result.segments[0].estimator_leg_phase == expected_leg_phase, mode


def test_transit_estimator_leg_phase_is_transit() -> None:
    speed = TRANSIT_SPEED_MPS + 1.0
    records = [_rec(i, speed=speed, alt=100.0) for i in range(3)]
    result = segment_trace(_trace(*records))

    assert result.segments[0].estimator_leg_phase == "transit"


def test_climb_and_descent_have_no_estimator_leg_phase() -> None:
    speed = LOITER_SPEED_MPS + 2.0
    climbing = [
        _rec(0, mode="AUTO", speed=speed, alt=100.0),
        _rec(1, mode="AUTO", speed=speed, alt=110.0),
        _rec(2, mode="AUTO", speed=speed, alt=120.0),
    ]
    result = segment_trace(_trace(*climbing))

    assert result.segments[0].estimator_leg_phase is None


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def test_metadata_schema_and_method() -> None:
    result = segment_trace(_trace(_rec(0, mode="RTL")))

    assert result.schema_version == PHASE_SEGMENT_SCHEMA_VERSION
    assert result.metadata.method == SEGMENTATION_METHOD


def test_metadata_unknown_record_count() -> None:
    records = [
        _rec(0, mode="TAKEOFF"),
        _rec(1),   # UNKNOWN (no data)
        _rec(2),   # UNKNOWN — two in a row so smoothing does NOT absorb
        _rec(3, mode="RTL"),
    ]
    result = segment_trace(_trace(*records))

    assert result.metadata.unknown_record_count == 2


def test_metadata_source_fields_used_reflects_available_data() -> None:
    records = [
        _rec(0, mode="TAKEOFF", speed=0.5, alt=100.0),
        _rec(1, speed=10.0, alt=100.0),
    ]
    result = segment_trace(_trace(*records))

    assert "flight_mode" in result.metadata.source_fields_used
    assert "groundspeed_mps" in result.metadata.source_fields_used
    assert "alt_amsl_m" in result.metadata.source_fields_used


def test_metadata_source_fields_absent_when_data_missing() -> None:
    result = segment_trace(_trace(_rec(0)))

    assert "flight_mode" not in result.metadata.source_fields_used
    assert "groundspeed_mps" not in result.metadata.source_fields_used
    assert "alt_amsl_m" not in result.metadata.source_fields_used


# ---------------------------------------------------------------------------
# I/O roundtrip
# ---------------------------------------------------------------------------


def test_phase_segments_write_read_roundtrip(tmp_path: Path) -> None:
    records = [
        _rec(0, mode="TAKEOFF"),
        _rec(1, speed=TRANSIT_SPEED_MPS + 1.0, alt=100.0),
        _rec(2, speed=TRANSIT_SPEED_MPS + 1.0, alt=100.0),
        _rec(3, mode="LOITER"),
    ]
    result = segment_trace(_trace(*records))
    out = tmp_path / "segments.json"

    write_phase_segments(result, out)
    loaded, document = load_phase_segments(out)

    assert loaded.schema_version == result.schema_version
    assert loaded.trace_id == result.trace_id
    assert len(loaded.segments) == len(result.segments)
    assert loaded.segments[0].phase == result.segments[0].phase
    assert loaded.metadata.method == result.metadata.method
    assert document.format == "json"
    assert document.sha256 == hashlib.sha256(out.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Integration: segment an ingested DataFlash trace
# ---------------------------------------------------------------------------


def test_segment_ingested_dataflash_trace_produces_transit() -> None:
    from bvlos_sim.adapters.flight_log import ingest_dataflash_log

    repo_root = Path(__file__).resolve().parents[1]
    log = repo_root / "tests" / "fixtures" / "synthetic_dataflash.log"
    trace = ingest_dataflash_log(log, trace_id="integration-seg")
    result = segment_trace(trace)

    # synthetic_dataflash.log: mode=AUTO, speed ~8 m/s (> TRANSIT_SPEED_MPS) → TRANSIT
    assert len(result.segments) == 1
    assert result.segments[0].phase == TracePhase.TRANSIT
    assert result.segments[0].estimator_leg_phase == "transit"


# ---------------------------------------------------------------------------
# Estimator-mapping drift guard
# ---------------------------------------------------------------------------


def test_estimator_mapping_values_are_valid_legphases() -> None:
    # The segmenter hard-codes LegPhase string values to avoid coupling adapters to
    # the estimator. Guard against drift: every mapped value must be a real LegPhase
    # member (there is, deliberately, no estimator leg for climb/descent).
    from bvlos_sim.estimator.core.enums import LegPhase

    from bvlos_sim.adapters.phase_segmentation.segmenter import _ESTIMATOR_PHASE_MAP

    valid_values = {phase.value for phase in LegPhase}
    assert set(_ESTIMATOR_PHASE_MAP.values()) <= valid_values
