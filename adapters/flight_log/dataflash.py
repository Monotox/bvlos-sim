"""ArduPilot DataFlash text-format (.log) ingestion adapter."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import TypeAlias

from adapters.version import tool_version
from schemas.flight_log import (
    FLIGHT_TRACE_SCHEMA_VERSION,
    FlightTraceMissionRef,
    FlightTraceProvenance,
    FlightTraceRecord,
    NormalizedFlightTrace,
)

ARDUPILOT_DATAFLASH_TEXT_FORMAT = "ardupilot_dataflash_text"

_SUPPORTED_EXTENSION = ".log"

# Fallback column positions used when no FMT line is present for that message type.
# Values are column indices in the data line (index 0 = message type name).
_GPS_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1,
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

_RawRow: TypeAlias = dict[str, str]


class FlightLogIngestionError(ValueError):
    """Raised when a log file cannot be ingested."""

    def __init__(self, message: str, *, path: Path, reason: str) -> None:
        super().__init__(message)
        self.path = path
        self.reason = reason


def ingest_dataflash_log(
    path: Path,
    *,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None = None,
) -> NormalizedFlightTrace:
    """Ingest an ArduPilot DataFlash text log (.log) into a NormalizedFlightTrace.

    Raises FlightLogIngestionError if the file cannot be read or contains no GPS records.
    """
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        raise FlightLogIngestionError(
            f"Cannot read log file: {exc}",
            path=path,
            reason="read_error",
        ) from exc

    sha256 = hashlib.sha256(raw_bytes).hexdigest()

    try:
        lines = raw_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise FlightLogIngestionError(
            "Log file is not valid UTF-8.",
            path=path,
            reason="encoding_error",
        ) from exc

    col_maps = _parse_fmt_lines(lines)
    gps_rows = _collect_rows(lines, "GPS", col_maps, _GPS_FALLBACK_COLS)
    bat_rows = _collect_rows(lines, "BAT", col_maps, _BAT_FALLBACK_COLS)
    mode_rows = _collect_rows(lines, "MODE", col_maps, _MODE_FALLBACK_COLS)
    nkf6_rows = _collect_rows(lines, "NKF6", col_maps, _NKF6_FALLBACK_COLS)
    if not nkf6_rows:
        nkf6_rows = _collect_rows(lines, "XKF6", col_maps, _NKF6_FALLBACK_COLS)

    if not gps_rows:
        raise FlightLogIngestionError(
            "Log file contains no GPS records.",
            path=path,
            reason="no_gps_records",
        )

    gps_cols = col_maps.get("GPS", {})
    missing_fields = _detect_missing_fields(
        bat_rows=bat_rows,
        nkf6_rows=nkf6_rows,
        mode_rows=mode_rows,
        gps_cols=gps_cols,
    )

    assumptions = _build_assumptions(nkf6_present=bool(nkf6_rows))
    provenance = FlightTraceProvenance(
        source_format=ARDUPILOT_DATAFLASH_TEXT_FORMAT,
        raw_log_sha256=sha256,
        raw_log_filename=path.name,
        tool_version=tool_version(),
        parsing_assumptions=assumptions,
        missing_fields=missing_fields,
    )

    t0_us = _parse_timeus(gps_rows[0])
    records = [
        _build_record(gps_row, t0_us, bat_rows=bat_rows, mode_rows=mode_rows, nkf6_rows=nkf6_rows)
        for gps_row in gps_rows
    ]

    return NormalizedFlightTrace(
        schema_version=FLIGHT_TRACE_SCHEMA_VERSION,
        trace_id=trace_id,
        provenance=provenance,
        mission_ref=mission_ref,
        records=records,
    )


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_fmt_lines(lines: list[str]) -> dict[str, dict[str, int]]:
    """Return a mapping of message_type → {column_name: column_index} from FMT lines.

    Column index 0 is the message type name on data lines, so FMT columns start at 1.
    """
    col_maps: dict[str, dict[str, int]] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("FMT,"):
            continue
        parts = [p.strip() for p in stripped.split(",")]
        # FMT, type_id, size, name, format, col1, col2, ...
        if len(parts) < 6:
            continue
        msg_name = parts[3]
        col_names = parts[5:]
        col_maps[msg_name] = {name: idx + 1 for idx, name in enumerate(col_names)}
    return col_maps


def _collect_rows(
    lines: list[str],
    msg_type: str,
    col_maps: dict[str, dict[str, int]],
    fallback: dict[str, int],
) -> list[_RawRow]:
    """Collect all data lines for msg_type as dicts keyed by column name."""
    col_map = col_maps.get(msg_type, fallback)
    rows: list[_RawRow] = []
    prefix = msg_type + ","
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith(prefix):
            continue
        parts = [p.strip() for p in stripped.split(",")]
        row: _RawRow = {}
        for col_name, col_idx in col_map.items():
            if col_idx < len(parts):
                row[col_name] = parts[col_idx]
        rows.append(row)
    return rows


def _parse_timeus(row: _RawRow) -> int:
    raw = row.get("TimeUS", "0")
    try:
        return int(raw)
    except ValueError:
        return 0


def _carry_forward(
    rows: list[_RawRow], timeus: int
) -> _RawRow | None:
    """Return the latest row with TimeUS <= timeus, or None."""
    result: _RawRow | None = None
    for row in rows:
        if _parse_timeus(row) <= timeus:
            result = row
        else:
            break
    return result


def _build_record(
    gps_row: _RawRow,
    t0_us: int,
    *,
    bat_rows: list[_RawRow],
    mode_rows: list[_RawRow],
    nkf6_rows: list[_RawRow],
) -> FlightTraceRecord:
    timeus = _parse_timeus(gps_row)
    timestamp_s = (timeus - t0_us) / 1_000_000.0

    lat_deg = _float(gps_row, "Lat")
    lon_deg = _float(gps_row, "Lng")
    if lat_deg is None or lon_deg is None:
        raise FlightLogIngestionError(
            "GPS record missing Lat or Lng.",
            path=Path("<unknown>"),
            reason="missing_gps_position",
        )

    bat = _carry_forward(bat_rows, timeus)
    mode = _carry_forward(mode_rows, timeus)
    nkf6 = _carry_forward(nkf6_rows, timeus)

    wind_east: float | None = None
    wind_north: float | None = None
    if nkf6 is not None and _int(nkf6, "C") == 0:
        wind_north = _float(nkf6, "VWN")
        wind_east = _float(nkf6, "VWE")

    return FlightTraceRecord(
        timestamp_s=timestamp_s,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        alt_amsl_m=_float(gps_row, "Alt"),
        groundspeed_mps=_float(gps_row, "Spd"),
        heading_deg=_float(gps_row, "GCrs"),
        battery_voltage_v=_float(bat, "Volt") if bat else None,
        battery_current_a=_float(bat, "Curr") if bat else None,
        battery_remaining_pct=_float(bat, "RemPct") if bat else None,
        flight_mode=_str(mode, "Mode") if mode else None,
        wind_east_mps=wind_east,
        wind_north_mps=wind_north,
    )


def _detect_missing_fields(
    *,
    bat_rows: list[_RawRow],
    nkf6_rows: list[_RawRow],
    mode_rows: list[_RawRow],
    gps_cols: dict[str, int],
) -> list[str]:
    missing: list[str] = []
    if not bat_rows:
        missing.extend(["battery_voltage_v", "battery_current_a", "battery_remaining_pct"])
    if not nkf6_rows:
        missing.extend(["wind_east_mps", "wind_north_mps"])
    if not mode_rows:
        missing.append("flight_mode")
    if gps_cols and "GCrs" not in gps_cols:
        missing.append("heading_deg")
    if gps_cols and "Alt" not in gps_cols:
        missing.append("alt_amsl_m")
    return missing


def _build_assumptions(*, nkf6_present: bool) -> list[str]:
    assumptions = [
        "timestamps derived from GPS.TimeUS relative to first GPS record",
        "altitude from GPS.Alt (AMSL when GPS Status >= 2)",
        "groundspeed from GPS.Spd",
        "heading from GPS.GCrs (ground course, not magnetic heading)",
    ]
    if nkf6_present:
        assumptions.append("wind estimate from NKF6 or XKF6 first core (C == 0)")
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
    except ValueError:
        return None


def _int(row: _RawRow | None, key: str) -> int | None:
    if row is None:
        return None
    raw = row.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _str(row: _RawRow | None, key: str) -> str | None:
    if row is None:
        return None
    return row.get(key) or None


__all__ = [
    "ARDUPILOT_DATAFLASH_TEXT_FORMAT",
    "FlightLogIngestionError",
    "ingest_dataflash_log",
]
