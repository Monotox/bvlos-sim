"""Fetch a WorldPop density grid and write a population-grid.v1 YAML file.

The script samples WorldPop's public population-density ImageServer at a regular
lat/lon grid. It is an optional data-prep helper; core estimation remains
offline and deterministic.
"""

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

import yaml

try:
    import requests
except ImportError:
    sys.exit("Error: 'requests' package not installed. Run: uv sync")

_WORLDPOP_DENSITY_URL = (
    "https://worldpop.arcgis.com/arcgis/rest/services/"
    "WorldPop_Population_Density_1km/ImageServer/getSamples"
)
_BATCH_SIZE = 500


def _axis(start: float, stop: float, step: float) -> list[float]:
    count = round((stop - start) / step) + 1
    return [round(start + i * step, 8) for i in range(count)]


def _chunks(values: Sequence[tuple[float, float]], size: int) -> Iterable[Sequence[tuple[float, float]]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _sample_density(points: Sequence[tuple[float, float]]) -> list[float]:
    densities: list[float] = []
    for batch in _chunks(points, _BATCH_SIZE):
        geometry = {
            "points": [[lon, lat] for lat, lon in batch],
            "spatialReference": {"wkid": 4326},
        }
        response = requests.get(
            _WORLDPOP_DENSITY_URL,
            params={
                "f": "json",
                "geometryType": "esriGeometryMultipoint",
                "geometry": json.dumps(geometry),
                "returnFirstValueOnly": "true",
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        samples = payload.get("samples") if isinstance(payload, dict) else None
        if not isinstance(samples, list):
            raise ValueError("WorldPop response missing samples list")
        densities.extend(_sample_value(sample) for sample in samples)
    return densities


def _sample_value(sample: object) -> float:
    if not isinstance(sample, dict):
        return 0.0
    value = sample.get("value")
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def _sample_grid(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    step: float,
) -> tuple[list[float], list[float], list[list[float]]]:
    lats = _axis(lat_min, lat_max, step)
    lons = _axis(lon_min, lon_max, step)
    points = [(lat, lon) for lat in lats for lon in lons]
    densities = _sample_density(points)
    if len(densities) != len(points):
        raise ValueError("WorldPop response size did not match requested grid")

    rows: list[list[float]] = []
    for row_index in range(len(lats)):
        start = row_index * len(lons)
        row = densities[start : start + len(lons)]
        rows.append([round(value, 3) for value in row])
    return lats, lons, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("lat_min", type=float)
    parser.add_argument("lat_max", type=float)
    parser.add_argument("lon_min", type=float)
    parser.add_argument("lon_max", type=float)
    parser.add_argument("step_deg", type=float, help="Grid step in degrees")
    parser.add_argument("--output", default="population.yaml", metavar="PATH")
    args = parser.parse_args()

    if args.lat_min >= args.lat_max:
        sys.exit("Error: lat_min must be less than lat_max")
    if args.lon_min >= args.lon_max:
        sys.exit("Error: lon_min must be less than lon_max")
    if args.step_deg <= 0:
        sys.exit("Error: step_deg must be positive")

    print(
        f"Sampling WorldPop population density for "
        f"lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] "
        f"step {args.step_deg} deg ..."
    )

    lats, lons, rows = _sample_grid(
        args.lat_min, args.lat_max, args.lon_min, args.lon_max, args.step_deg
    )

    grid = {
        "origin_lat": lats[0],
        "origin_lon": lons[0],
        "step_lat_deg": args.step_deg,
        "step_lon_deg": args.step_deg,
        "density_ppl_km2": rows,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.dump(grid, default_flow_style=None, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {output} ({len(lats)} rows x {len(lons)} cols)")


if __name__ == "__main__":
    main()
