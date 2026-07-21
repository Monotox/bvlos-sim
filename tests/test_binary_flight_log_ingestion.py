"""Binary controller-log ingestion and format dispatch tests."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import struct

import pytest
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from adapters.flight_log import (
    ARDUPILOT_DATAFLASH_BINARY_FORMAT,
    MAX_FLIGHT_LOG_BYTES,
    PX4_ULOG_FORMAT,
    FlightLogIngestionError,
    ingest_flight_log,
)
from adapters.flight_log.dataflash import ingest_dataflash_log
from adapters.flight_log.dataflash_binary import ingest_dataflash_binary
from adapters.flight_log.ulog import ULOG_MAGIC, _battery_rows, _mode_rows, ingest_ulog

REPO_ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()

requires_pymavlink = pytest.mark.skipif(
    importlib.util.find_spec("pymavlink") is None,
    reason="requires the 'flight-logs' optional dependency",
)
requires_pyulog = pytest.mark.skipif(
    importlib.util.find_spec("pyulog") is None,
    reason="requires the 'flight-logs' optional dependency",
)


def test_dispatch_rejects_unknown_content(tmp_path: Path) -> None:
    path = tmp_path / "unknown.dat"
    path.write_bytes(b"not a controller log")

    with pytest.raises(FlightLogIngestionError) as exc_info:
        ingest_flight_log(path, trace_id="unknown")

    assert exc_info.value.reason == "unsupported_format"


def test_dispatch_rejects_oversized_log_before_parsing(tmp_path: Path) -> None:
    path = tmp_path / "flight.log"
    path.write_bytes(b"FMT," + b"x" * 64)

    with pytest.raises(FlightLogIngestionError) as exc_info:
        ingest_flight_log(path, trace_id="large", max_bytes=4)

    assert exc_info.value.reason == "file_too_large"


def test_dispatch_rejects_limit_above_process_safety_ceiling(tmp_path: Path) -> None:
    path = tmp_path / "flight.log"
    path.write_bytes(b"FMT,synthetic")

    with pytest.raises(ValueError, match="64 MiB.*process-safety limit"):
        ingest_flight_log(
            path,
            trace_id="unsafe-limit",
            max_bytes=MAX_FLIGHT_LOG_BYTES + 1,
        )


def test_direct_text_ingestion_enforces_size_limit(tmp_path: Path) -> None:
    path = tmp_path / "flight.log"
    path.write_bytes(b"FMT," + b"x" * 64)

    with pytest.raises(FlightLogIngestionError) as exc_info:
        ingest_dataflash_log(path, trace_id="large", max_bytes=4)

    assert exc_info.value.reason == "file_too_large"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO requires POSIX")
def test_dispatch_rejects_non_regular_file_without_blocking(tmp_path: Path) -> None:
    path = tmp_path / "flight.log"
    os.mkfifo(path)

    with pytest.raises(FlightLogIngestionError) as exc_info:
        ingest_flight_log(path, trace_id="fifo")

    assert exc_info.value.reason == "non_regular_file"


def test_dataflash_text_selects_one_gps_receiver(tmp_path: Path) -> None:
    path = tmp_path / "multi-gps.log"
    path.write_text(
        "\n".join(
            [
                "FMT, 1, 0, GPS, synthetic, TimeUS,Status,I,Lat,Lng,Alt,Spd,GCrs",
                "GPS, 1000000, 3, 0, 47.0, 9.0, 500.0, 18.0, 90.0",
                "GPS, 1500000, 3, 1, -20.0, 130.0, 10.0, 1.0, 0.0",
                "GPS, 2000000, 3, 0, 47.001, 9.001, 510.0, 19.0, 91.0",
            ]
        ),
        encoding="utf-8",
    )

    trace = ingest_dataflash_log(path, trace_id="multi-gps")

    assert [record.lat_deg for record in trace.records] == [47.0, 47.001]
    assert any(
        "GPS receiver instance 0 selected" in assumption
        for assumption in trace.provenance.parsing_assumptions
    )


def _dataflash_binary_fixture() -> bytes:
    message_type = 0x82
    message_format = "QBBLLfff"
    columns = "TimeUS,Status,I,Lat,Lng,Alt,Spd,GCrs"
    payload_format = "<QBBiifff"
    message_length = 3 + struct.calcsize(payload_format)
    fmt_payload = struct.pack(
        "<BB4s16s64s",
        message_type,
        message_length,
        b"GPS",
        message_format.encode("ascii"),
        columns.encode("ascii"),
    )
    fmt_record = b"\xa3\x95\x80" + fmt_payload
    records = [
        struct.pack(
            payload_format,
            time_us,
            3,
            0,
            round(lat * 10_000_000),
            round(lon * 10_000_000),
            alt,
            speed,
            course,
        )
        for time_us, lat, lon, alt, speed, course in (
            (1_000_000, 47.0, 9.0, 500.0, 18.0, 90.0),
            (2_000_000, 47.001, 9.001, 510.0, 19.0, 91.0),
        )
    ]
    return fmt_record + b"".join(b"\xa3\x95\x82" + record for record in records)


def _ulog_message(message_type: str, payload: bytes) -> bytes:
    return struct.pack("<HB", len(payload), ord(message_type)) + payload


def _ulog_fixture() -> bytes:
    header = ULOG_MAGIC + bytes([1]) + struct.pack("<Q", 1_000_000)
    flags = _ulog_message("B", bytes(40))
    name = "vehicle_gps_position"
    definition = (
        f"{name}:uint64_t timestamp;double latitude_deg;"
        "double longitude_deg;float altitude_msl_m;float vel_m_s;"
        "float cog_rad;uint8_t fix_type;"
    ).encode("ascii")
    format_message = _ulog_message("F", definition)
    subscription = _ulog_message("A", struct.pack("<BH", 0, 1) + name.encode())
    records = []
    for values in (
        (1_000_000, 47.0, 9.0, 500.0, 18.0, 0.0, 3),
        (2_000_000, 47.001, 9.001, 510.0, 19.0, 1.5707963, 3),
    ):
        payload = struct.pack("<H", 1) + struct.pack("<QddfffB", *values)
        records.append(_ulog_message("D", payload))
    return header + flags + format_message + subscription + b"".join(records)


@requires_pymavlink
def test_real_dataflash_binary_is_decoded_by_pymavlink(tmp_path: Path) -> None:
    path = tmp_path / "flight.bin"
    path.write_bytes(_dataflash_binary_fixture())

    trace = ingest_dataflash_binary(path, trace_id="real-dataflash")

    assert len(trace.records) == 2
    assert trace.records[1].lat_deg == pytest.approx(47.001)


@requires_pymavlink
def test_dataflash_binary_reader_closes_after_exhaustion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("adapters.flight_log.dataflash_binary")
    from pymavlink import DFReader

    class FakeReader:
        closed = False

        def recv_msg(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

    reader = FakeReader()
    monkeypatch.setattr(DFReader, "DFReader_binary", lambda _path: reader)

    assert list(module._iter_dataflash_messages(tmp_path / "snapshot.bin")) == []
    assert reader.closed is True


@requires_pymavlink
def test_dataflash_binary_reader_closes_when_iteration_is_abandoned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("adapters.flight_log.dataflash_binary")
    from pymavlink import DFReader

    class FakeMessage:
        def get_type(self) -> str:
            return "GPS"

        def to_dict(self) -> dict[str, int | str]:
            return {"mavpackettype": "GPS", "TimeUS": 1_000_000}

    class FakeReader:
        closed = False

        def recv_msg(self) -> FakeMessage:
            return FakeMessage()

        def close(self) -> None:
            self.closed = True

    reader = FakeReader()
    monkeypatch.setattr(DFReader, "DFReader_binary", lambda _path: reader)
    messages = module._iter_dataflash_messages(tmp_path / "snapshot.bin")

    assert next(messages)[0] == "GPS"
    messages.close()

    assert reader.closed is True


@requires_pyulog
def test_real_ulog_is_decoded_by_pyulog(tmp_path: Path) -> None:
    path = tmp_path / "flight.ulg"
    path.write_bytes(_ulog_fixture())

    trace = ingest_ulog(path, trace_id="real-ulog")

    assert len(trace.records) == 2
    assert trace.records[1].lat_deg == pytest.approx(47.001)


@pytest.mark.parametrize(
    ("reader", "magic"),
    [
        (ingest_dataflash_binary, b"\xa3\x95"),
        (ingest_ulog, ULOG_MAGIC),
    ],
)
def test_direct_binary_readers_enforce_size_limit(
    tmp_path: Path,
    reader: object,
    magic: bytes,
) -> None:
    path = tmp_path / "large.bin"
    path.write_bytes(magic + b"x" * 64)

    with pytest.raises(FlightLogIngestionError) as exc_info:
        reader(path, trace_id="large", max_bytes=len(magic))

    assert exc_info.value.reason == "file_too_large"


def test_dataflash_binary_maps_controller_messages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("adapters.flight_log.dataflash_binary")
    path = tmp_path / "flight.bin"
    path.write_bytes(b"\xa3\x95synthetic")
    messages = [
        ("BAT", {"TimeUS": 900_000, "Volt": 22.2, "Curr": 12.0, "RemPct": 80}),
        ("MODE", {"TimeUS": 900_000, "Mode": "AUTO"}),
        ("NKF6", {"TimeUS": 900_000, "C": 0, "VWN": 2.0, "VWE": -1.0}),
        (
            "GPS",
            {
                "TimeUS": 1_000_000,
                "Status": 3,
                "Lat": 47.0,
                "Lng": 9.0,
                "Alt": 500.0,
                "Spd": 18.0,
                "GCrs": 90.0,
            },
        ),
        (
            "GPS",
            {
                "TimeUS": 2_000_000,
                "Status": 3,
                "Lat": 47.001,
                "Lng": 9.001,
                "Alt": 510.0,
                "Spd": 19.0,
                "GCrs": 91.0,
            },
        ),
    ]
    monkeypatch.setattr(
        module, "_iter_dataflash_messages", lambda _path: iter(messages)
    )

    trace = ingest_dataflash_binary(path, trace_id="dataflash-bin")

    assert trace.provenance.source_format == ARDUPILOT_DATAFLASH_BINARY_FORMAT
    assert (
        trace.provenance.raw_log_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert len(trace.records) == 2
    assert trace.records[0].battery_remaining_pct == pytest.approx(80.0)
    assert trace.records[0].wind_east_mps == pytest.approx(-1.0)


def test_ulog_maps_px4_topics_deterministically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = importlib.import_module("adapters.flight_log.ulog")
    path = tmp_path / "flight.ulg"
    path.write_bytes(ULOG_MAGIC + b"synthetic")
    datasets = {
        ("vehicle_gps_position", 0): {
            "timestamp": [1_000_000, 2_000_000],
            "fix_type": [3, 3],
            "latitude_deg": [47.0, 47.001],
            "longitude_deg": [9.0, 9.001],
            "altitude_msl_m": [500.0, 510.0],
            "vel_m_s": [18.0, 19.0],
            "cog_rad": [0.0, 1.5707963267948966],
        },
        ("battery_status", 0): {
            "timestamp": [900_000],
            "voltage_v": [22.2],
            "current_a": [12.0],
            "remaining": [0.8],
        },
        ("vehicle_status", 0): {
            "timestamp": [900_000],
            "nav_state": [3],
        },
        ("wind", 0): {
            "timestamp": [900_000],
            "windspeed_north": [2.0],
            "windspeed_east": [-1.0],
        },
    }
    monkeypatch.setattr(module, "_read_ulog_datasets", lambda _path: datasets)

    first = ingest_ulog(path, trace_id="px4-ulog")
    second = ingest_ulog(path, trace_id="px4-ulog")

    assert first == second
    assert first.provenance.source_format == PX4_ULOG_FORMAT
    assert len(first.records) == 2
    assert first.records[0].lat_deg == pytest.approx(47.0)
    assert first.records[0].alt_amsl_m == pytest.approx(500.0)
    assert first.records[0].battery_remaining_pct == pytest.approx(80.0)
    assert first.records[0].flight_mode == "AUTO_MISSION"
    assert first.records[1].heading_deg == pytest.approx(90.0)


@pytest.mark.parametrize(
    ("nav_state", "expected_mode"),
    [
        (10, "ACRO"),
        (14, "OFFBOARD"),
        (17, "AUTO_TAKEOFF"),
        (30, "EXTERNAL8"),
        (99, "NAV_STATE_99"),
    ],
)
def test_ulog_uses_current_px4_navigation_state_values(
    nav_state: int,
    expected_mode: str,
) -> None:
    rows = _mode_rows({"timestamp": [1_000_000], "nav_state": [nav_state]})

    assert rows == [{"TimeUS": 1_000_000, "Mode": expected_mode}]


def test_ulog_omits_invalid_px4_battery_sentinels() -> None:
    rows = _battery_rows(
        {
            "timestamp": [1_000_000],
            "voltage_v": [0.0],
            "current_a": [-1.0],
            "remaining": [-1.0],
        }
    )

    assert rows == [{"TimeUS": 1_000_000, "Volt": None, "Curr": None, "RemPct": None}]


def test_ingest_log_cli_embeds_paired_input_hashes(tmp_path: Path) -> None:
    output = tmp_path / "trace.json"
    mission = REPO_ROOT / "examples" / "missions" / "pipeline_demo_001.yaml"
    vehicle = REPO_ROOT / "examples" / "vehicles" / "quadplane_v1.yaml"
    log = REPO_ROOT / "tests" / "fixtures" / "synthetic_dataflash.log"

    result = runner.invoke(
        app,
        [
            "ingest-log",
            str(log),
            "--trace-id",
            "paired-trace",
            "--mission",
            str(mission),
            "--vehicle",
            str(vehicle),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS), result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert (
        payload["mission_ref"]["mission_sha256"]
        == hashlib.sha256(mission.read_bytes()).hexdigest()
    )
    assert (
        payload["mission_ref"]["vehicle_sha256"]
        == hashlib.sha256(vehicle.read_bytes()).hexdigest()
    )


def test_ingest_log_cli_requires_complete_pair() -> None:
    mission = REPO_ROOT / "examples" / "missions" / "pipeline_demo_001.yaml"
    log = REPO_ROOT / "tests" / "fixtures" / "synthetic_dataflash.log"

    result = runner.invoke(
        app,
        [
            "ingest-log",
            str(log),
            "--trace-id",
            "unpaired-trace",
            "--mission",
            str(mission),
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "must be supplied together" in result.output


def test_ingest_log_cli_rejects_size_limit_above_hard_ceiling(tmp_path: Path) -> None:
    log = tmp_path / "flight.log"
    log.write_bytes(b"FMT,synthetic")

    result = runner.invoke(
        app,
        [
            "ingest-log",
            str(log),
            "--trace-id",
            "unsafe-limit",
            "--max-size-mib",
            "65",
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "64 MiB flight-log process-safety limit" in result.output


def test_ingest_log_cli_rejects_output_collision_with_raw_log(tmp_path: Path) -> None:
    log = tmp_path / "flight.log"
    original = (REPO_ROOT / "tests/fixtures/synthetic_dataflash.log").read_bytes()
    log.write_bytes(original)

    result = runner.invoke(
        app,
        ["ingest-log", str(log), "--trace-id", "collision", "--output", str(log)],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert log.read_bytes() == original


def test_ingest_log_cli_rejects_symlink_output_alias(tmp_path: Path) -> None:
    log = tmp_path / "flight.log"
    original = (REPO_ROOT / "tests/fixtures/synthetic_dataflash.log").read_bytes()
    log.write_bytes(original)
    output_alias = tmp_path / "trace.json"
    output_alias.symlink_to(log)

    result = runner.invoke(
        app,
        [
            "ingest-log",
            str(log),
            "--trace-id",
            "alias-collision",
            "--output",
            str(output_alias),
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert log.read_bytes() == original
