# Ticket 052: Real-World Data Fetch Scripts

## Goal

Replace the synthetic demo data (flat 10 m Dutch polder, made-up no-fly box,
single invented helipad) with three small CLI scripts that pull real terrain,
real wind forecasts, and real landing zones from free public APIs. The scripts
produce files that drop directly into the `assets:` section of any mission
YAML. A first-time user can go from clone to a geographically realistic
estimate in under five minutes.

## Motivation

The current demo runs over a flat, featureless area where terrain-referenced
altitude is invisible and wind is constant. A new user cannot see what the
tool does differently from a spreadsheet. Swapping the demo area to somewhere
with real topography (Alpine foothills, Scottish Highlands, US Rockies) and
real forecast wind makes every existing feature — terrain-referenced altitude,
spatiotemporal wind correction, landing-zone reachability — immediately legible
in the output.

## Scope

Three scripts in a new `scripts/` directory, each under ~60 lines, depending
only on `requests` (already a transitive dependency) and optionally
`elevation` (SRTM local lookup):

| Script | Source API | Output |
|---|---|---|
| `scripts/fetch_wind.py` | Open-Meteo forecast | `wind_grid.yaml` for `SpatiotemporalWindProvider` |
| `scripts/fetch_terrain.py` | `elevation` package (SRTM) | `terrain.yaml` for `GridTerrainProvider` |
| `scripts/fetch_landing_zones.py` | Overpass API | `landing_zones.geojson` for `landing-zone-geojson.v1` |

One updated example mission wired to all three outputs, located in a
mountainous area where terrain-referenced altitude produces non-trivial
results.

## Script Specifications

### `scripts/fetch_wind.py`

```
uv run python scripts/fetch_wind.py <lat> <lon> [--departure-time HH:MM] [--date YYYY-MM-DD] [--window-hours N] [--output path]
```

- Calls `https://api.open-meteo.com/v1/forecast` (or `/v1/archive` when
  `--date` is in the past) with `hourly=wind_speed_10m,wind_direction_10m,
  wind_speed_80m,wind_direction_80m,wind_speed_120m,wind_direction_120m,
  wind_speed_180m,wind_direction_180m&wind_speed_unit=ms`.
- Returns 4 altitude bands (10 m, 80 m, 120 m, 180 m) × 24 hourly time steps
  for the requested date.
- `--departure-time HH:MM` (default `00:00`) selects the starting forecast
  hour and maps it to `time_s: [0, 3600, ...]` in the output YAML so that
  `time_s=0` corresponds to the planned takeoff time. Without this parameter
  the wind data is temporally wrong for any flight that does not depart at
  midnight.
- `--window-hours N` (default `4`) limits the output to N hourly slices
  starting from `--departure-time`, covering a typical mission duration.
- Decomposes speed + direction into east/north components:
  `wind_east = −speed · sin(dir_rad)`, `wind_north = −speed · cos(dir_rad)`
  (meteorological convention: direction is *from*).
- Writes a `SpatiotemporalWindProvider`-compatible YAML with
  `lat_min/lat_max/lon_min/lon_max` set to the queried point ± 0.01°,
  `altitudes_m: [10, 80, 120, 180]`, and `times_s` indexed from 0.
- No API key. No registration. Free forever.

### `scripts/fetch_terrain.py`

```
uv run python scripts/fetch_terrain.py <lat_min> <lat_max> <lon_min> <lon_max> <step_deg> [--output path]
```

- Uses the `elevation` PyPI package, which downloads and caches SRTM tiles
  locally on first run (no network call after that). Falls back to the
  Open-Elevation REST API (`https://api.open-elevation.com/api/v1/lookup`
  via POST) only when `elevation` is not installed.
- Writes a `GridTerrainProvider`-compatible YAML with
  `lat_min, lat_max, lon_min, lon_max, step_deg` and a 2-D `elevations_m`
  array in row-major order (north-to-south, west-to-east).
- The `elevation` package is added to `pyproject.toml` as an optional
  dependency under `[project.optional-dependencies] scripts`.

### `scripts/fetch_landing_zones.py`

```
uv run python scripts/fetch_landing_zones.py <lat_min> <lat_max> <lon_min> <lon_max> [--output path]
```

- Queries the Overpass API (`https://overpass-api.de/api/interpreter`) with:
  ```
  [out:json];
  (
    node["aeroway"="helipad"](<bbox>);
    node["aeroway"="aerodrome"](<bbox>);
    way["aeroway"="runway"](<bbox>);
  );
  out center;
  ```
- Transforms results to a `landing-zone-geojson.v1` FeatureCollection with
  Point geometry and properties `{ "surface": <from OSM tag or "unknown"> }`.
- No API key. No registration. Free forever.

## Updated Demo Example

New directory: `examples/real_world/`

| File | Contents |
|---|---|
| `examples/real_world/README.md` | Three fetch commands + one estimate command |
| `examples/real_world/alpine_mission.yaml` | Mission over Alpine foothills (~lat 47, lon 8) referencing real terrain and wind |
| `examples/real_world/quadplane_v1.yaml` | Symlink or copy of existing vehicle file |

The alpine area is chosen because:
- SRTM elevation varies ~500–2000 m across a small bounding box, making
  terrain-referenced altitude produce visibly non-trivial AGL corrections.
- Wind at 10 m vs. 180 m diverges meaningfully, exercising the altitude
  interpolation in `SpatiotemporalWindProvider`.
- There are real helipads and aerodromes within a 20 km radius to exercise
  landing-zone reachability.

Pre-fetched static copies of the terrain YAML and wind YAML are committed to
`examples/real_world/assets/` so the example works offline without running
the fetch scripts.

## File Plan

New files:

| File | Purpose |
|---|---|
| `scripts/fetch_wind.py` | Open-Meteo → `wind_grid.yaml` |
| `scripts/fetch_terrain.py` | SRTM / Open-Elevation → `terrain.yaml` |
| `scripts/fetch_landing_zones.py` | Overpass API → `landing_zones.geojson` |
| `examples/real_world/README.md` | Step-by-step real-data demo |
| `examples/real_world/alpine_mission.yaml` | Alpine demo mission |
| `examples/real_world/assets/terrain.yaml` | Pre-fetched SRTM terrain grid |
| `examples/real_world/assets/wind_grid.yaml` | Pre-fetched Open-Meteo forecast snapshot |
| `examples/real_world/assets/landing_zones.geojson` | Pre-fetched Overpass LZ data |

Modified files:

- `pyproject.toml` — add `elevation` as optional dep under `[scripts]` extra
- `README.md` — add "Real-world data" section pointing to `examples/real_world/`

## Integration Requirements

- Scripts must be runnable with `uv run python scripts/fetch_*.py` with no
  additional setup beyond `uv sync --extra scripts` for the `elevation` dep.
- Output files must be valid inputs to existing `assets:` fields in mission
  YAML without any manual editing.
- Pre-fetched asset files must be committed so that `uv run bvlos-sim estimate
  examples/real_world/alpine_mission.yaml ...` works offline.
- Scripts must not be imported by any estimator or test code — they are
  developer utilities only.

## Acceptance Criteria

1. `uv run python scripts/fetch_wind.py 47.0 8.0 --departure-time 14:00 --date 2025-06-15`
   produces a valid `SpatiotemporalWindProvider` YAML where `times_s[0] == 0`
   corresponds to 14:00 UTC on the given date.
1a. `uv run python scripts/fetch_wind.py 47.0 8.0` (no departure-time) still
    produces valid output defaulting to the 00:00 window.
2. `uv run python scripts/fetch_terrain.py 46.9 47.1 7.9 8.1 0.01` produces a
   valid `GridTerrainProvider` YAML; elevations are non-trivially non-zero.
3. `uv run python scripts/fetch_landing_zones.py 46.9 47.1 7.9 8.1` produces a
   valid `landing-zone-geojson.v1` GeoJSON FeatureCollection.
4. `uv run bvlos-sim estimate examples/real_world/alpine_mission.yaml
   examples/real_world/quadplane_v1.yaml` exits 0 using only the committed
   pre-fetched assets (no network required).
5. The alpine mission output shows at least one leg with
   `terrain_elevation_m > 100` confirming terrain-referenced altitude is
   active.
6. All existing tests continue to pass.
7. `uv run ruff check` passes.

## Out of Scope

- Geofence sourcing: OpenAIP free-tier access requires verification before
  scripting; deferred to a follow-on ticket once the API access model is
  confirmed.
- QGC `.plan` importer: deferred to Ticket 060.
- Flight log ingestion: deferred to Tickets 080–082.
- Any network calls inside the main estimator or test suite.
