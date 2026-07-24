"""Build population-grid.v2 evidence from an authority-exported raster.

Converts an ESRI ASCII grid (.asc) or a lat,lon,density CSV into the
`population-grid.v2` YAML the `sora` command accepts. Aggregation always
takes the MAXIMUM source value per output cell (`conservative_cell_maximum`
semantics); a target cell with no source coverage aborts the run.

The tool guarantees format and conservative max-pooling only. Authority
approval, conservative source data, and the validity window remain the
operator's responsibility.

Usage:
    python scripts/build_population_grid.py LAT_MIN LAT_MAX LON_MIN LON_MAX \
        --step-deg 0.01 --input population.asc \
        --source "Authority-approved conservative population map" \
        --population-year 2026 --native-resolution-m 100 \
        --authority-assessment-reference POP-2026-014 \
        --valid-from 2026-01-01T00:00:00Z --valid-until 2026-12-31T23:59:59Z \
        --transient-population-assessment-reference EVENTS-2026-008 \
        --assemblies-present false \
        --output population_grid.yaml
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from datetime import datetime
from pathlib import Path

import yaml


def _fail(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(1)


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "yes", "1"}:
        return True
    if lowered in {"false", "no", "0"}:
        return False
    raise argparse.ArgumentTypeError(f"expected true/false, got {value!r}")


def _parse_iso(value: str, flag: str) -> str:
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(f"{flag} must be an ISO 8601 timestamp, got {value!r}")
    return value


def _read_asc(path: Path) -> list[tuple[float, float, float]]:
    """Yield (lat, lon, density) cell centres from an ESRI ASCII grid."""
    lines = path.read_text(encoding="utf-8").splitlines()
    header: dict[str, float] = {}
    row_start = 0
    for index, line in enumerate(lines):
        parts = line.split()
        if len(parts) == 2 and parts[0].lower() in {
            "ncols",
            "nrows",
            "xllcorner",
            "yllcorner",
            "cellsize",
            "nodata_value",
        }:
            header[parts[0].lower()] = float(parts[1])
            row_start = index + 1
        else:
            break
    for key in ("ncols", "nrows", "xllcorner", "yllcorner", "cellsize"):
        if key not in header:
            _fail(f"{path}: missing {key} in ESRI ASCII header")
    ncols = int(header["ncols"])
    nrows = int(header["nrows"])
    cellsize = header["cellsize"]
    nodata = header.get("nodata_value")
    samples: list[tuple[float, float, float]] = []
    rows = lines[row_start:]
    if len(rows) < nrows:
        _fail(f"{path}: expected {nrows} data rows, found {len(rows)}")
    for row_index, line in enumerate(rows[:nrows]):
        values = line.split()
        if len(values) != ncols:
            _fail(
                f"{path}: row {row_index + 1} has {len(values)} values, "
                f"expected {ncols}"
            )
        # ESRI rows run north to south; row 0 is the top of the grid.
        lat = header["yllcorner"] + (nrows - row_index - 0.5) * cellsize
        for col_index, raw in enumerate(values):
            value = float(raw)
            if nodata is not None and value == nodata:
                continue
            lon = header["xllcorner"] + (col_index + 0.5) * cellsize
            samples.append((lat, lon, value))
    return samples


def _read_csv(path: Path) -> list[tuple[float, float, float]]:
    samples: list[tuple[float, float, float]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        for row_number, row in enumerate(reader, start=1):
            if not row or row[0].strip().lower() in {"lat", "latitude"}:
                continue
            if len(row) < 3:
                _fail(f"{path}: row {row_number} needs lat,lon,density")
            try:
                samples.append((float(row[0]), float(row[1]), float(row[2])))
            except ValueError:
                _fail(f"{path}: row {row_number} is not numeric")
    return samples


def _validate_density(value: float, lat: float, lon: float) -> float:
    if not math.isfinite(value) or value < 0.0:
        _fail(f"density at lat={lat}, lon={lon} must be finite and >= 0")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build population-grid.v2 evidence from an ESRI ASCII grid or "
            "lat,lon,density CSV using conservative per-cell maxima."
        )
    )
    parser.add_argument("lat_min", type=float)
    parser.add_argument("lat_max", type=float)
    parser.add_argument("lon_min", type=float)
    parser.add_argument("lon_max", type=float)
    parser.add_argument("--step-deg", type=float, required=True)
    parser.add_argument(
        "--input", type=Path, required=True, help="Source .asc or .csv file"
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--population-year", type=int, required=True)
    parser.add_argument("--native-resolution-m", type=float, required=True)
    parser.add_argument("--authority-assessment-reference", required=True)
    parser.add_argument("--valid-from", required=True)
    parser.add_argument("--valid-until", required=True)
    parser.add_argument("--transient-population-assessment-reference", required=True)
    parser.add_argument(
        "--assemblies-present", type=_parse_bool, required=True, metavar="BOOL"
    )
    parser.add_argument("--output", default="population_grid.yaml", metavar="PATH")
    args = parser.parse_args()

    if args.lat_max <= args.lat_min or args.lon_max <= args.lon_min:
        _fail("lat_max/lon_max must exceed lat_min/lon_min")
    if args.step_deg <= 0:
        _fail("--step-deg must be positive")
    _parse_iso(args.valid_from, "--valid-from")
    _parse_iso(args.valid_until, "--valid-until")

    suffix = args.input.suffix.lower()
    if suffix == ".asc":
        samples = _read_asc(args.input)
    elif suffix == ".csv":
        samples = _read_csv(args.input)
    else:
        _fail(f"unsupported input format {suffix!r}; expected .asc or .csv")

    rows = round((args.lat_max - args.lat_min) / args.step_deg)
    cols = round((args.lon_max - args.lon_min) / args.step_deg)
    if rows < 1 or cols < 1:
        _fail("requested grid has no cells; widen the bounds or shrink --step-deg")

    maxima: list[list[float | None]] = [[None] * cols for _ in range(rows)]
    for lat, lon, value in samples:
        row = int((lat - args.lat_min) / args.step_deg)
        col = int((lon - args.lon_min) / args.step_deg)
        if not (0 <= row < rows and 0 <= col < cols):
            continue
        density = _validate_density(value, lat, lon)
        current = maxima[row][col]
        if current is None or density > current:
            maxima[row][col] = density

    for row_index, row_values in enumerate(maxima):
        for col_index, cell in enumerate(row_values):
            if cell is None:
                cell_lat = args.lat_min + (row_index + 0.5) * args.step_deg
                cell_lon = args.lon_min + (col_index + 0.5) * args.step_deg
                _fail(
                    "no source coverage for output cell centred at "
                    f"lat={cell_lat:.6f}, lon={cell_lon:.6f}; population "
                    "evidence must not contain unassessed cells"
                )

    centre_lat = (args.lat_min + args.lat_max) / 2.0
    effective_resolution_m = args.step_deg * 111_320.0 * max(
        math.cos(math.radians(centre_lat)), 0.1
    )

    document = {
        "schema_version": "population-grid.v2",
        "origin_lat": args.lat_min,
        "origin_lon": args.lon_min,
        "step_lat_deg": args.step_deg,
        "step_lon_deg": args.step_deg,
        "density_ppl_km2": [
            [round(value, 1) for value in row_values] for row_values in maxima
        ],
        "metadata": {
            "source": args.source,
            "population_year": args.population_year,
            "native_resolution_m": args.native_resolution_m,
            "effective_resolution_m": round(effective_resolution_m, 1),
            "value_semantics": "conservative_cell_maximum",
            "authority_assessment_reference": args.authority_assessment_reference,
            "valid_from": args.valid_from,
            "valid_until": args.valid_until,
            "transient_population_assessment_reference": (
                args.transient_population_assessment_reference
            ),
            "operational_footprint_assemblies_present": bool(args.assemblies_present),
        },
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    print(f"Wrote {out} ({rows}x{cols} cells, conservative per-cell maxima)")
    print(
        "Reminder: the format is now correct, but authority approval, "
        "conservative source data, and the validity window remain the "
        "operator's responsibility.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
