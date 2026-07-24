"""Library-backed PX4 ULog ingestion."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from bvlos_sim.adapters.flight_log.dataflash import (
    DEFAULT_MAX_FLIGHT_LOG_BYTES,
    FlightLogIngestionError,
    _RawRow,
    _build_dataflash_trace,
    _read_bytes,
)
from bvlos_sim.schemas.flight_log import FlightTraceMissionRef, NormalizedFlightTrace

PX4_ULOG_FORMAT = "px4_ulog"
ULOG_MAGIC = b"ULog\x01\x12\x35"

_PX4_NAV_STATES = {
    0: "MANUAL",
    1: "ALTCTL",
    2: "POSCTL",
    3: "AUTO_MISSION",
    4: "AUTO_LOITER",
    5: "AUTO_RTL",
    6: "POSITION_SLOW",
    7: "GUIDED_COURSE",
    8: "ALTITUDE_CRUISE",
    9: "FREE3",
    10: "ACRO",
    11: "FREE2",
    12: "DESCEND",
    13: "TERMINATION",
    14: "OFFBOARD",
    15: "STAB",
    16: "FREE1",
    17: "AUTO_TAKEOFF",
    18: "AUTO_LAND",
    19: "AUTO_FOLLOW_TARGET",
    20: "AUTO_PRECLAND",
    21: "ORBIT",
    22: "AUTO_VTOL_TAKEOFF",
    23: "EXTERNAL1",
    24: "EXTERNAL2",
    25: "EXTERNAL3",
    26: "EXTERNAL4",
    27: "EXTERNAL5",
    28: "EXTERNAL6",
    29: "EXTERNAL7",
    30: "EXTERNAL8",
}

type _DatasetKey = tuple[str, int]
type _DatasetMap = dict[_DatasetKey, Mapping[str, Sequence[Any]]]


def ingest_ulog(
    path: Path,
    *,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None = None,
    max_bytes: int = DEFAULT_MAX_FLIGHT_LOG_BYTES,
) -> NormalizedFlightTrace:
    """Ingest a PX4 ``.ulg`` controller log using pyulog."""
    raw_bytes = _read_bytes(path, max_bytes=max_bytes)
    return _ingest_ulog_bytes(
        path,
        raw_bytes=raw_bytes,
        trace_id=trace_id,
        mission_ref=mission_ref,
    )


def _ingest_ulog_bytes(
    path: Path,
    *,
    raw_bytes: bytes,
    trace_id: str,
    mission_ref: FlightTraceMissionRef | None,
) -> NormalizedFlightTrace:
    """Parse an already bounded immutable snapshot of a ULog file."""
    if not raw_bytes.startswith(ULOG_MAGIC):
        raise FlightLogIngestionError(
            "File does not have a PX4 ULog header.",
            path=path,
            reason="format_mismatch",
        )

    try:
        with TemporaryDirectory(prefix="bvlos-ulog-") as temp_dir:
            snapshot = Path(temp_dir) / (path.name or "flight.ulg")
            snapshot.write_bytes(raw_bytes)
            datasets = _read_ulog_datasets(snapshot)
        gps_rows = _gps_rows(_dataset(datasets, "vehicle_gps_position"))
        battery_rows = _battery_rows(_dataset(datasets, "battery_status"))
        mode_rows = _mode_rows(_dataset(datasets, "vehicle_status"))
        wind_rows = _wind_rows(
            _first_dataset(datasets, ("wind", "estimator_wind", "wind_estimate"))
        )
    except FlightLogIngestionError:
        raise
    except Exception as exc:
        raise FlightLogIngestionError(
            f"Could not parse PX4 ULog: {exc}",
            path=path,
            reason="parse_error",
        ) from exc

    assumptions = [
        "timestamps derived from vehicle_gps_position.timestamp relative to first valid GPS record",
        "altitude from vehicle_gps_position altitude_msl_m or legacy alt (AMSL)",
        "groundspeed from vehicle_gps_position.vel_m_s",
        "heading from vehicle_gps_position.cog_rad (ground course, not magnetic heading)",
        "battery fields carried forward from battery_status",
    ]
    if wind_rows:
        assumptions.append("wind estimate carried forward from the PX4 wind topic")

    return _build_dataflash_trace(
        path=path,
        raw_bytes=raw_bytes,
        trace_id=trace_id,
        mission_ref=mission_ref,
        source_format=PX4_ULOG_FORMAT,
        gps_rows=gps_rows,
        battery_rows=battery_rows,
        mode_rows=mode_rows,
        wind_rows=wind_rows,
        source_assumptions=assumptions,
    )


def _read_ulog_datasets(path: Path) -> _DatasetMap:
    try:
        from pyulog import ULog
    except ImportError as exc:
        raise FlightLogIngestionError(
            "PX4 ULog ingestion requires the 'flight-logs' optional dependency.",
            path=path,
            reason="missing_dependency",
        ) from exc

    parsed = ULog(str(path))
    return {
        (str(item.name), int(item.multi_id)): item.data for item in parsed.data_list
    }


def _dataset(datasets: _DatasetMap, name: str) -> Mapping[str, Sequence[Any]] | None:
    return datasets.get((name, 0)) or next(
        (
            data
            for (dataset_name, _multi_id), data in datasets.items()
            if dataset_name == name
        ),
        None,
    )


def _first_dataset(
    datasets: _DatasetMap,
    names: Sequence[str],
) -> Mapping[str, Sequence[Any]] | None:
    return next((data for name in names if (data := _dataset(datasets, name))), None)


def _rows(data: Mapping[str, Sequence[Any]] | None) -> list[dict[str, object]]:
    if not data or "timestamp" not in data:
        return []
    count = len(data["timestamp"])
    return [
        {
            str(field): _python_scalar(values[index])
            for field, values in data.items()
            if index < len(values)
        }
        for index in range(count)
    ]


def _gps_rows(data: Mapping[str, Sequence[Any]] | None) -> list[_RawRow]:
    rows: list[_RawRow] = []
    for source in _rows(data):
        lat = _scaled_degrees(_first_number(source, ("latitude_deg", "lat")))
        lon = _scaled_degrees(_first_number(source, ("longitude_deg", "lon")))
        if lat is None or lon is None:
            continue
        speed = _number(source.get("vel_m_s"))
        if speed is None:
            north = _number(source.get("vel_n_m_s"))
            east = _number(source.get("vel_e_m_s"))
            speed = (
                math.hypot(north, east)
                if north is not None and east is not None
                else None
            )
        course_rad = _number(source.get("cog_rad"))
        rows.append(
            {
                "TimeUS": _timestamp_us(source),
                "Status": source.get("fix_type"),
                "Lat": lat,
                "Lng": lon,
                "Alt": _altitude_m(source),
                "Spd": speed,
                "GCrs": (
                    math.degrees(course_rad) % 360.0 if course_rad is not None else None
                ),
            }
        )
    return rows


def _battery_rows(data: Mapping[str, Sequence[Any]] | None) -> list[_RawRow]:
    rows: list[_RawRow] = []
    for source in _rows(data):
        remaining = _number(source.get("remaining"))
        if remaining is not None:
            remaining = remaining * 100.0 if 0.0 <= remaining <= 1.0 else remaining
            if not 0.0 <= remaining <= 100.0:
                remaining = None
        voltage = _number(source.get("voltage_v"))
        if voltage is not None and voltage <= 0.0:
            voltage = None
        current = _number(source.get("current_a"))
        if current == -1.0:
            current = None
        rows.append(
            {
                "TimeUS": _timestamp_us(source),
                "Volt": voltage,
                "Curr": current,
                "RemPct": remaining,
            }
        )
    return rows


def _mode_rows(data: Mapping[str, Sequence[Any]] | None) -> list[_RawRow]:
    rows: list[_RawRow] = []
    for source in _rows(data):
        raw_state = source.get("nav_state")
        state = _integer(raw_state)
        mode = (
            _PX4_NAV_STATES.get(state, f"NAV_STATE_{state}")
            if state is not None
            else None
        )
        rows.append({"TimeUS": _timestamp_us(source), "Mode": mode})
    return rows


def _wind_rows(data: Mapping[str, Sequence[Any]] | None) -> list[_RawRow]:
    rows: list[_RawRow] = []
    for source in _rows(data):
        north = _first_number(
            source,
            ("windspeed_north", "wind_north", "wind_velocity_north"),
        )
        east = _first_number(
            source,
            ("windspeed_east", "wind_east", "wind_velocity_east"),
        )
        if north is None and east is None:
            continue
        rows.append(
            {
                "TimeUS": _timestamp_us(source),
                "C": 0,
                "VWN": north,
                "VWE": east,
            }
        )
    return rows


def _timestamp_us(source: Mapping[str, object]) -> int:
    timestamp = _integer(source.get("timestamp"))
    if timestamp is None or timestamp < 0:
        raise ValueError("ULog dataset row has no valid timestamp")
    return timestamp


def _scaled_degrees(value: object) -> float | None:
    number = _number(value)
    if number is None:
        return None
    return number / 10_000_000.0 if abs(number) > 180.0 else number


def _altitude_m(source: Mapping[str, object]) -> float | None:
    direct = _first_number(source, ("altitude_msl_m", "alt_amsl_m"))
    if direct is not None:
        return direct
    millimetres = _number(source.get("alt"))
    return millimetres / 1_000.0 if millimetres is not None else None


def _first_number(source: Mapping[str, object], names: Sequence[str]) -> float | None:
    return next(
        (value for name in names if (value := _number(source.get(name))) is not None),
        None,
    )


def _number(value: object) -> float | None:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: object) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None


def _python_scalar(value: Any) -> object:
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    return value


__all__ = ["PX4_ULOG_FORMAT", "ULOG_MAGIC", "ingest_ulog"]
