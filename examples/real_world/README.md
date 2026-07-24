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
  examples/real_world/quadplane_v1.yaml \
  --engineering-only
```

This is an engineering data demo, not an operational GO case. The mission omits
some mandatory readiness evidence, so the default command still writes its
result but exits `10`; `--engineering-only` makes computational feasibility the
shell-success criterion.

The output includes `terrain_provider_id: uniform_grid` and
`wind_provider_id: spatiotemporal_grid` in result metadata, confirming which
real terrain and spatiotemporal wind are active. Terrain elevations in this
grid range from 393 to 2025 m (Pilatus area), well above the flat polder used
in the pipeline demo, and the checklist reports a non-zero worst wind drawn
from the forecast bands the route actually flies through.

## What a failing mission looks like

This variant uses a smaller battery and fails the reserve check.

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_infeasible.yaml \
  examples/real_world/quadplane_small_battery.yaml \
  --format summary \
  --engineering-only
```

Output:

```text
INFEASIBLE   reserve −179.7 %   flight 7m 55s   RTH infeasible   [INSUFFICIENT_ENERGY]
```

The mission consumes 101.94677145 Wh, leaving -16.94677145 Wh at landing with
the 85 Wh battery. The required 25 % reserve threshold is 21.25 Wh, and the
hard RTH reserve check also fails. Running `size-battery` with
`quadplane_small_battery_sizing.yaml` reports a minimum 183.2 Wh for the
current route and RTH model; reducing route demand is the alternative.

## Re-fetch the assets yourself

### One command (recommended)

`fetch_all.py` fetches terrain, wind, and landing zones for a centre point
in one go and prints the `assets:` block to paste into your mission YAML.
Fetch geofences separately with `fetch_geofences.py` (see the "Fetch
geofences" section below).

```bash
uv sync --extra scripts   # installs srtm.py (once)
uv run python bvlos_sim/scripts/fetch_all.py 47.05 8.30 \
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

uv run python bvlos_sim/scripts/fetch_terrain.py 46.9 47.2 8.15 8.45 0.01 \
  --void-policy interpolate \
  --output terrain.yaml

uv run python bvlos_sim/scripts/fetch_wind.py 47.05 8.3 \
  --departure-time 14:00 --date 2025-06-15 --window-hours 4 \
  --output wind_grid.yaml

uv run python bvlos_sim/scripts/fetch_landing_zones.py 46.9 47.2 8.1 8.4 \
  --output landing_zones.geojson
```

All scripts write files that wire directly into the `assets:` section of any
mission YAML without manual editing.

### Fetch geofences

OpenAIP is the primary source for complete airspace coverage and requires a
free account at https://www.openaip.net.

```bash
uv run python bvlos_sim/scripts/fetch_geofences.py 46.9 47.2 8.1 8.4 \
  --source openaip \
  --api-key $OPENAIP_KEY \
  --output geofences.geojson
```

Overpass is the keyless fallback. It returns way-based airspace only;
relation-based zones, including most CTR/TMA areas, are skipped. Use OpenAIP
when complete coverage matters. When a fetch yields zero features the script
refuses to write the file and exits with an error; pass `--allow-empty` to
write an empty `geofences.geojson` for an area that genuinely has no airspace.

```bash
uv run python bvlos_sim/scripts/fetch_geofences.py 46.9 47.2 8.1 8.4 \
  --source overpass \
  --output geofences.geojson
```

The demo ships no geofence file: the Overpass fallback returned zero zones
for this area (its CTR/TMA coverage is relation-based), and an empty airspace
file would render a meaningless green "0 conflicts across 0 zone(s)" check.
The checklist therefore reports geofence evidence as missing — fetch real
coverage via OpenAIP before flying here.

## Area and data sources

| Asset | Source | Licence | Coverage |
|---|---|---|---|
| `terrain.yaml` | SRTM via `srtm.py` | Public domain | lat 46.9–47.2, lon 8.15–8.45, 31×31 grid |
| `wind_grid.yaml` | Open-Meteo historical forecast (2025-06-15 14:00 UTC) | CC BY 4.0 | 4 altitude bands (AMSL), 4 hourly slices |
| `landing_zones.geojson` | OpenStreetMap via Overpass | ODbL 1.0 | 13 helipads/aerodromes/runways |

These three are **not** covered by this repository's MIT licence. Redistributing
them, or data you fetch yourself, carries the attribution and share-alike
obligations in [NOTICE.md](../../NOTICE.md).

The area covers the Lucerne basin and surrounding pre-Alps, including the
Pilatus massif (peak elevation 2025 m in the SRTM grid). SRTM has voids over
the lakes, so the grid is fetched with `--void-policy interpolate`; the wind
grid's `altitude_m` axis is metres AMSL, matching the ~550 m the route flies.
