"""Fetch terrain, wind, and landing zones for a mission area in one command.

Writes three asset files ready to paste into the `assets:` section of a
mission YAML. The terrain script requires `uv sync --extra scripts` first.

Example:
    uv run python scripts/fetch_all.py 47.05 8.30 --departure-time 14:00

Output:
    terrain.yaml, wind_grid.yaml, landing_zones.geojson (in --output-dir)
    Prints the assets: block to paste into your mission YAML.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import yaml

# sys.path extended before sibling-script imports below.
_SCRIPTS = Path(__file__).parent
sys.path.insert(0, str(_SCRIPTS))

try:
    from fetch_terrain import _sample_grid  # noqa: E402
except ImportError:
    _sample_grid = None  # srtm.py not installed; handled below

from fetch_wind import _ALTITUDES_M  # noqa: E402
from fetch_wind import _build_grid as _build_wind_grid  # noqa: E402
from fetch_wind import _fetch as _fetch_wind  # noqa: E402
from fetch_landing_zones import _query as _query_lz  # noqa: E402
from fetch_landing_zones import _to_feature  # noqa: E402


def _bbox(lat: float, lon: float, radius: float) -> tuple[float, float, float, float]:
    return (
        round(lat - radius, 6),
        round(lat + radius, 6),
        round(lon - radius, 6),
        round(lon + radius, 6),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("lat", type=float, help="Mission area centre latitude")
    parser.add_argument("lon", type=float, help="Mission area centre longitude")
    parser.add_argument(
        "--radius-deg",
        type=float,
        default=0.15,
        metavar="DEG",
        help="Bounding box half-width in degrees (default: 0.15 ≈ 16 km)",
    )
    parser.add_argument(
        "--departure-time",
        default="00:00",
        metavar="HH:MM",
        help="UTC departure time; sets time_s=0 in wind output (default: 00:00)",
    )
    parser.add_argument(
        "--date",
        default=None,
        metavar="YYYY-MM-DD",
        help="Date to fetch wind for (default: today). Past dates use archive API.",
    )
    parser.add_argument(
        "--window-hours",
        type=int,
        default=4,
        metavar="N",
        help="Hourly wind slices from --departure-time (default: 4)",
    )
    parser.add_argument(
        "--step-deg",
        type=float,
        default=0.01,
        metavar="DEG",
        help="Terrain grid resolution in degrees (default: 0.01 ≈ 1 km)",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        metavar="DIR",
        help="Directory for output files (default: current directory)",
    )
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

    if args.step_deg <= 0:
        sys.exit("Error: --step-deg must be positive")
    if args.radius_deg <= 0:
        sys.exit("Error: --radius-deg must be positive")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    lat_min, lat_max, lon_min, lon_max = _bbox(args.lat, args.lon, args.radius_deg)

    step = 1
    total = 3 if _sample_grid is not None else 2

    # --- terrain ---
    terrain_path = out_dir / "terrain.yaml"
    if _sample_grid is None:
        print(
            "Warning: terrain skipped — 'srtm.py' not installed. "
            "Run: uv sync --extra scripts",
            file=sys.stderr,
        )
    else:
        print(
            f"[{step}/{total}] Terrain  lat [{lat_min}, {lat_max}] "
            f"lon [{lon_min}, {lon_max}] step {args.step_deg}° …"
        )
        print("       (SRTM tiles downloaded and cached on first run)")
        lats, lons, rows = _sample_grid(lat_min, lat_max, lon_min, lon_max, args.step_deg)
        terrain_grid = {
            "origin_lat": lats[0],
            "origin_lon": lons[0],
            "step_lat_deg": args.step_deg,
            "step_lon_deg": args.step_deg,
            "elevations_m": rows,
        }
        terrain_path.write_text(yaml.dump(terrain_grid, default_flow_style=None, sort_keys=False))
        print(f"       → {terrain_path} ({len(lats)} rows × {len(lons)} cols)")
        step += 1

    # --- wind ---
    wind_path = out_dir / "wind_grid.yaml"
    print(
        f"[{step}/{total}] Wind     lat={args.lat}, lon={args.lon}, "
        f"date={target_date}, departure={dep_hour:02d}:00 UTC, "
        f"window={args.window_hours}h …"
    )
    wind_data = _fetch_wind(args.lat, args.lon, target_date)
    wind_grid = _build_wind_grid(wind_data, args.lat, args.lon, dep_hour, args.window_hours)
    wind_path.write_text(yaml.dump(wind_grid, default_flow_style=None, sort_keys=False))
    n_times = len(wind_grid["axes"]["time_s"])  # type: ignore[arg-type]
    print(f"       → {wind_path} ({n_times} time steps × {len(_ALTITUDES_M)} altitude bands)")
    step += 1

    # --- landing zones ---
    lz_path = out_dir / "landing_zones.geojson"
    print(
        f"[{step}/{total}] Landing zones  lat [{lat_min}, {lat_max}] "
        f"lon [{lon_min}, {lon_max}] …"
    )
    elements = _query_lz(lat_min, lat_max, lon_min, lon_max)
    features = [f for e in elements if (f := _to_feature(e)) is not None]
    lz_path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=2))
    print(f"       → {lz_path} ({len(features)} features)")

    # --- summary ---
    cwd = Path.cwd()
    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(cwd))
        except ValueError:
            return str(p)

    print()
    print("Done. Add this to your mission YAML:")
    print()
    assets: dict[str, str] = {}
    if _sample_grid is not None:
        assets["terrain_file"] = _rel(terrain_path)
    assets["wind_grid_file"] = _rel(wind_path)
    assets["landing_zones_file"] = _rel(lz_path)
    print("assets:")
    for key, val in assets.items():
        print(f"  {key}: {val}")


if __name__ == "__main__":
    main()
