"""Tests for predicted-vs-observed validation metrics (Ticket 082)."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from adapters.flight_log import ingest_dataflash_log
from adapters.phase_segmentation import segment_trace
from adapters.validation import (
    build_validation_report,
    load_validation_report,
    write_validation_report,
)
from estimator.core.enums import EstimateStatus, LegPhase
from estimator.core.results import EnergyEstimate, LegEstimate, MissionEstimate
from schemas import ValidationAcceptance as PublicValidationAcceptance
from schemas.flight_log import (
    FlightTraceProvenance,
    FlightTraceRecord,
    NormalizedFlightTrace,
)
from schemas.phase_segment import (
    PHASE_SEGMENT_SCHEMA_VERSION,
    PhaseSegment,
    PhaseSegmentResult,
    SegmentationMetadata,
    TracePhase,
)
from schemas.validation import (
    VALIDATION_REPORT_SCHEMA_VERSION,
    MetricComparison,
    ValidationAcceptance,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_LOG = REPO_ROOT / "examples" / "flight_logs" / "pipeline_demo_001.log"

_PROVENANCE = FlightTraceProvenance(
    source_format="test",
    raw_log_sha256="0" * 64,
    raw_log_filename="test.log",
    tool_version="0.0.0",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _record(
    t: float,
    lat: float,
    lon: float,
    *,
    speed: float | None = None,
    battery_pct: float | None = None,
) -> FlightTraceRecord:
    return FlightTraceRecord(
        timestamp_s=t,
        lat_deg=lat,
        lon_deg=lon,
        groundspeed_mps=speed,
        battery_remaining_pct=battery_pct,
    )


def _trace(*records: FlightTraceRecord, trace_id: str = "t1") -> NormalizedFlightTrace:
    return NormalizedFlightTrace(
        schema_version="flight-trace.v1",
        trace_id=trace_id,
        provenance=_PROVENANCE,
        records=list(records),
    )


def _segments(*segments: PhaseSegment, trace_id: str = "t1") -> PhaseSegmentResult:
    return PhaseSegmentResult(
        schema_version=PHASE_SEGMENT_SCHEMA_VERSION,
        trace_id=trace_id,
        segments=list(segments),
        metadata=SegmentationMetadata(
            method="test", source_fields_used=[], unknown_record_count=0
        ),
    )


def _leg(phase: LegPhase, time_s: float, *, speed: float | None) -> LegEstimate:
    return LegEstimate(
        leg_index=0,
        route_item_index=0,
        route_item_id=None,
        action="goto",
        phase=phase,
        start_lat=0.0,
        start_lon=0.0,
        start_alt_amsl_m=0.0,
        end_lat=0.0,
        end_lon=0.0,
        end_alt_amsl_m=0.0,
        horizontal_distance_m=0.0,
        vertical_delta_m=0.0,
        vertical_distance_m=0.0,
        path_distance_m=0.0,
        time_s=time_s,
        groundspeed_mps=speed,
    )


def _estimate(
    *legs: LegEstimate,
    total_time_s: float,
    total_horizontal_distance_m: float,
    reserve_percent: float | None = None,
) -> MissionEstimate:
    energy = None
    if reserve_percent is not None:
        energy = EnergyEstimate(
            is_feasible=True,
            total_energy_wh=100.0,
            battery_capacity_wh=500.0,
            usable_energy_wh=450.0,
            reserve_threshold_percent=20.0,
            reserve_threshold_wh=100.0,
            reserve_at_landing_wh=350.0,
            reserve_at_landing_percent=reserve_percent,
        )
    return MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=total_horizontal_distance_m,
        total_vertical_distance_m=0.0,
        total_path_distance_m=total_horizontal_distance_m,
        total_time_s=total_time_s,
        totals_are_partial=False,
        legs=list(legs),
        energy=energy,
    )


# ---------------------------------------------------------------------------
# MetricComparison
# ---------------------------------------------------------------------------


def test_validation_acceptance_is_public_schema_export() -> None:
    assert PublicValidationAcceptance is ValidationAcceptance


def test_metric_comparison_both_present() -> None:
    m = MetricComparison.build(110.0, 100.0)
    assert m.abs_error == pytest.approx(10.0)
    assert m.pct_error == pytest.approx(10.0)


def test_metric_comparison_observed_zero_has_no_pct() -> None:
    m = MetricComparison.build(5.0, 0.0)
    assert m.abs_error == pytest.approx(5.0)
    assert m.pct_error is None


def test_metric_comparison_missing_side_has_no_errors() -> None:
    assert MetricComparison.build(5.0, None).abs_error is None
    assert MetricComparison.build(None, 5.0).pct_error is None


# ---------------------------------------------------------------------------
# Mission-level metrics
# ---------------------------------------------------------------------------


def test_mission_time_compared() -> None:
    trace = _trace(
        _record(0.0, 47.0, 9.0, speed=8.0),
        _record(100.0, 47.001, 9.0, speed=8.0),
    )
    estimate = _estimate(
        _leg(LegPhase.TRANSIT, 110.0, speed=8.0),
        total_time_s=110.0,
        total_horizontal_distance_m=120.0,
    )
    report = build_validation_report(
        estimate=estimate,
        trace=trace,
        segments=_segments(),
        validation_id="v1",
        tool_version="0.0.0",
    )
    assert report.mission_metrics.time_s.predicted == pytest.approx(110.0)
    assert report.mission_metrics.time_s.observed == pytest.approx(100.0)
    assert report.mission_metrics.time_s.abs_error == pytest.approx(10.0)


def test_mission_distance_uses_geodesic_over_records() -> None:
    trace = _trace(
        _record(0.0, 47.0, 9.0),
        _record(50.0, 47.001, 9.0),
        _record(100.0, 47.002, 9.0),
    )
    report = build_validation_report(
        estimate=_estimate(total_time_s=100.0, total_horizontal_distance_m=200.0),
        trace=trace,
        segments=_segments(),
        validation_id="v1",
        tool_version="0.0.0",
    )
    # Two ~111 m steps of 0.001 deg latitude (WGS-84 geodesic).
    assert report.mission_metrics.horizontal_distance_m.observed == pytest.approx(
        222.4, abs=1.0
    )


def test_mission_reserve_compares_estimator_reserve_to_battery_remaining() -> None:
    trace = _trace(
        _record(0.0, 47.0, 9.0, battery_pct=100.0),
        _record(100.0, 47.001, 9.0, battery_pct=64.0),
    )
    report = build_validation_report(
        estimate=_estimate(
            total_time_s=100.0, total_horizontal_distance_m=120.0, reserve_percent=70.0
        ),
        trace=trace,
        segments=_segments(),
        validation_id="v1",
        tool_version="0.0.0",
    )
    assert report.mission_metrics.reserve_percent.predicted == pytest.approx(70.0)
    assert report.mission_metrics.reserve_percent.observed == pytest.approx(64.0)
    assert report.mission_metrics.reserve_percent.abs_error == pytest.approx(6.0)


def test_missing_battery_yields_reserve_note_and_null_observed() -> None:
    trace = _trace(_record(0.0, 47.0, 9.0), _record(100.0, 47.001, 9.0))
    report = build_validation_report(
        estimate=_estimate(
            total_time_s=100.0, total_horizontal_distance_m=120.0, reserve_percent=70.0
        ),
        trace=trace,
        segments=_segments(),
        validation_id="v1",
        tool_version="0.0.0",
    )
    assert report.mission_metrics.reserve_percent.observed is None
    assert any("reserve unavailable" in note.lower() for note in report.notes)


# ---------------------------------------------------------------------------
# Per-phase metrics
# ---------------------------------------------------------------------------


def test_phase_bridge_matches_predicted_and_observed_on_estimator_phase() -> None:
    records = [_record(float(i), 47.0, 9.0, speed=8.0) for i in range(4)]
    trace = _trace(*records)
    segments = _segments(
        PhaseSegment(
            phase=TracePhase.TRANSIT,
            start_index=0,
            end_index=3,
            start_time_s=0.0,
            end_time_s=30.0,
            record_count=4,
            estimator_leg_phase="transit",
        )
    )
    estimate = _estimate(
        _leg(LegPhase.TRANSIT, 25.0, speed=10.0),
        total_time_s=25.0,
        total_horizontal_distance_m=250.0,
    )
    report = build_validation_report(
        estimate=estimate,
        trace=trace,
        segments=segments,
        validation_id="v1",
        tool_version="0.0.0",
    )
    transit = next(p for p in report.phase_validations if p.phase == "transit")
    assert transit.time_s.predicted == pytest.approx(25.0)
    assert transit.time_s.observed == pytest.approx(30.0)
    assert transit.mean_groundspeed_mps.predicted == pytest.approx(10.0)
    assert transit.mean_groundspeed_mps.observed == pytest.approx(8.0)
    assert transit.predicted_leg_count == 1
    assert transit.observed_segment_count == 1


def test_unmapped_observed_phase_is_noted_not_compared() -> None:
    records = [_record(float(i), 47.0, 9.0, speed=4.0) for i in range(3)]
    trace = _trace(*records)
    segments = _segments(
        PhaseSegment(
            phase=TracePhase.CLIMB,
            start_index=0,
            end_index=2,
            start_time_s=0.0,
            end_time_s=20.0,
            record_count=3,
            estimator_leg_phase=None,
        )
    )
    report = build_validation_report(
        estimate=_estimate(
            _leg(LegPhase.TRANSIT, 25.0, speed=10.0),
            total_time_s=25.0,
            total_horizontal_distance_m=250.0,
        ),
        trace=trace,
        segments=segments,
        validation_id="v1",
        tool_version="0.0.0",
    )
    assert all(p.phase != "climb" for p in report.phase_validations)
    assert any(
        "climb" in note and "no estimator counterpart" in note for note in report.notes
    )


def test_phase_validations_sorted_by_phase_name() -> None:
    records = [_record(float(i), 47.0, 9.0, speed=8.0) for i in range(2)]
    estimate = _estimate(
        _leg(LegPhase.TRANSIT, 10.0, speed=8.0),
        _leg(LegPhase.VERTICAL_TAKEOFF, 5.0, speed=1.0),
        total_time_s=15.0,
        total_horizontal_distance_m=80.0,
    )
    report = build_validation_report(
        estimate=estimate,
        trace=_trace(*records),
        segments=_segments(),
        validation_id="v1",
        tool_version="0.0.0",
    )
    phases = [p.phase for p in report.phase_validations]
    assert phases == sorted(phases)


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_trace_id_mismatch_raises() -> None:
    trace = _trace(_record(0.0, 47.0, 9.0), trace_id="a")
    with pytest.raises(ValueError, match="does not match"):
        build_validation_report(
            estimate=_estimate(total_time_s=1.0, total_horizontal_distance_m=1.0),
            trace=trace,
            segments=_segments(trace_id="b"),
            validation_id="v1",
            tool_version="0.0.0",
        )


# ---------------------------------------------------------------------------
# I/O roundtrip
# ---------------------------------------------------------------------------


def test_validation_report_write_read_roundtrip(tmp_path: Path) -> None:
    report = build_validation_report(
        estimate=_estimate(
            _leg(LegPhase.TRANSIT, 100.0, speed=8.0),
            total_time_s=100.0,
            total_horizontal_distance_m=800.0,
            reserve_percent=70.0,
        ),
        trace=_trace(
            _record(0.0, 47.0, 9.0, speed=8.0, battery_pct=100.0),
            _record(100.0, 47.005, 9.0, speed=8.0, battery_pct=64.0),
        ),
        segments=_segments(),
        validation_id="roundtrip-1",
        tool_version="0.0.0",
    )
    out = tmp_path / "report.json"
    write_validation_report(report, out)
    loaded, document = load_validation_report(out)

    assert loaded.schema_version == VALIDATION_REPORT_SCHEMA_VERSION
    assert loaded.validation_id == "roundtrip-1"
    assert loaded.mission_metrics.time_s.observed == pytest.approx(100.0)
    assert loaded.acceptance.thresholds_pct
    assert document.format == "json"


# ---------------------------------------------------------------------------
# Full path: ingest example log -> segment -> validate
# ---------------------------------------------------------------------------


def test_full_path_from_example_log() -> None:
    trace = ingest_dataflash_log(EXAMPLE_LOG, trace_id="pipeline-demo-001-obs")
    segments = segment_trace(trace)
    estimate = _estimate(
        _leg(LegPhase.TRANSIT, 120.0, speed=18.0),
        total_time_s=120.0,
        total_horizontal_distance_m=2160.0,
        reserve_percent=70.0,
    )
    report = build_validation_report(
        estimate=estimate,
        trace=trace,
        segments=segments,
        validation_id="example-validation",
        tool_version="0.0.0",
    )
    # Example flight ends near 62% battery and produces comparable mission metrics.
    assert report.mission_metrics.reserve_percent.observed == pytest.approx(62.0)
    assert report.observed_record_count == len(trace.records)
    assert report.mission_metrics.horizontal_distance_m.observed is not None
    assert any(p.phase == "transit" for p in report.phase_validations)
    assert isinstance(report.acceptance.passed, bool)


__all__: list[str] = []


def test_validate_refuses_a_calibration_fitted_from_the_same_trace() -> None:
    """A model tuned on a flight reproduces that flight; that is not evidence."""

    from adapters.commands.validate import _refuse_circular_validation
    from schemas.calibration import CalibrationProfile

    profile = CalibrationProfile.model_validate(
        {
            "schema_version": "calibration-profile.v1",
            "calibration_id": "cal-1",
            "base_vehicle_id": "quadplane_v1",
            "provenance": {
                "tool_version": "0.0.0-test",
                "calibration_dataset_version": "d1",
                "source_trace_ids": ["flight-a"],
            },
            "parameters": [],
        }
    )

    # A different trace is fine.
    _refuse_circular_validation(profile, "flight-b")
    # No calibration at all is fine.
    _refuse_circular_validation(None, "flight-a")

    with pytest.raises(typer.BadParameter, match="circular"):
        _refuse_circular_validation(profile, "flight-a")
