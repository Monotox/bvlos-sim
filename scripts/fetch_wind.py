"""Fetch Open-Meteo wind forecast and write a wind_grid.yaml for SpatiotemporalWindProvider."""

import argparse
import math
import sys
from datetime import date
from datetime import datetime
from pathlib import Path

import yaml

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"
_HISTORICAL_FORECAST_START = date(2022, 1, 1)
_ALTITUDES_M = [10, 80, 120, 180]
_SPATIAL_EPSILON_DEG = 1e-6


def _decompose(speed: float, direction_deg: float) -> tuple[float, float]:
    """Meteorological convention: direction is FROM. Returns (east, north) m/s."""
    d = math.radians(direction_deg)
    return -speed * math.sin(d), -speed * math.cos(d)


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in value.items()}


def _fetch(lat: float, lon: float, target_date: date) -> dict[str, object]:
    if target_date < _HISTORICAL_FORECAST_START:
        raise ValueError(
            "80/120/180 m historical forecast levels are unavailable before "
            f"{_HISTORICAL_FORECAST_START.isoformat()}"
        )
    if requests is None:
        raise RuntimeError(
            "'requests' package not installed; run: "
            "pip install 'bvlos-sim[scripts]' or uv sync --extra scripts"
        )
    hourly_vars = ",".join(f"wind_speed_{a}m,wind_direction_{a}m" for a in _ALTITUDES_M)
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": hourly_vars,
        "wind_speed_unit": "ms",
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
    }
    url = _HISTORICAL_FORECAST_URL if target_date < date.today() else _FORECAST_URL
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    payload: object = resp.json()
    if not isinstance(payload, dict):
        raise ValueError("Open-Meteo response root must be an object")
    return {str(key): item for key, item in payload.items()}


def _build_grid(
    data: dict[str, object],
    lat: float,
    lon: float,
    dep_hour: int,
    window_hours: int,
) -> dict[str, object]:
    if not math.isfinite(lat) or not -89.99 <= lat <= 89.99:
        raise ValueError(
            "latitude must be finite and leave room for the 0.01-degree grid"
        )
    if not math.isfinite(lon) or not -179.99 <= lon <= 179.99:
        raise ValueError(
            "longitude must be finite and leave room for the 0.01-degree grid"
        )
    surface_elevation_m = _finite_number(data.get("elevation"), field="elevation")
    hourly = _object_dict(data.get("hourly"))
    if not hourly:
        raise ValueError("Open-Meteo response missing hourly wind data")
    end_hour = dep_hour + window_hours
    if end_hour > 24:
        raise ValueError(
            "requested wind window extends beyond the available UTC day; "
            "fetch a shorter window or the following day separately"
        )
    n = end_hour - dep_hour
    if n < 2:
        raise ValueError("wind grids require at least two consecutive hourly samples")

    times_s = [i * 3600 for i in range(n)]

    time_values = _required_hourly_series(hourly, "time")
    if len(time_values) < end_hour:
        raise ValueError(
            "Open-Meteo response does not cover the complete requested time window"
        )
    selected_datetimes = [
        _hourly_datetime(time_values[index], index=index)
        for index in range(dep_hour, end_hour)
    ]
    if selected_datetimes[0].hour != dep_hour or selected_datetimes[0].minute != 0:
        raise ValueError(
            "Open-Meteo hourly timestamps do not align with departure time"
        )
    if any(
        (later - earlier).total_seconds() != 3600.0
        for earlier, later in zip(
            selected_datetimes,
            selected_datetimes[1:],
            strict=False,
        )
    ):
        raise ValueError("Open-Meteo hourly timestamps are not consecutive")

    required_series: dict[str, list[object]] = {}
    for alt in _ALTITUDES_M:
        for prefix in ("wind_speed", "wind_direction"):
            key = f"{prefix}_{alt}m"
            series = _required_hourly_series(hourly, key)
            if len(series) != len(time_values):
                raise ValueError(
                    f"Open-Meteo hourly series {key!r} length does not match time"
                )
            required_series[key] = series

    values = []
    for i in range(n):
        idx = dep_hour + i
        alt_blocks = []
        for alt in _ALTITUDES_M:
            speed = _finite_number(
                required_series[f"wind_speed_{alt}m"][idx],
                field=f"wind_speed_{alt}m[{idx}]",
            )
            direction = _finite_number(
                required_series[f"wind_direction_{alt}m"][idx],
                field=f"wind_direction_{alt}m[{idx}]",
            )
            if speed < 0.0:
                raise ValueError(f"wind_speed_{alt}m[{idx}] must be non-negative")
            if not 0.0 <= direction <= 360.0:
                raise ValueError(
                    f"wind_direction_{alt}m[{idx}] must be between 0 and 360 degrees"
                )
            east, north = _decompose(speed, direction)
            pair = [round(east, 4), round(north, 4)]
            # 2×2 uniform spatial grid — same wind value at all four corners
            alt_blocks.append([[pair, pair], [pair, pair]])
        values.append(alt_blocks)

    return {
        "axes": {
            "time_s": times_s,
            # Open-Meteo wind levels are heights above ground, while the
            # provider queries this axis using altitude AMSL.
            "altitude_m": [surface_elevation_m + value for value in _ALTITUDES_M],
            "lat": [
                round(lat - _SPATIAL_EPSILON_DEG, 6),
                round(lat + _SPATIAL_EPSILON_DEG, 6),
            ],
            "lon": [
                round(lon - _SPATIAL_EPSILON_DEG, 6),
                round(lon + _SPATIAL_EPSILON_DEG, 6),
            ],
        },
        "values": values,
        "metadata": {
            "source": "Open-Meteo",
            "source_point": {"lat": lat, "lon": lon},
            "source_elevation_amsl_m": surface_elevation_m,
            "vertical_reference": "AMSL",
            "spatial_model": "single-point constant field",
        },
    }


def _required_hourly_series(hourly: dict[str, object], key: str) -> list[object]:
    value = hourly.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Open-Meteo response missing hourly series {key!r}")
    return value


def _finite_number(value: object, *, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Open-Meteo value {field} must be numeric") from exc
    if not math.isfinite(number):
        raise ValueError(f"Open-Meteo value {field} must be finite")
    return number


def _hourly_datetime(value: object, *, index: int) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"Open-Meteo time[{index}] must be an ISO-8601 string")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"Open-Meteo time[{index}] must be a valid ISO-8601 timestamp"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat", type=float, help="Centre latitude")
    parser.add_argument("lon", type=float, help="Centre longitude")
    parser.add_argument(
        "--departure-time",
        default="00:00",
        metavar="HH:MM",
        help="UTC departure time; sets time_s=0 in output (default: 00:00)",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help=(
            "Date to fetch (default: today). Past dates from 2022 onward use "
            "the historical forecast API."
        ),
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=4,
        metavar="N",
        help="Number of hourly slices starting from --departure-time (default: 4)",
    )
    parser.add_argument("--output", default="wind_grid.yaml", metavar="PATH")
    args = parser.parse_args()

    if requests is None:
        sys.exit(
            "Error: 'requests' package not installed. Run: "
            "pip install 'bvlos-sim[scripts]'"
        )

    if args.window_hours < 2:
        sys.exit("Error: --window-hours must provide at least two hourly samples")

    try:
        target_date = date.fromisoformat(args.date) if args.date else date.today()
    except ValueError:
        sys.exit(f"Error: invalid --date value '{args.date}'; expected YYYY-MM-DD")

    try:
        departure = datetime.strptime(args.departure_time, "%H:%M")
        if departure.minute != 0:
            raise ValueError
        dep_hour = departure.hour
    except ValueError:
        sys.exit(
            f"Error: invalid --departure-time '{args.departure_time}'; "
            "expected an exact UTC hour as HH:00"
        )

    if not math.isfinite(args.lat) or not -89.99 <= args.lat <= 89.99:
        sys.exit("Error: lat must leave room for the 0.01-degree grid")
    if not math.isfinite(args.lon) or not -179.99 <= args.lon <= 179.99:
        sys.exit("Error: lon must leave room for the 0.01-degree grid")

    print(
        f"Fetching wind for lat={args.lat}, lon={args.lon}, "
        f"date={target_date}, departure={dep_hour:02d}:00 UTC, "
        f"window={args.window_hours}h …"
    )

    try:
        data = _fetch(args.lat, args.lon, target_date)
        grid = _build_grid(data, args.lat, args.lon, dep_hour, args.window_hours)
    except (RuntimeError, ValueError) as exc:
        sys.exit(f"Error: {exc}")

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.dump(grid, default_flow_style=None, sort_keys=False), encoding="utf-8"
    )
    n_times = len(grid["axes"]["time_s"])
    print(f"Wrote {out} ({n_times} time steps × {len(_ALTITUDES_M)} altitude bands)")


if __name__ == "__main__":
    main()
