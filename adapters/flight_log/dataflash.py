"""ArduPilot DataFlash text-format (.log) ingestion adapter."""

from __future__ import annotations

import hashlib
import os
import stat
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from adapters.version import tool_version
from schemas.flight_log import (
    FLIGHT_TRACE_SCHEMA_VERSION,
    FlightTraceMissionRef,
    FlightTraceProvenance,
    FlightTraceRecord,
    NormalizedFlightTrace,
)

ARDUPILOT_DATAFLASH_TEXT_FORMAT = "ardupilot_dataflash_text"
# The adapters intentionally snapshot the complete source before parsing so the
# parser cannot be raced onto different bytes.  Text decoding and third-party
# readers then materialize additional structures, so accepting hundreds of MiB
# would permit multi-GiB process growth.  Keep the public override downward-only
# and require large logs to be split before ingestion.
MAX_FLIGHT_LOG_BYTES = 64 * 1024 * 1024
DEFAULT_MAX_FLIGHT_LOG_BYTES = MAX_FLIGHT_LOG_BYTES

# Fallback column indices used when no FMT line declares the message type.
# Index 0 on data lines is the message type name; FMT-named columns start at 1.
_GPS_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1,
    "Status": 2,
    "Lat": 7,
    "Lng": 8,
    "Alt": 9,
    "Spd": 10,
    "GCrs": 11,
}
_BAT_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1,
    "Volt": 2,
    "Curr": 4,
    "RemPct": 6,
}
_MODE_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1,
    "Mode": 2,
}
_NKF6_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1,
    "C": 2,
    "VWN": 3,
    "VWE": 4,
}

# Minimum ArduPilot GPS fix status (2 == 2D fix) for a record to carry a usable
# position; rows below this — or at the null island (0, 0) — are excluded.
_MIN_GPS_FIX_STATUS = 2

# GPS-derived fields populated directly from each GPS data line.
_GPS_FIELD_COLS: dict[str, str] = {
    "alt_amsl_m": "Alt",
    "groundspeed_mps": "Spd",
    "heading_deg": "GCrs",
}
# Record fields whose absence across every record is reported in provenance.
_OPTIONAL_RECORD_FIELDS: tuple[str, ...] = (
    "alt_amsl_m",
    "groundspeed_mps",
    "heading_deg",
    "battery_voltage_v",
    "battery_current_a",
    "battery_remaining_pct",
    "flight_mode",
    "wind_east_mps",
    "wind_north_mps",
)

type _RawRow = dict[str, object]


class FlightLogIngestionError(ValueError):
    """Raised when a log file cannot be ingested."""

    def __init__(self, message: str, *, path: Path, reason: str) -> None:
        super().__init__(message)
        self.path = path
        self.reason = reason


@dataclass(frozen=True)
class _Series:
    """Time-ordered rows of one message type, queryable by carry-forward.

    ``rows`` must be sorted ascending by TimeUS; ``times`` mirrors their
    timestamps so lookups are O(log n) via binary search.
    """

    rows: list[_RawRow]
    times: list[int]

    @classmethod
    def from_rows(cls, rows: list[_RawRow]) -> _Series:
        return cls(rows=rows, times=[_row_timeus(row) for row in rows])

    def at(self, timeus: int) -> _RawRow | None:
        """Most recent row at or before ``timeus`` (carry-forward), or None."""
        pos = bisect_right(self.times, timeus) - 1
        return self.rows[pos] if pos >= 0 else None


def ingest_dataflash_log(
    path: Path,
    *,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None = None,
    max_bytes: int = DEFAULT_MAX_FLIGHT_LOG_BYTES,
) -> NormalizedFlightTrace:
    """Ingest an ArduPilot DataFlash text log (.log) into a NormalizedFlightTrace.

    Raises FlightLogIngestionError if the file cannot be read or contains no GPS records.
    """
    raw_bytes = _read_bytes(path, max_bytes=max_bytes)
    return _ingest_dataflash_bytes(
        path,
        raw_bytes=raw_bytes,
        trace_id=trace_id,
        mission_ref=mission_ref,
    )


def _ingest_dataflash_bytes(
    path: Path,
    *,
    raw_bytes: bytes,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None,
) -> NormalizedFlightTrace:
    lines = _decode_lines(raw_bytes, path)
    col_maps = _parse_fmt_lines(lines)

    all_gps_rows = _collect_rows(lines, "GPS", col_maps, _GPS_FALLBACK_COLS)
    return _build_dataflash_trace(
        path=path,
        raw_bytes=raw_bytes,
        trace_id=trace_id,
        mission_ref=mission_ref,
        source_format=ARDUPILOT_DATAFLASH_TEXT_FORMAT,
        gps_rows=all_gps_rows,
        battery_rows=_collect_rows(lines, "BAT", col_maps, _BAT_FALLBACK_COLS),
        mode_rows=_collect_rows(lines, "MODE", col_maps, _MODE_FALLBACK_COLS),
        wind_rows=(
            _collect_rows(lines, "NKF6", col_maps, _NKF6_FALLBACK_COLS)
            or _collect_rows(lines, "XKF6", col_maps, _NKF6_FALLBACK_COLS)
        ),
    )


def _build_dataflash_trace(
    *,
    path: Path,
    raw_bytes: bytes,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None,
    source_format: str,
    gps_rows: list[_RawRow],
    battery_rows: list[_RawRow],
    mode_rows: list[_RawRow],
    wind_rows: list[_RawRow],
    source_assumptions: list[str] | None = None,
) -> NormalizedFlightTrace:
    """Normalize decoded DataFlash rows from either text or binary readers."""
    gps_rows, selected_gps_instance = _select_gps_instance(gps_rows)
    all_gps_rows = _by_timeus(gps_rows)
    gps_rows = [row for row in all_gps_rows if _has_valid_fix(row)]
    dropped_gps = len(all_gps_rows) - len(gps_rows)
    if not gps_rows:
        raise FlightLogIngestionError(
            "Log file contains no GPS records with a position fix.",
            path=path,
            reason="no_gps_records",
        )

    bat = _Series.from_rows(_by_timeus(battery_rows))
    mode = _Series.from_rows(_by_timeus(mode_rows))
    # Wind comes from the first EKF core only (C == 0); filter before carry-forward
    # so interleaved multi-core rows never mask the core-0 estimate.
    nkf6 = _Series.from_rows(_core0_only(_by_timeus(wind_rows)))

    t0_us = _row_timeus(gps_rows[0])
    records = [
        _build_record(gps_row, t0_us, path=path, bat=bat, mode=mode, nkf6=nkf6)
        for gps_row in gps_rows
    ]

    assumptions = _build_assumptions(
        records,
        dropped_gps,
        source_assumptions=source_assumptions,
    )
    if selected_gps_instance is not None:
        assumptions.append(
            f"GPS receiver instance {selected_gps_instance} selected; other receivers ignored"
        )
    provenance = FlightTraceProvenance(
        source_format=source_format,
        raw_log_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        raw_log_filename=path.name,
        tool_version=tool_version(),
        parsing_assumptions=assumptions,
        missing_fields=_detect_missing_fields(records),
    )

    return NormalizedFlightTrace(
        schema_version=FLIGHT_TRACE_SCHEMA_VERSION,
        trace_id=trace_id,
        provenance=provenance,
        mission_ref=mission_ref,
        records=records,
    )


# ---------------------------------------------------------------------------
# File access
# ---------------------------------------------------------------------------


def _read_bytes(
    path: Path,
    *,
    max_bytes: int = DEFAULT_MAX_FLIGHT_LOG_BYTES,
) -> bytes:
    """Read one regular file through one descriptor with a strict byte cap."""
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_bytes > MAX_FLIGHT_LOG_BYTES:
        raise ValueError(
            "max_bytes may not exceed the 64 MiB flight-log process-safety limit"
        )
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
        descriptor = os.open(path, flags)
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise FlightLogIngestionError(
                "Flight log must be a regular file.",
                path=path,
                reason="non_regular_file",
            )
        if file_stat.st_size > max_bytes:
            raise FlightLogIngestionError(
                f"Flight log is {file_stat.st_size} bytes; the configured limit is {max_bytes} bytes.",
                path=path,
                reason="file_too_large",
            )
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = None
            raw_bytes = stream.read(max_bytes + 1)
        if len(raw_bytes) > max_bytes:
            raise FlightLogIngestionError(
                f"Flight log exceeds the configured limit of {max_bytes} bytes.",
                path=path,
                reason="file_too_large",
            )
        return raw_bytes
    except FlightLogIngestionError:
        raise
    except OSError as exc:
        raise FlightLogIngestionError(
            f"Cannot read log file: {exc}",
            path=path,
            reason="read_error",
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _decode_lines(raw_bytes: bytes, path: Path) -> list[str]:
    try:
        return raw_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise FlightLogIngestionError(
            "Log file is not valid UTF-8.",
            path=path,
            reason="encoding_error",
        ) from exc


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_fmt_lines(lines: list[str]) -> dict[str, dict[str, int]]:
    # FMT line: FMT, type_id, size, name, format, col1, col2, ...
    # Columns on data lines start at index 1 (index 0 is the message type name).
    col_maps: dict[str, dict[str, int]] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("FMT,"):
            continue
        parts = [p.strip() for p in stripped.split(",")]
        if len(parts) < 6:
            continue
        msg_name = parts[3]
        col_maps[msg_name] = {name: i + 1 for i, name in enumerate(parts[5:])}
    return col_maps


def _collect_rows(
    lines: list[str],
    msg_type: str,
    col_maps: dict[str, dict[str, int]],
    fallback: dict[str, int],
) -> list[_RawRow]:
    col_map = col_maps.get(msg_type, fallback)
    prefix = msg_type + ","
    rows: list[_RawRow] = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        parts = [p.strip() for p in stripped.split(",")]
        rows.append(
            {name: parts[idx] for name, idx in col_map.items() if idx < len(parts)}
        )
    return rows


def _by_timeus(rows: list[_RawRow]) -> list[_RawRow]:
    """Return rows sorted by TimeUS, dropping rows with absent or unparseable timestamps."""
    timed: list[tuple[int, _RawRow]] = []
    for row in rows:
        raw = row.get("TimeUS")
        if raw is None:
            continue
        try:
            timed.append((int(raw), row))
        except (TypeError, ValueError):
            continue
    timed.sort(key=lambda item: item[0])
    return [row for _, row in timed]


def _select_gps_instance(rows: list[_RawRow]) -> tuple[list[_RawRow], int | None]:
    """Use one GPS receiver so interleaved devices cannot create route jumps."""
    instances: set[int] = set()
    for row in rows:
        instance = _int(row, "I")
        if instance is not None:
            instances.add(instance)
    if not instances:
        return rows, None
    selected = 0 if 0 in instances else min(instances)
    return [row for row in rows if _int(row, "I") == selected], selected


def _core0_only(rows: list[_RawRow]) -> list[_RawRow]:
    """Keep only first-core EKF rows (C == 0); rows missing C are discarded."""
    return [row for row in rows if _int(row, "C") == 0]


def _has_valid_fix(row: _RawRow) -> bool:
    """True when a GPS row carries a usable position (>= 2D fix, not null island).

    Status is honoured only when present; logs without a Status column fall back
    to the null-island and parseability checks alone.
    """
    status = _int(row, "Status")
    if status is not None and status < _MIN_GPS_FIX_STATUS:
        return False
    lat = _float(row, "Lat")
    lon = _float(row, "Lng")
    if lat is None or lon is None:
        return False
    return not (lat == 0.0 and lon == 0.0)


def _row_timeus(row: _RawRow) -> int:
    return int(row["TimeUS"])


def _build_record(
    gps_row: _RawRow,
    t0_us: int,
    *,
    path: Path,
    bat: _Series,
    mode: _Series,
    nkf6: _Series,
) -> FlightTraceRecord:
    timeus = _row_timeus(gps_row)

    lat_deg = _float(gps_row, "Lat")
    lon_deg = _float(gps_row, "Lng")
    if lat_deg is None or lon_deg is None:
        raise FlightLogIngestionError(
            "GPS record missing Lat or Lng.",
            path=path,
            reason="missing_gps_position",
        )

    bat_row = bat.at(timeus)
    mode_row = mode.at(timeus)
    nkf6_row = nkf6.at(timeus)

    return FlightTraceRecord(
        timestamp_s=(timeus - t0_us) / 1_000_000.0,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        alt_amsl_m=_float(gps_row, "Alt"),
        groundspeed_mps=_float(gps_row, "Spd"),
        heading_deg=_float(gps_row, "GCrs"),
        battery_voltage_v=_float(bat_row, "Volt"),
        battery_current_a=_float(bat_row, "Curr"),
        battery_remaining_pct=_float(bat_row, "RemPct"),
        flight_mode=_str(mode_row, "Mode"),
        wind_east_mps=_float(nkf6_row, "VWE"),
        wind_north_mps=_float(nkf6_row, "VWN"),
    )


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _detect_missing_fields(records: list[FlightTraceRecord]) -> list[str]:
    """Report optional record fields that are absent from every record.

    Driven by the materialized records rather than source columns, so carry-forward
    gaps and missing FMT declarations are reflected accurately.
    """
    return [
        field
        for field in _OPTIONAL_RECORD_FIELDS
        if all(getattr(record, field) is None for record in records)
    ]


def _build_assumptions(
    records: list[FlightTraceRecord],
    dropped_gps: int,
    *,
    source_assumptions: list[str] | None = None,
) -> list[str]:
    assumptions = (
        list(source_assumptions)
        if source_assumptions is not None
        else [
            "timestamps derived from GPS.TimeUS relative to first GPS record",
            "altitude from GPS.Alt (AMSL when GPS Status >= 2)",
            "groundspeed from GPS.Spd",
            "heading from GPS.GCrs (ground course, not magnetic heading)",
        ]
    )
    if source_assumptions is None and any(
        record.wind_east_mps is not None or record.wind_north_mps is not None
        for record in records
    ):
        assumptions.append("wind estimate from NKF6 or XKF6 first core (C == 0)")
    if dropped_gps > 0:
        assumptions.append(
            f"excluded {dropped_gps} GPS record(s) without a 2D fix "
            f"(Status >= {_MIN_GPS_FIX_STATUS}) or at the null island (0, 0)"
        )
    return assumptions


# ---------------------------------------------------------------------------
# Value extraction helpers
# ---------------------------------------------------------------------------


def _float(row: _RawRow | None, key: str) -> float | None:
    if row is None:
        return None
    raw = row.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _int(row: _RawRow | None, key: str) -> int | None:
    if row is None:
        return None
    raw = row.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _str(row: _RawRow | None, key: str) -> str | None:
    if row is None:
        return None
    # Empty string from the log is treated as absent — mode name must be non-empty.
    value = row.get(key)
    return str(value) if value not in (None, "") else None


__all__ = [
    "ARDUPILOT_DATAFLASH_TEXT_FORMAT",
    "DEFAULT_MAX_FLIGHT_LOG_BYTES",
    "FlightLogIngestionError",
    "MAX_FLIGHT_LOG_BYTES",
    "ingest_dataflash_log",
]
