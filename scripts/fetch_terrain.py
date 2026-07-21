"""Fetch SRTM terrain elevation and write a terrain.yaml for GridTerrainProvider."""

import argparse
import math
import sys
from pathlib import Path

import yaml

try:
    import srtm
except ImportError:
    srtm = None  # type: ignore[assignment]


def _axis(start: float, stop: float, step: float) -> list[float]:
    if not all(math.isfinite(value) for value in (start, stop, step)):
        raise ValueError("grid bounds and step must be finite")
    if start >= stop or step <= 0.0:
        raise ValueError("grid bounds must increase and step must be positive")
    intervals = (stop - start) / step
    rounded_intervals = round(intervals)
    if not math.isclose(intervals, rounded_intervals, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("grid step must divide the requested bounds exactly")
    return [round(start + i * step, 8) for i in range(rounded_intervals + 1)]


def _sample_grid(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    step: float,
) -> tuple[list[float], list[float], list[list[float]]]:
    if not -90.0 <= lat_min < lat_max <= 90.0:
        raise ValueError("latitude bounds must lie between -90 and 90")
    if not -180.0 <= lon_min < lon_max <= 180.0:
        raise ValueError("longitude bounds must lie between -180 and 180")
    if srtm is None:
        raise RuntimeError(
            "'srtm.py' package not installed; run: pip install 'bvlos-sim[scripts]' "
            "or uv sync --extra scripts"
        )
    elevation_data = srtm.get_data()

    lats = _axis(lat_min, lat_max, step)
    lons = _axis(lon_min, lon_max, step)
    n_lat = len(lats)

    rows: list[list[float]] = []
    for i, row_lat in enumerate(lats):
        print(f"\r  row {i + 1}/{n_lat}", end="", flush=True)
        row: list[float] = []
        for col_lon in lons:
            elev = elevation_data.get_elevation(row_lat, col_lon)
            if elev is None:
                raise ValueError(
                    f"SRTM coverage missing at lat={row_lat}, lon={col_lon}"
                )
            try:
                value = float(elev)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"SRTM returned a non-numeric elevation at "
                    f"lat={row_lat}, lon={col_lon}"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(
                    f"SRTM returned a non-finite elevation at "
                    f"lat={row_lat}, lon={col_lon}"
                )
            row.append(value)
        rows.append(row)
    print()

    return lats, lons, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat_min", type=float)
    parser.add_argument("lat_max", type=float)
    parser.add_argument("lon_min", type=float)
    parser.add_argument("lon_max", type=float)
    parser.add_argument("step_deg", type=float, help="Grid step in degrees")
    parser.add_argument("--output", default="terrain.yaml", metavar="PATH")
    args = parser.parse_args()

    if srtm is None:
        sys.exit(
            "Error: 'srtm.py' package not installed. Run: "
            "pip install 'bvlos-sim[scripts]'"
        )

    if args.lat_min >= args.lat_max:
        sys.exit("Error: lat_min must be less than lat_max")
    if args.lon_min >= args.lon_max:
        sys.exit("Error: lon_min must be less than lon_max")
    if args.step_deg <= 0:
        sys.exit("Error: step_deg must be positive")
    if args.lat_min < -90.0 or args.lat_max > 90.0:
        sys.exit("Error: latitude bounds must lie between -90 and 90")
    if args.lon_min < -180.0 or args.lon_max > 180.0:
        sys.exit("Error: longitude bounds must lie between -180 and 180")

    print(
        f"Sampling SRTM elevation for "
        f"lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] "
        f"step {args.step_deg}° …"
    )
    print("(SRTM tiles will be downloaded and cached on first run)")

    try:
        lats, lons, rows = _sample_grid(
            args.lat_min, args.lat_max, args.lon_min, args.lon_max, args.step_deg
        )
    except (RuntimeError, ValueError) as exc:
        sys.exit(f"Error: {exc}")

    grid = {
        "origin_lat": lats[0],
        "origin_lon": lons[0],
        "step_lat_deg": args.step_deg,
        "step_lon_deg": args.step_deg,
        "elevations_m": rows,
    }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.dump(grid, default_flow_style=None, sort_keys=False), encoding="utf-8"
    )
    print(f"Wrote {out} ({len(lats)} rows × {len(lons)} cols)")


if __name__ == "__main__":
    main()
