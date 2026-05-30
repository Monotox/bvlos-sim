"""Tests for flight log ingestion and trace normalization (Ticket 080)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from adapters.flight_log import (
    ARDUPILOT_DATAFLASH_TEXT_FORMAT,
    FlightLogIngestionError,
    ingest_dataflash_log,
    load_flight_trace,
    write_flight_trace,
)
from schemas.flight_log import (
    FLIGHT_TRACE_SCHEMA_VERSION,
    FlightTraceMissionRef,
    NormalizedFlightTrace,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_LOG = REPO_ROOT / "tests" / "fixtures" / "synthetic_dataflash.log"


def _ingest() -> NormalizedFlightTrace:
    return ingest_dataflash_log(SYNTHETIC_LOG, trace_id="test-trace")


# ---------------------------------------------------------------------------
# GPS record extraction
# ---------------------------------------------------------------------------


def test_dataflash_ingest_gps_records_have_lat_lon_alt() -> None:
    trace = _ingest()

    assert len(trace.records) == 3
    r0 = trace.records[0]
    assert r0.lat_deg == pytest.approx(47.641468, abs=1e-5)
    assert r0.lon_deg == pytest.approx(9.341230, abs=1e-5)
    assert r0.alt_amsl_m == pytest.approx(430.5)
    assert r0.groundspeed_mps == pytest.approx(8.3)
    assert r0.heading_deg == pytest.approx(270.1)


def test_dataflash_ingest_timestamps_relative_to_first_gps() -> None:
    trace = _ingest()

    assert trace.records[0].timestamp_s == pytest.approx(0.0)
    assert trace.records[1].timestamp_s == pytest.approx(100.0)
    assert trace.records[2].timestamp_s == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# BAT carry-forward
# ---------------------------------------------------------------------------


def test_dataflash_ingest_carry_forward_battery() -> None:
    trace = _ingest()

    r0, r1, r2 = trace.records
    # BAT at t=100s covers GPS at t=100s and t=200s.
    assert r0.battery_voltage_v == pytest.approx(22.1)
    assert r0.battery_current_a == pytest.approx(15.3)
    assert r0.battery_remaining_pct == pytest.approx(82.0)
    assert r1.battery_voltage_v == pytest.approx(22.1)
    # BAT at t=250s is the latest sample before GPS at t=300s.
    assert r2.battery_voltage_v == pytest.approx(21.9)
    assert r2.battery_remaining_pct == pytest.approx(80.0)


# ---------------------------------------------------------------------------
# MODE and NKF6
# ---------------------------------------------------------------------------


def test_dataflash_ingest_flight_mode_from_mode_message() -> None:
    trace = _ingest()

    for record in trace.records:
        assert record.flight_mode == "AUTO"


def test_dataflash_ingest_wind_from_nkf6() -> None:
    trace = _ingest()

    for record in trace.records:
        assert record.wind_north_mps == pytest.approx(2.5)
        assert record.wind_east_mps == pytest.approx(-1.2)


# ---------------------------------------------------------------------------
# Missing-field detection
# ---------------------------------------------------------------------------


def test_dataflash_ingest_missing_fields_when_bat_absent(tmp_path: Path) -> None:
    log = tmp_path / "no_bat.log"
    log.write_text(
        "FMT, 15, 45, GPS, QBILLeeEefBBH, TimeUS,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,Yaw,U\n"
        "GPS, 100000000, 1, 0, 0, 14, 0.90, 47.641468, 9.341230, 430.5, 8.3, 270.1, 0.1, 0.0, 1\n",
        encoding="utf-8",
    )
    trace = ingest_dataflash_log(log, trace_id="no-bat")

    assert "battery_voltage_v" in trace.provenance.missing_fields
    assert "battery_current_a" in trace.provenance.missing_fields
    assert "battery_remaining_pct" in trace.provenance.missing_fields


def test_dataflash_ingest_missing_fields_when_nkf6_absent(tmp_path: Path) -> None:
    log = tmp_path / "no_wind.log"
    log.write_text(
        "FMT, 15, 45, GPS, QBILLeeEefBBH, TimeUS,Status,GMS,GWk,NSats,HDop,Lat,Lng,Alt,Spd,GCrs,VZ,Yaw,U\n"
        "GPS, 100000000, 1, 0, 0, 14, 0.90, 47.641468, 9.341230, 430.5, 8.3, 270.1, 0.1, 0.0, 1\n",
        encoding="utf-8",
    )
    trace = ingest_dataflash_log(log, trace_id="no-wind")

    assert "wind_east_mps" in trace.provenance.missing_fields
    assert "wind_north_mps" in trace.provenance.missing_fields


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_dataflash_ingest_provenance_has_sha256_format_version() -> None:
    trace = _ingest()
    expected_sha256 = hashlib.sha256(SYNTHETIC_LOG.read_bytes()).hexdigest()

    assert trace.provenance.source_format == ARDUPILOT_DATAFLASH_TEXT_FORMAT
    assert trace.provenance.raw_log_sha256 == expected_sha256
    assert trace.provenance.raw_log_filename == SYNTHETIC_LOG.name
    assert trace.provenance.tool_version != ""
    assert len(trace.provenance.parsing_assumptions) >= 4


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_dataflash_ingest_empty_gps_raises_ingestion_error(tmp_path: Path) -> None:
    log = tmp_path / "no_gps.log"
    log.write_text(
        "FMT, 11, 50, BAT, QBfff, TimeUS,Instance,Volt,Curr,RemPct\n"
        "BAT, 1000000, 0, 22.0, 10.0, 90.0\n",
        encoding="utf-8",
    )

    with pytest.raises(FlightLogIngestionError) as exc_info:
        ingest_dataflash_log(log, trace_id="empty")

    assert exc_info.value.reason == "no_gps_records"


def test_dataflash_ingest_missing_file_raises_ingestion_error(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.log"

    with pytest.raises(FlightLogIngestionError) as exc_info:
        ingest_dataflash_log(missing, trace_id="missing")

    assert exc_info.value.reason == "read_error"


# ---------------------------------------------------------------------------
# trace_id and mission_ref propagation
# ---------------------------------------------------------------------------


def test_dataflash_ingest_uses_trace_id_and_mission_ref() -> None:
    ref = FlightTraceMissionRef(
        mission_file="examples/missions/pipeline_demo_001.yaml",
        vehicle_file="examples/vehicles/quadplane_v1.yaml",
    )
    trace = ingest_dataflash_log(SYNTHETIC_LOG, trace_id="my-trace-001", mission_ref=ref)

    assert trace.trace_id == "my-trace-001"
    assert trace.mission_ref is not None
    assert trace.mission_ref.mission_file == "examples/missions/pipeline_demo_001.yaml"
    assert trace.mission_ref.vehicle_file == "examples/vehicles/quadplane_v1.yaml"


# ---------------------------------------------------------------------------
# Schema version and structure
# ---------------------------------------------------------------------------


def test_normalized_flight_trace_schema_version_is_correct() -> None:
    trace = _ingest()

    assert trace.schema_version == FLIGHT_TRACE_SCHEMA_VERSION


def test_dataflash_ingest_records_are_chronological() -> None:
    trace = _ingest()

    timestamps = [r.timestamp_s for r in trace.records]
    assert timestamps == sorted(timestamps)
    assert timestamps[0] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# I/O roundtrip
# ---------------------------------------------------------------------------


def test_flight_trace_write_read_roundtrip(tmp_path: Path) -> None:
    trace = _ingest()
    out = tmp_path / "trace.json"

    write_flight_trace(trace, out)
    loaded_trace, document = load_flight_trace(out)

    assert loaded_trace.schema_version == trace.schema_version
    assert loaded_trace.trace_id == trace.trace_id
    assert len(loaded_trace.records) == len(trace.records)
    assert loaded_trace.records[0].lat_deg == pytest.approx(trace.records[0].lat_deg)
    assert loaded_trace.records[2].battery_voltage_v == pytest.approx(
        trace.records[2].battery_voltage_v
    )
    assert document.format == "json"
    assert len(document.sha256) == 64


def test_load_flight_trace_returns_model_and_input_document(tmp_path: Path) -> None:
    trace = _ingest()
    out = tmp_path / "trace_doc.json"
    write_flight_trace(trace, out)

    loaded_trace, document = load_flight_trace(out)
    expected_sha256 = hashlib.sha256(out.read_bytes()).hexdigest()

    assert isinstance(loaded_trace, NormalizedFlightTrace)
    assert document.sha256 == expected_sha256
    assert document.path == out


def test_write_flight_trace_produces_valid_json(tmp_path: Path) -> None:
    trace = _ingest()
    out = tmp_path / "trace.json"

    write_flight_trace(trace, out)
    parsed = json.loads(out.read_text(encoding="utf-8"))

    assert parsed["schema_version"] == "flight-trace.v1"
    assert "records" in parsed
    assert "provenance" in parsed
    assert parsed["provenance"]["source_format"] == ARDUPILOT_DATAFLASH_TEXT_FORMAT
