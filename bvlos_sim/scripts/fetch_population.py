"""Fetch a diagnostic WorldPop point-sampled population grid.

The script samples WorldPop's public population-density ImageServer at a regular
lat/lon grid. Point sampling can alias native-raster peaks, so this helper does
not produce the conservative ``population-grid.v2`` evidence required by the
SORA command. It remains useful for engineering visualization and diagnostics.
"""

import argparse
import json
import math
import sys
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path

import yaml

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]

try:  # package import
    from ._attribution import WORLDPOP, print_attribution
except ImportError:  # executed as a script
    from _attribution import WORLDPOP, print_attribution  # type: ignore[no-redef]

_WORLDPOP_DENSITY_URL = (
    "https://worldpop.arcgis.com/arcgis/rest/services/"
    "WorldPop_Population_Density_1km/ImageServer/getSamples"
)
_BATCH_SIZE = 500
_MIN_YEAR = 2000
_MAX_YEAR = 2020
_DEFAULT_YEAR = 2020
_DATASET_DOI = "10.5258/SOTON/WP00674"


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


def _chunks(
    values: Sequence[tuple[float, float]], size: int
) -> Iterable[Sequence[tuple[float, float]]]:
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _year_epoch_ms(year: int) -> int:
    if not _MIN_YEAR <= year <= _MAX_YEAR:
        raise ValueError(f"WorldPop year must be between {_MIN_YEAR} and {_MAX_YEAR}")
    instant = datetime(year, 1, 1, tzinfo=timezone.utc)
    return int(instant.timestamp() * 1000)


def _sample_density(
    points: Sequence[tuple[float, float]],
    *,
    year: int = _DEFAULT_YEAR,
    fail_on_missing: bool = False,
) -> list[float]:
    if requests is None:
        raise RuntimeError(
            "'requests' package not installed; run: "
            "pip install 'bvlos-sim[scripts]' or uv sync --extra scripts"
        )
    densities: list[float] = []
    missing_cells = 0
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
                # The ImageServer contains annual slices. Without an explicit
                # instant ArcGIS may return its default (oldest) mosaic.
                "time": str(_year_epoch_ms(year)),
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        samples = payload.get("samples") if isinstance(payload, dict) else None
        if not isinstance(samples, list):
            raise ValueError("WorldPop response missing samples list")
        if len(samples) != len(batch):
            raise ValueError(
                "WorldPop response returned partial coverage for a requested batch "
                f"({len(samples)} samples for {len(batch)} points)"
            )
        for sample in samples:
            value = _sample_value(sample)
            if value is None:
                if fail_on_missing:
                    raise ValueError(
                        "WorldPop returned a no-data sample (water or unmapped "
                        "cell) and --fail-on-missing is set"
                    )
                missing_cells += 1
                value = 0.0
            densities.append(value)
    if missing_cells:
        print(
            f"Warning: {missing_cells} water/no-data cells sampled as density 0.0",
            file=sys.stderr,
        )
    return densities


def _sample_value(sample: object) -> float | None:
    """Return sampled density, or None for a water/no-data cell."""
    if not isinstance(sample, dict):
        raise ValueError("WorldPop sample must be an object")
    raw_value = sample.get("value")
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and raw_value.strip().lower() == "nodata":
        return None
    try:
        value = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("WorldPop sample value must be numeric") from exc
    if not math.isfinite(value) or value < 0.0:
        raise ValueError("WorldPop sample value must be finite and non-negative")
    return value


def _sample_grid(
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    step: float,
    *,
    year: int = _DEFAULT_YEAR,
    fail_on_missing: bool = False,
) -> tuple[list[float], list[float], list[list[float]]]:
    if not -90.0 <= lat_min < lat_max <= 90.0:
        raise ValueError("latitude bounds must lie between -90 and 90")
    if not -180.0 <= lon_min < lon_max <= 180.0:
        raise ValueError("longitude bounds must lie between -180 and 180")
    lats = _axis(lat_min, lat_max, step)
    lons = _axis(lon_min, lon_max, step)
    points = [(lat, lon) for lat in lats for lon in lons]
    densities = _sample_density(points, year=year, fail_on_missing=fail_on_missing)
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
    parser.add_argument(
        "--year",
        type=int,
        default=_DEFAULT_YEAR,
        metavar="YYYY",
        help=(
            f"WorldPop annual density slice ({_MIN_YEAR}-{_MAX_YEAR}; "
            f"default: {_DEFAULT_YEAR})"
        ),
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help=(
            "Abort when WorldPop returns no-data cells (water or unmapped) "
            "instead of sampling them as density 0.0"
        ),
    )
    parser.add_argument("--output", default="population.yaml", metavar="PATH")
    args = parser.parse_args()

    if requests is None:
        sys.exit(
            "Error: 'requests' package not installed. Run: "
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
    if not _MIN_YEAR <= args.year <= _MAX_YEAR:
        sys.exit(f"Error: --year must be between {_MIN_YEAR} and {_MAX_YEAR}")

    print(
        f"Sampling WorldPop population density for "
        f"lat [{args.lat_min}, {args.lat_max}] "
        f"lon [{args.lon_min}, {args.lon_max}] "
        f"step {args.step_deg} deg, year {args.year} ..."
    )

    try:
        lats, lons, rows = _sample_grid(
            args.lat_min,
            args.lat_max,
            args.lon_min,
            args.lon_max,
            args.step_deg,
            year=args.year,
            fail_on_missing=args.fail_on_missing,
        )
    except (RuntimeError, ValueError) as exc:
        sys.exit(f"Error: {exc}")

    grid = {
        "origin_lat": lats[0],
        "origin_lon": lons[0],
        "step_lat_deg": args.step_deg,
        "step_lon_deg": args.step_deg,
        "density_ppl_km2": rows,
        "metadata": {
            "source": _WORLDPOP_DENSITY_URL,
            "dataset_doi": _DATASET_DOI,
            "population_year": args.year,
            "value_semantics": "point_sampled_bilinear_diagnostic",
            "sora_eligible": False,
        },
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        yaml.dump(grid, default_flow_style=None, sort_keys=False),
        encoding="utf-8",
    )
    print(f"Wrote {output} ({len(lats)} rows x {len(lons)} cols)")
    print_attribution(WORLDPOP)


if __name__ == "__main__":
    main()
