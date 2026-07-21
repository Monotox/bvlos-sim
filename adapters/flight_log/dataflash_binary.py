"""Library-backed ArduPilot DataFlash binary ingestion."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from adapters.flight_log.dataflash import (
    DEFAULT_MAX_FLIGHT_LOG_BYTES,
    FlightLogIngestionError,
    _RawRow,
    _build_dataflash_trace,
    _read_bytes,
)
from schemas.flight_log import FlightTraceMissionRef, NormalizedFlightTrace

ARDUPILOT_DATAFLASH_BINARY_FORMAT = "ardupilot_dataflash_binary"


def ingest_dataflash_binary(
    path: Path,
    *,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None = None,
    max_bytes: int = DEFAULT_MAX_FLIGHT_LOG_BYTES,
) -> NormalizedFlightTrace:
    """Ingest an ArduPilot controller ``.bin`` log using pymavlink DFReader."""
    raw_bytes = _read_bytes(path, max_bytes=max_bytes)
    return _ingest_dataflash_binary_bytes(
        path,
        raw_bytes=raw_bytes,
        trace_id=trace_id,
        mission_ref=mission_ref,
    )


def _ingest_dataflash_binary_bytes(
    path: Path,
    *,
    raw_bytes: bytes,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None,
) -> NormalizedFlightTrace:
    """Parse an already bounded immutable snapshot of a binary log."""
    if not raw_bytes.startswith(b"\xa3\x95"):
        raise FlightLogIngestionError(
            "File does not have an ArduPilot DataFlash binary header.",
            path=path,
            reason="format_mismatch",
        )

    rows: dict[str, list[_RawRow]] = {
        "GPS": [],
        "BAT": [],
        "MODE": [],
        "NKF6": [],
        "XKF6": [],
    }
    try:
        with TemporaryDirectory(prefix="bvlos-dataflash-") as temp_dir:
            snapshot = Path(temp_dir) / (path.name or "flight.bin")
            snapshot.write_bytes(raw_bytes)
            for message_type, payload in _iter_dataflash_messages(snapshot):
                if message_type not in rows:
                    continue
                row = _normalise_row(payload)
                if "TimeUS" in row:
                    rows[message_type].append(row)
    except FlightLogIngestionError:
        raise
    except Exception as exc:
        raise FlightLogIngestionError(
            f"Could not parse ArduPilot DataFlash binary log: {exc}",
            path=path,
            reason="parse_error",
        ) from exc

    return _build_dataflash_trace(
        path=path,
        raw_bytes=raw_bytes,
        trace_id=trace_id,
        mission_ref=mission_ref,
        source_format=ARDUPILOT_DATAFLASH_BINARY_FORMAT,
        gps_rows=rows["GPS"],
        battery_rows=rows["BAT"],
        mode_rows=rows["MODE"],
        wind_rows=rows["NKF6"] or rows["XKF6"],
    )


def _iter_dataflash_messages(path: Path) -> Iterator[tuple[str, Mapping[str, Any]]]:
    try:
        from pymavlink import DFReader
    except ImportError as exc:
        raise FlightLogIngestionError(
            "ArduPilot binary ingestion requires the 'flight-logs' optional dependency.",
            path=path,
            reason="missing_dependency",
        ) from exc

    reader = DFReader.DFReader_binary(str(path))
    try:
        while True:
            message = reader.recv_msg()
            if message is None:
                break
            message_type = str(message.get_type())
            payload = message.to_dict()
            if isinstance(payload, Mapping):
                yield message_type, payload
    finally:
        reader.close()


def _normalise_row(payload: Mapping[str, Any]) -> _RawRow:
    row: _RawRow = {
        str(key): _python_scalar(value)
        for key, value in payload.items()
        if key != "mavpackettype"
    }
    if "TimeUS" not in row and "TimeMS" in row:
        row["TimeUS"] = int(float(row["TimeMS"])) * 1_000
    return row


def _python_scalar(value: Any) -> object:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    return value


__all__ = [
    "ARDUPILOT_DATAFLASH_BINARY_FORMAT",
    "ingest_dataflash_binary",
]
