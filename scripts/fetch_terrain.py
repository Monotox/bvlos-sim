"""Fetch SRTM terrain elevation and write a terrain.yaml for GridTerrainProvider."""

import argparse
import sys
from pathlib import Path

import yaml

try:
    import srtm
except ImportError:
    sys.exit(
        "Error: 'srtm.py' package not installed. "
        "Run: uv sync --extra scripts"
    )


def _sample_grid(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    step: float,
) -> tuple[list[float], list[float], list[list[float]]]:
    elevation_data = srtm.get_data()

    lats: list[float] = []
    lat = lat_min
    while lat <= lat_max + step * 1e-6:
        lats.append(round(lat, 8))
        lat += step

    lons: list[float] = []
    lon = lon_min
    while lon <= lon_max + step * 1e-6:
        lons.append(round(lon, 8))
        lon += step

    rows: list[list[float]] = []
    for row_lat in lats:
        row: list[float] = []
        for col_lon in lons:
            elev = elevation_data.get_elevation(row_lat, col_lon)
            row.append(float(elev) if elev is not None else 0.0)
        rows.append(row)

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

    if args.lat_min >= args.lat_max:
        sys.exit("Error: lat_min must be less than lat_max")
    if args.lon_min >= args.lon_max:
        sys.exit("Error: lon_min must be less than lon_max")
    if args.step_deg <= 0:
        sys.exit("Error: step_deg must be positive")

    print(
        f"Sampling SRTM elevation for "
        f"lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] "
        f"step {args.step_deg}° …"
    )
    print("(SRTM tiles will be downloaded and cached on first run)")

    lats, lons, rows = _sample_grid(
        args.lat_min, args.lat_max, args.lon_min, args.lon_max, args.step_deg
    )

    grid = {
        "origin_lat": lats[0],
        "origin_lon": lons[0],
        "step_lat_deg": args.step_deg,
        "step_lon_deg": args.step_deg,
        "elevations_m": rows,
    }

    out = Path(args.output)
    out.write_text(yaml.dump(grid, default_flow_style=None, sort_keys=False))
    print(f"Wrote {out} ({len(lats)} rows × {len(lons)} cols)")


if __name__ == "__main__":
    main()
