"""ArduPilot DataFlash text-format (.log) ingestion adapter."""

from __future__ import annotations

import hashlib
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

# Fallback column indices used when no FMT line declares the message type.
# Index 0 on data lines is the message type name; FMT-named columns start at 1.
_GPS_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1, "Lat": 7, "Lng": 8, "Alt": 9, "Spd": 10, "GCrs": 11,
}
_BAT_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1, "Volt": 2, "Curr": 4, "RemPct": 6,
}
_MODE_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1, "Mode": 2,
}
_NKF6_FALLBACK_COLS: dict[str, int] = {
    "TimeUS": 1, "C": 2, "VWN": 3, "VWE": 4,
}

type _RawRow = dict[str, str]


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

    try:
        lines = raw_bytes.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise FlightLogIngestionError(
            "Log file is not valid UTF-8.",
            path=path,
            reason="encoding_error",
        ) from exc

    sha256 = hashlib.sha256(raw_bytes).hexdigest()
    col_maps = _parse_fmt_lines(lines)

    gps_rows = _by_timeus(_collect_rows(lines, "GPS", col_maps, _GPS_FALLBACK_COLS))
    bat_rows = _by_timeus(_collect_rows(lines, "BAT", col_maps, _BAT_FALLBACK_COLS))
    mode_rows = _by_timeus(_collect_rows(lines, "MODE", col_maps, _MODE_FALLBACK_COLS))
    nkf6_rows = _by_timeus(
        _collect_rows(lines, "NKF6", col_maps, _NKF6_FALLBACK_COLS)
        or _collect_rows(lines, "XKF6", col_maps, _NKF6_FALLBACK_COLS)
    )

    if not gps_rows:
        raise FlightLogIngestionError(
            "Log file contains no GPS records.",
            path=path,
            reason="no_gps_records",
        )

    # Use the FMT-declared columns when available, falling back to hardcoded positions.
    effective_gps_cols = col_maps.get("GPS") or _GPS_FALLBACK_COLS

    provenance = FlightTraceProvenance(
        source_format=ARDUPILOT_DATAFLASH_TEXT_FORMAT,
        raw_log_sha256=sha256,
        raw_log_filename=path.name,
        tool_version=tool_version(),
        parsing_assumptions=_build_assumptions(nkf6_present=bool(nkf6_rows)),
        missing_fields=_detect_missing_fields(
            bat_rows=bat_rows,
            nkf6_rows=nkf6_rows,
            mode_rows=mode_rows,
            gps_cols=effective_gps_cols,
        ),
    )

    t0_us = _row_timeus(gps_rows[0])
    records = [
        _build_record(
            gps_row,
            t0_us,
            path=path,
            bat_rows=bat_rows,
            mode_rows=mode_rows,
            nkf6_rows=nkf6_rows,
        )
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
        except ValueError:
            continue
    timed.sort(key=lambda item: item[0])
    return [row for _, row in timed]


def _row_timeus(row: _RawRow) -> int:
    return int(row["TimeUS"])


def _carry_forward(rows: list[_RawRow], timeus: int) -> _RawRow | None:
    # rows must be pre-sorted by TimeUS (guaranteed by _by_timeus at collection time).
    result: _RawRow | None = None
    for row in rows:
        if _row_timeus(row) <= timeus:
            result = row
        else:
            break
    return result


def _build_record(
    gps_row: _RawRow,
    t0_us: int,
    *,
    path: Path,
    bat_rows: list[_RawRow],
    mode_rows: list[_RawRow],
    nkf6_rows: list[_RawRow],
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

    bat = _carry_forward(bat_rows, timeus)
    mode = _carry_forward(mode_rows, timeus)
    nkf6 = _carry_forward(nkf6_rows, timeus)
    # Only trust the first EKF core (C == 0); discard multi-core wind estimates.
    nkf6_core0 = nkf6 if _int(nkf6, "C") == 0 else None

    return FlightTraceRecord(
        timestamp_s=(timeus - t0_us) / 1_000_000.0,
        lat_deg=lat_deg,
        lon_deg=lon_deg,
        alt_amsl_m=_float(gps_row, "Alt"),
        groundspeed_mps=_float(gps_row, "Spd"),
        heading_deg=_float(gps_row, "GCrs"),
        battery_voltage_v=_float(bat, "Volt"),
        battery_current_a=_float(bat, "Curr"),
        battery_remaining_pct=_float(bat, "RemPct"),
        flight_mode=_str(mode, "Mode"),
        wind_east_mps=_float(nkf6_core0, "VWE"),
        wind_north_mps=_float(nkf6_core0, "VWN"),
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
    if "GCrs" not in gps_cols:
        missing.append("heading_deg")
    if "Alt" not in gps_cols:
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
    # Empty string from the log is treated as absent — mode name must be non-empty.
    return row.get(key) or None


__all__ = [
    "ARDUPILOT_DATAFLASH_TEXT_FORMAT",
    "FlightLogIngestionError",
    "ingest_dataflash_log",
]
