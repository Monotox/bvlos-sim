"""Fetch Open-Meteo wind forecast and write a wind_grid.yaml for SpatiotemporalWindProvider."""

import argparse
import math
import sys
from datetime import date
from pathlib import Path

import yaml

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' package not installed. Run: uv sync")

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
_ALTITUDES_M = [10, 80, 120, 180]


def _decompose(speed: float, direction_deg: float) -> tuple[float, float]:
    """Meteorological convention: direction is FROM. Returns (east, north) m/s."""
    d = math.radians(direction_deg)
    return -speed * math.sin(d), -speed * math.cos(d)


def _fetch(lat: float, lon: float, target_date: date) -> dict[str, object]:
    hourly_vars = ",".join(
        f"wind_speed_{a}m,wind_direction_{a}m" for a in _ALTITUDES_M
    )
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": hourly_vars,
        "wind_speed_unit": "ms",
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
    }
    url = _ARCHIVE_URL if target_date < date.today() else _FORECAST_URL
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def _build_grid(
    data: dict[str, object],
    lat: float,
    lon: float,
    dep_hour: int,
    window_hours: int,
) -> dict[str, object]:
    hourly = data["hourly"]
    assert isinstance(hourly, dict)
    end_hour = min(dep_hour + window_hours, 24)
    n = end_hour - dep_hour
    if n < 1:
        raise ValueError(f"--departure-time {dep_hour:02d}:00 leaves no hours in window")

    times_s = [i * 3600 for i in range(n)]

    values = []
    for i in range(n):
        idx = dep_hour + i
        alt_blocks = []
        for alt in _ALTITUDES_M:
            raw_speed = hourly[f"wind_speed_{alt}m"][idx]  # type: ignore[index]
            raw_dir = hourly[f"wind_direction_{alt}m"][idx]  # type: ignore[index]
            speed = float(raw_speed) if raw_speed is not None else 0.0
            direction = float(raw_dir) if raw_dir is not None else 0.0
            east, north = _decompose(speed, direction)
            pair = [round(east, 4), round(north, 4)]
            # 2×2 uniform spatial grid — same wind value at all four corners
            alt_blocks.append([[pair, pair], [pair, pair]])
        values.append(alt_blocks)

    return {
        "axes": {
            "time_s": times_s,
            "altitude_m": list(_ALTITUDES_M),
            "lat": [round(lat - 0.01, 6), round(lat + 0.01, 6)],
            "lon": [round(lon - 0.01, 6), round(lon + 0.01, 6)],
        },
        "values": values,
    }


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
        help="Date to fetch (default: today). Past dates use the archive API.",
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

    try:
        target_date = date.fromisoformat(args.date) if args.date else date.today()
    except ValueError:
        sys.exit(f"Error: invalid --date value '{args.date}'; expected YYYY-MM-DD")

    try:
        dep_hour = int(args.departure_time.split(":")[0])
        if not 0 <= dep_hour <= 23:
            raise ValueError
    except (ValueError, IndexError):
        sys.exit(
            f"Error: invalid --departure-time '{args.departure_time}'; expected HH:MM (00–23)"
        )

    print(
        f"Fetching wind for lat={args.lat}, lon={args.lon}, "
        f"date={target_date}, departure={dep_hour:02d}:00 UTC, "
        f"window={args.window_hours}h …"
    )

    data = _fetch(args.lat, args.lon, target_date)
    grid = _build_grid(data, args.lat, args.lon, dep_hour, args.window_hours)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.dump(grid, default_flow_style=None, sort_keys=False))
    n_times = len(grid["axes"]["time_s"])
    print(f"Wrote {out} ({n_times} time steps × {len(_ALTITUDES_M)} altitude bands)")


if __name__ == "__main__":
    main()
