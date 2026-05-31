"""Tests for calibration profile fitting and apply (Ticket 083)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from adapters.cli import app

from adapters.calibration import (
    CalibrationInput,
    CalibrationMismatchError,
    apply_calibration,
    fit_calibration_profile,
    load_and_apply_calibration,
    load_calibration_profile,
    write_calibration_profile,
)
from adapters.canonical_json import render_canonical_json
from adapters.flight_log import ingest_dataflash_log
from adapters.io import InputLoadError, load_vehicle
from adapters.phase_segmentation import segment_trace
from schemas.calibration import (
    CALIBRATION_PROFILE_SCHEMA_VERSION,
    CalibratedParameter,
    CalibratedParameterName,
    CalibrationProfile,
    CalibrationProvenance,
)
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

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_LOG = REPO_ROOT / "examples" / "flight_logs" / "pipeline_demo_001.log"
EXAMPLE_VEHICLE = REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"
EXAMPLE_MISSION = REPO_ROOT / "examples" / "missions" / "pipeline_demo_001.yaml"
EXAMPLE_TRACE = REPO_ROOT / "examples" / "flight_logs" / "pipeline_demo_001_trace.json"
EXAMPLE_CALIBRATION = (
    REPO_ROOT / "examples" / "calibration" / "quadplane_v1_calibration.json"
)

runner = CliRunner()

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
    *,
    alt: float | None = None,
    speed: float | None = None,
    wind_e: float | None = None,
    wind_n: float | None = None,
) -> FlightTraceRecord:
    return FlightTraceRecord(
        timestamp_s=t,
        lat_deg=47.0,
        lon_deg=9.0,
        alt_amsl_m=alt,
        groundspeed_mps=speed,
        wind_east_mps=wind_e,
        wind_north_mps=wind_n,
    )


def _trace(*records: FlightTraceRecord, trace_id: str = "t1") -> NormalizedFlightTrace:
    return NormalizedFlightTrace(
        schema_version="flight-trace.v1",
        trace_id=trace_id,
        provenance=_PROVENANCE,
        records=list(records),
    )


def _segment(
    records: list[FlightTraceRecord],
    *,
    phase: TracePhase,
    estimator_leg_phase: str | None,
    start: int,
    end: int,
) -> PhaseSegment:
    return PhaseSegment(
        phase=phase,
        start_index=start,
        end_index=end,
        start_time_s=records[start].timestamp_s,
        end_time_s=records[end].timestamp_s,
        record_count=end - start + 1,
        estimator_leg_phase=estimator_leg_phase,
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


def _vehicle():
    vehicle, _ = load_vehicle(EXAMPLE_VEHICLE)
    return vehicle


def _fit(*inputs: CalibrationInput, calibration_id: str = "cal-1", **kwargs):
    return fit_calibration_profile(
        vehicle=_vehicle(),
        inputs=list(inputs),
        calibration_id=calibration_id,
        tool_version="0.0.0",
        **kwargs,
    )


def _param(profile: CalibrationProfile, name: CalibratedParameterName):
    return next(
        (p for p in profile.parameters if p.parameter == name),
        None,
    )


# ---------------------------------------------------------------------------
# Cruise speed
# ---------------------------------------------------------------------------


def test_cruise_speed_fit_from_transit_segments() -> None:
    records = [
        _record(0.0, speed=16.0, wind_e=3.0, wind_n=4.0),
        _record(5.0, speed=18.0, wind_e=0.0, wind_n=0.0),
        _record(10.0, speed=20.0, wind_e=0.0, wind_n=0.0),
    ]
    trace = _trace(*records)
    segments = _segments(
        _segment(
            records,
            phase=TracePhase.TRANSIT,
            estimator_leg_phase="transit",
            start=0,
            end=2,
        )
    )
    profile = _fit(CalibrationInput(trace=trace, segments=segments))

    cruise = _param(profile, CalibratedParameterName.CRUISE_SPEED_MPS)
    assert cruise is not None
    assert cruise.fitted_value == pytest.approx(18.0)
    assert cruise.confidence_low == pytest.approx(16.0)
    assert cruise.confidence_high == pytest.approx(20.0)
    assert cruise.sample_count == 3
    assert cruise.unit == "m/s"
    assert cruise.spread == pytest.approx(1.632993, abs=1e-5)
    # Wind magnitude sqrt(3^2 + 4^2) = 5.0 is the max observed condition.
    assert any("5.00 m/s" in c for c in cruise.applicable_conditions)


# ---------------------------------------------------------------------------
# Climb / descent rate
# ---------------------------------------------------------------------------


def test_climb_rate_fit_from_vertical_rate() -> None:
    # 0->10 m over 5 s = 2.0 m/s; 10->25 m over 5 s = 3.0 m/s.
    records = [_record(0.0, alt=0.0), _record(5.0, alt=10.0), _record(10.0, alt=25.0)]
    segments = _segments(
        _segment(
            records, phase=TracePhase.CLIMB, estimator_leg_phase=None, start=0, end=2
        )
    )
    profile = _fit(CalibrationInput(trace=_trace(*records), segments=segments))
    climb = _param(profile, CalibratedParameterName.CLIMB_RATE_MPS)
    assert climb is not None
    assert climb.fitted_value == pytest.approx(2.5)
    assert climb.confidence_low == pytest.approx(2.0)
    assert climb.confidence_high == pytest.approx(3.0)
    assert climb.sample_count == 2
    assert any("AMSL band 0.0 to 25.0 m" in c for c in climb.applicable_conditions)


def test_descent_rate_fit_stored_as_positive_magnitude() -> None:
    # 100->90 over 5 s = -2.0; 90->75 over 5 s = -3.0 -> magnitudes 2.0, 3.0.
    records = [
        _record(0.0, alt=100.0),
        _record(5.0, alt=90.0),
        _record(10.0, alt=75.0),
    ]
    segments = _segments(
        _segment(
            records, phase=TracePhase.DESCENT, estimator_leg_phase=None, start=0, end=2
        )
    )
    profile = _fit(CalibrationInput(trace=_trace(*records), segments=segments))
    descent = _param(profile, CalibratedParameterName.DESCENT_RATE_MPS)
    assert descent is not None
    assert descent.fitted_value == pytest.approx(2.5)
    assert descent.confidence_low == pytest.approx(2.0)
    assert descent.confidence_high == pytest.approx(3.0)
    assert descent.sample_count == 2


def test_small_vertical_rate_below_threshold_is_not_climb() -> None:
    # 0.2 m/s is below the 0.5 m/s climb threshold -> no climb fit.
    records = [_record(0.0, alt=0.0), _record(10.0, alt=2.0)]
    segments = _segments(
        _segment(
            records, phase=TracePhase.CLIMB, estimator_leg_phase=None, start=0, end=1
        )
    )
    profile = _fit(CalibrationInput(trace=_trace(*records), segments=segments))
    assert _param(profile, CalibratedParameterName.CLIMB_RATE_MPS) is None
    assert any("climb_rate_mps not fit" in note for note in profile.notes)


# ---------------------------------------------------------------------------
# Station-keep wind authority
# ---------------------------------------------------------------------------


def test_station_keep_authority_is_max_observed_hold_wind() -> None:
    records = [
        _record(0.0, speed=0.5, wind_e=3.0, wind_n=4.0),  # wind 5.0
        _record(5.0, speed=0.8, wind_e=6.0, wind_n=8.0),  # wind 10.0
    ]
    trace = _trace(*records)
    segments = _segments(
        _segment(
            records,
            phase=TracePhase.LOITER,
            estimator_leg_phase="loiter_dwell",
            start=0,
            end=1,
        )
    )
    profile = _fit(CalibrationInput(trace=trace, segments=segments))
    authority = _param(profile, CalibratedParameterName.MAX_STATION_KEEP_WIND_MPS)
    assert authority is not None
    # Demonstrated authority is the strongest wind held against, not the mean.
    assert authority.fitted_value == pytest.approx(10.0)
    assert authority.confidence_low == pytest.approx(5.0)
    assert authority.confidence_high == pytest.approx(10.0)
    assert authority.sample_count == 2


def test_moving_loiter_records_excluded_from_station_keep() -> None:
    records = [_record(0.0, speed=5.0, wind_e=3.0, wind_n=4.0)]  # not holding
    trace = _trace(*records)
    segments = _segments(
        _segment(
            records,
            phase=TracePhase.LOITER,
            estimator_leg_phase="loiter_dwell",
            start=0,
            end=0,
        )
    )
    profile = _fit(CalibrationInput(trace=trace, segments=segments))
    assert _param(profile, CalibratedParameterName.MAX_STATION_KEEP_WIND_MPS) is None
    assert any("max_station_keep_wind_mps not fit" in n for n in profile.notes)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_provenance_carries_sorted_traces_version_and_links() -> None:
    records = [_record(0.0, speed=18.0), _record(5.0, speed=18.0)]
    seg_a = _segments(
        _segment(
            records,
            phase=TracePhase.TRANSIT,
            estimator_leg_phase="transit",
            start=0,
            end=1,
        ),
        trace_id="zzz",
    )
    seg_b = _segments(
        _segment(
            records,
            phase=TracePhase.TRANSIT,
            estimator_leg_phase="transit",
            start=0,
            end=1,
        ),
        trace_id="aaa",
    )
    profile = _fit(
        CalibrationInput(trace=_trace(*records, trace_id="zzz"), segments=seg_a),
        CalibrationInput(trace=_trace(*records, trace_id="aaa"), segments=seg_b),
        validation_report_ids=["v2", "v1"],
    )
    assert profile.provenance.source_trace_ids == ["aaa", "zzz"]
    assert profile.provenance.validation_report_ids == ["v1", "v2"]
    assert profile.provenance.tool_version == "0.0.0"
    assert profile.provenance.calibration_dataset_version.startswith("ds-2-")
    cruise = _param(profile, CalibratedParameterName.CRUISE_SPEED_MPS)
    assert cruise is not None
    assert (
        cruise.calibration_dataset_version
        == profile.provenance.calibration_dataset_version
    )


def test_trace_id_mismatch_between_trace_and_segments_raises() -> None:
    records = [_record(0.0, speed=18.0)]
    bad = _segments(trace_id="other")
    with pytest.raises(ValueError, match="does not match"):
        _fit(CalibrationInput(trace=_trace(*records, trace_id="t1"), segments=bad))


# ---------------------------------------------------------------------------
# Apply path
# ---------------------------------------------------------------------------


def _calibration(
    *params: CalibratedParameter, base_vehicle_id: str = "quadplane_v1"
) -> CalibrationProfile:
    return CalibrationProfile(
        schema_version=CALIBRATION_PROFILE_SCHEMA_VERSION,
        calibration_id="cal-1",
        base_vehicle_id=base_vehicle_id,
        provenance=CalibrationProvenance(
            tool_version="0.0.0",
            calibration_dataset_version="ds-test",
            source_trace_ids=["t1"],
        ),
        parameters=list(params),
    )


def _calibrated_param(
    name: CalibratedParameterName, value: float
) -> CalibratedParameter:
    return CalibratedParameter(
        parameter=name,
        fitted_value=value,
        unit="m/s",
        sample_count=1,
        confidence_low=value,
        confidence_high=value,
        spread=0.0,
        calibration_dataset_version="ds-test",
        derivation="test",
    )


def test_apply_overrides_only_listed_fields() -> None:
    vehicle = _vehicle()
    calibration = _calibration(
        _calibrated_param(CalibratedParameterName.CRUISE_SPEED_MPS, 20.0),
        _calibrated_param(CalibratedParameterName.CLIMB_RATE_MPS, 2.5),
    )
    calibrated = apply_calibration(vehicle, calibration)

    assert calibrated.performance.cruise_speed_mps == pytest.approx(20.0)
    assert calibrated.performance.climb_rate_mps == pytest.approx(2.5)
    # Untouched fields are inherited from the base vehicle.
    assert (
        calibrated.performance.descent_rate_mps == vehicle.performance.descent_rate_mps
    )
    assert calibrated.performance.max_speed_mps == vehicle.performance.max_speed_mps
    # The base vehicle is not mutated.
    assert vehicle.performance.cruise_speed_mps == pytest.approx(18.0)


def test_apply_is_noop_when_no_parameters() -> None:
    vehicle = _vehicle()
    calibrated = apply_calibration(vehicle, _calibration())
    assert calibrated is vehicle


def test_apply_vehicle_id_mismatch_rejected() -> None:
    vehicle = _vehicle()
    calibration = _calibration(
        _calibrated_param(CalibratedParameterName.CRUISE_SPEED_MPS, 20.0),
        base_vehicle_id="some_other_vehicle",
    )
    with pytest.raises(CalibrationMismatchError, match="does not match"):
        apply_calibration(vehicle, calibration)


def test_apply_revalidates_vehicle_invariants() -> None:
    vehicle = _vehicle()
    # max_speed_mps is 25.0; a calibrated cruise above it must be rejected.
    calibration = _calibration(
        _calibrated_param(CalibratedParameterName.CRUISE_SPEED_MPS, 30.0),
    )
    with pytest.raises(ValidationError):
        apply_calibration(vehicle, calibration)


def test_load_and_apply_calibration_maps_mismatch_to_input_error(
    tmp_path: Path,
) -> None:
    calibration = _calibration(
        _calibrated_param(CalibratedParameterName.CRUISE_SPEED_MPS, 20.0),
        base_vehicle_id="some_other_vehicle",
    )
    path = tmp_path / "cal.json"
    write_calibration_profile(calibration, path)
    with pytest.raises(InputLoadError) as exc_info:
        load_and_apply_calibration(_vehicle(), path)
    assert exc_info.value.input_name == "calibration"


# ---------------------------------------------------------------------------
# Determinism and I/O
# ---------------------------------------------------------------------------


def test_fit_is_deterministic() -> None:
    records = [
        _record(0.0, alt=0.0, speed=18.0, wind_e=1.0, wind_n=2.0),
        _record(5.0, alt=10.0, speed=18.0, wind_e=1.0, wind_n=2.0),
    ]
    trace = _trace(*records)
    segments = _segments(
        _segment(
            records,
            phase=TracePhase.TRANSIT,
            estimator_leg_phase="transit",
            start=0,
            end=1,
        )
    )
    first = _fit(CalibrationInput(trace=trace, segments=segments))
    second = _fit(CalibrationInput(trace=trace, segments=segments))
    assert render_canonical_json(
        first.model_dump(mode="json")
    ) == render_canonical_json(second.model_dump(mode="json"))


def test_calibration_write_read_roundtrip(tmp_path: Path) -> None:
    calibration = _calibration(
        _calibrated_param(CalibratedParameterName.CRUISE_SPEED_MPS, 18.0),
    )
    out = tmp_path / "cal.json"
    write_calibration_profile(calibration, out)
    loaded, document = load_calibration_profile(out)

    assert loaded.schema_version == CALIBRATION_PROFILE_SCHEMA_VERSION
    assert loaded.base_vehicle_id == "quadplane_v1"
    assert loaded.parameters[0].fitted_value == pytest.approx(18.0)
    assert document.format == "json"


# ---------------------------------------------------------------------------
# Full path: ingest example log -> segment -> fit
# ---------------------------------------------------------------------------


def test_full_path_from_example_log() -> None:
    trace = ingest_dataflash_log(EXAMPLE_LOG, trace_id="pipeline-demo-001-obs")
    segments = segment_trace(trace)
    profile = fit_calibration_profile(
        vehicle=_vehicle(),
        inputs=[CalibrationInput(trace=trace, segments=segments)],
        calibration_id="pipeline-demo-001-calibration",
        tool_version="0.0.0",
    )

    cruise = _param(profile, CalibratedParameterName.CRUISE_SPEED_MPS)
    climb = _param(profile, CalibratedParameterName.CLIMB_RATE_MPS)
    assert cruise is not None and cruise.fitted_value == pytest.approx(18.0)
    assert climb is not None and climb.fitted_value == pytest.approx(2.5)
    # This flight neither descends nor station-keeps; both are noted, not invented.
    assert _param(profile, CalibratedParameterName.DESCENT_RATE_MPS) is None
    assert _param(profile, CalibratedParameterName.MAX_STATION_KEEP_WIND_MPS) is None
    assert any("descent_rate_mps not fit" in note for note in profile.notes)

    # Applying the fitted profile produces a usable, valid calibrated vehicle.
    calibrated = apply_calibration(_vehicle(), profile)
    assert calibrated.performance.cruise_speed_mps == pytest.approx(18.0)
    assert calibrated.performance.climb_rate_mps == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_calibrate_json_emits_versioned_envelope() -> None:
    result = runner.invoke(
        app,
        ["calibrate", str(EXAMPLE_VEHICLE), str(EXAMPLE_TRACE), "--format", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == CALIBRATION_PROFILE_SCHEMA_VERSION
    assert payload["base_vehicle_id"] == "quadplane_v1"
    fitted = {p["parameter"] for p in payload["parameters"]}
    assert fitted == {"cruise_speed_mps", "climb_rate_mps"}


def test_cli_calibrate_markdown_default() -> None:
    result = runner.invoke(app, ["calibrate", str(EXAMPLE_VEHICLE), str(EXAMPLE_TRACE)])
    assert result.exit_code == 0
    assert result.stdout.startswith("# Calibration Profile:")


def test_cli_calibrate_is_deterministic() -> None:
    args = ["calibrate", str(EXAMPLE_VEHICLE), str(EXAMPLE_TRACE), "--format", "json"]
    first = runner.invoke(app, args)
    second = runner.invoke(app, args)
    assert first.stdout == second.stdout


def test_cli_calibrate_bad_id_is_invalid_input() -> None:
    result = runner.invoke(
        app,
        [
            "calibrate",
            str(EXAMPLE_VEHICLE),
            str(EXAMPLE_TRACE),
            "--calibration-id",
            "bad id with spaces",
        ],
    )
    assert result.exit_code == 11


def test_cli_estimate_with_matching_calibration_succeeds() -> None:
    result = runner.invoke(
        app,
        [
            "estimate",
            str(EXAMPLE_MISSION),
            str(EXAMPLE_VEHICLE),
            "--calibration",
            str(EXAMPLE_CALIBRATION),
            "--format",
            "summary",
        ],
    )
    assert result.exit_code == 0


def test_cli_estimate_with_mismatched_calibration_is_invalid_input(
    tmp_path: Path,
) -> None:
    calibration = _calibration(
        _calibrated_param(CalibratedParameterName.CRUISE_SPEED_MPS, 20.0),
        base_vehicle_id="some_other_vehicle",
    )
    path = tmp_path / "mismatch.json"
    write_calibration_profile(calibration, path)
    result = runner.invoke(
        app,
        [
            "estimate",
            str(EXAMPLE_MISSION),
            str(EXAMPLE_VEHICLE),
            "--calibration",
            str(path),
        ],
    )
    assert result.exit_code == 11


__all__: list[str] = []
