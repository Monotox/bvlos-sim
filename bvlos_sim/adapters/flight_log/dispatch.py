"""Content-based flight-log format dispatch."""

from __future__ import annotations

from pathlib import Path

from bvlos_sim.adapters.flight_log.dataflash import (
    DEFAULT_MAX_FLIGHT_LOG_BYTES,
    FlightLogIngestionError,
    MAX_FLIGHT_LOG_BYTES,
    _ingest_dataflash_bytes,
    _read_bytes,
)
from bvlos_sim.adapters.flight_log.dataflash_binary import _ingest_dataflash_binary_bytes
from bvlos_sim.adapters.flight_log.ulog import ULOG_MAGIC, _ingest_ulog_bytes
from bvlos_sim.schemas.flight_log import FlightTraceMissionRef, NormalizedFlightTrace

_DATAFLASH_BINARY_MAGIC = b"\xa3\x95"


def ingest_flight_log(
    path: Path,
    *,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None = None,
    max_bytes: int = DEFAULT_MAX_FLIGHT_LOG_BYTES,
) -> NormalizedFlightTrace:
    """Detect a supported controller-log format by content and ingest it."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    raw_bytes = _read_bytes(path, max_bytes=max_bytes)
    prefix = raw_bytes[:4_096]

    kwargs = {"trace_id": trace_id, "mission_ref": mission_ref}
    if prefix.startswith(ULOG_MAGIC):
        return _ingest_ulog_bytes(path, raw_bytes=raw_bytes, **kwargs)
    if prefix.startswith(_DATAFLASH_BINARY_MAGIC):
        return _ingest_dataflash_binary_bytes(path, raw_bytes=raw_bytes, **kwargs)
    if _looks_like_dataflash_text(prefix, suffix=path.suffix):
        return _ingest_dataflash_bytes(path, raw_bytes=raw_bytes, **kwargs)
    raise FlightLogIngestionError(
        "Unsupported flight-log format; expected ArduPilot DataFlash text/binary or PX4 ULog.",
        path=path,
        reason="unsupported_format",
    )


def _looks_like_dataflash_text(prefix: bytes, *, suffix: str) -> bool:
    try:
        text = prefix.decode("utf-8")
    except UnicodeDecodeError:
        return False
    stripped = text.lstrip("\ufeff\r\n\t ")
    return (
        suffix.lower() == ".log" or stripped.startswith("FMT,") or "\nGPS," in stripped
    )


__all__ = [
    "DEFAULT_MAX_FLIGHT_LOG_BYTES",
    "MAX_FLIGHT_LOG_BYTES",
    "ingest_flight_log",
]
