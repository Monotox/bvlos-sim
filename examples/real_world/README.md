# Real-World Data Demo

This example runs a BVLOS estimate over the Lucerne/Zug area of Switzerland
using real terrain from SRTM, a real wind forecast from Open-Meteo, and real
aeroway landing zones and airspace geofences from OpenStreetMap via Overpass.

Pre-fetched assets are committed to `assets/` so the estimate runs offline
with no network calls.

## Run the estimate (offline, no setup needed)

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml
```

The output includes `terrain_provider_id: uniform_grid` and
`wind_provider_id: spatiotemporal_grid` in result metadata, confirming that
real terrain and spatiotemporal wind are active. Terrain elevations in this
grid range from 0 to 1943 m (Pilatus area), well above the flat polder used
in the pipeline demo.

## Re-fetch the assets yourself

### One command (recommended)

`fetch_all.py` fetches terrain, wind, and landing zones for a centre point
in one go and prints the `assets:` block to paste into your mission YAML.
Fetch geofences separately with `fetch_geofences.py` (see the "Fetch
geofences" section below).

```bash
uv sync --extra scripts   # installs srtm.py (once)
uv run python scripts/fetch_all.py 47.05 8.30 \
  --departure-time 14:00 --date 2025-06-15 \
  --output-dir examples/real_world/assets
```

Output:

```
[1/3] Terrain  lat [46.9, 47.2] lon [8.15, 8.45] step 0.01° …
      → terrain.yaml (31 rows × 31 cols)
[2/3] Wind     lat=47.05, lon=8.3, date=2025-06-15, departure=14:00 UTC, window=4h …
      → wind_grid.yaml (4 time steps × 4 altitude bands)
[3/3] Landing zones  lat [46.9, 47.2] lon [8.15, 8.45] …
      → landing_zones.geojson (13 features)

Done. Add this to your mission YAML:

assets:
  terrain_file: examples/real_world/assets/terrain.yaml
  wind_grid_file: examples/real_world/assets/wind_grid.yaml
  landing_zones_file: examples/real_world/assets/landing_zones.geojson
```

### Individual scripts

Run the individual scripts if you need finer control (different bounding box
for terrain vs. landing zones, specific step size, etc.).

```bash
uv sync --extra scripts   # installs srtm.py (once)

uv run python scripts/fetch_terrain.py 46.9 47.2 8.1 8.4 0.01 \
  --output terrain.yaml

uv run python scripts/fetch_wind.py 47.05 8.3 \
  --departure-time 14:00 --date 2025-06-15 --window-hours 4 \
  --output wind_grid.yaml

uv run python scripts/fetch_landing_zones.py 46.9 47.2 8.1 8.4 \
  --output landing_zones.geojson
```

All scripts write files that wire directly into the `assets:` section of any
mission YAML without manual editing.

### Fetch geofences

OpenAIP is the primary source for complete airspace coverage and requires a
free account at https://www.openaip.net.

```bash
uv run python scripts/fetch_geofences.py 46.9 47.2 8.1 8.4 \
  --source openaip \
  --api-key $OPENAIP_KEY \
  --output geofences.geojson
```

Overpass is the keyless fallback. It returns way-based airspace only;
relation-based zones, including most CTR/TMA areas, are skipped. Use OpenAIP
when complete coverage matters.

```bash
uv run python scripts/fetch_geofences.py 46.9 47.2 8.1 8.4 \
  --source overpass \
  --output geofences.geojson
```

The committed `geofences.geojson` was produced via the Overpass fallback.

## Area and data sources

| Asset | Source | Coverage |
|---|---|---|
| `terrain.yaml` | SRTM via `srtm.py` | lat 46.9–47.2, lon 8.1–8.4, 31×31 grid |
| `wind_grid.yaml` | Open-Meteo archive (2025-06-15 14:00 UTC) | 4 altitude bands, 4 hourly slices |
| `landing_zones.geojson` | OpenStreetMap via Overpass | 12 helipads/aerodromes/runways |
| `geofences.geojson` | OpenStreetMap via Overpass | way-based aeronautical boundaries |

The area covers the Lucerne basin and surrounding pre-Alps, including the
Pilatus massif (peak elevation 1943 m in the SRTM grid). Wind at 10 m vs.
180 m altitude diverges meaningfully in the forecast, exercising quadrilinear
interpolation in `SpatiotemporalWindProvider`.
