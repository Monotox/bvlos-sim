# Ticket 055: GeoJSON / KML Route Export

## Goal

Add a `--format geojson` output mode to the `estimate` and `scenario` CLI
commands that emits the mission route as a GeoJSON FeatureCollection. Legs are
coloured by energy margin, landing zones and geofence polygons are included as
separate feature layers. The output opens directly in Google Earth, QGIS,
QGroundControl, and any web map, turning an opaque JSON blob into something a
pilot or operations team can visually inspect in seconds.

## Motivation

The estimator already computes everything needed — per-leg lat/lon positions,
energy consumed, feasibility booleans, geofence polygon references, landing
zone reachability. None of it is visible without reading raw JSON. A GeoJSON
export requires no new computation and no new schemas: it is a pure adapter
on top of existing result types, approximately 80 lines of code, and it
transforms the tool's output from machine-readable to human-visible.

## Output Format

A single GeoJSON FeatureCollection with three named layers expressed as
features with a `layer` property:

### `route` layer — one LineString per leg

```json
{
  "type": "Feature",
  "geometry": { "type": "LineString", "coordinates": [[lon0,lat0,alt0], [lon1,lat1,alt1]] },
  "properties": {
    "layer": "route",
    "phase": "CRUISE",
    "leg_index": 2,
    "path_distance_m": 4521.3,
    "energy_wh": 12.4,
    "energy_margin_pct": 38.2,
    "feasible": true
  }
}
```

`energy_margin_pct` = `(reserve_at_landing_wh − reserve_threshold_wh) / capacity_wh × 100`.
Consumers can style the line by this value (green > 30 %, amber 10–30 %, red < 10 %).

### `landing_zones` layer — one Point per LZ

```json
{
  "type": "Feature",
  "geometry": { "type": "Point", "coordinates": [lon, lat] },
  "properties": {
    "layer": "landing_zones",
    "reachable": true,
    "name": "EHRD"
  }
}
```

Included only when the mission YAML references a landing-zone file.

### `geofences` layer — one Polygon per geofence feature

```json
{
  "type": "Feature",
  "geometry": { "type": "Polygon", "coordinates": [[[...]]] },
  "properties": {
    "layer": "geofences",
    "kind": "forbidden",
    "name": "EHR06A",
    "conflict": false
  }
}
```

`conflict: true` when the route intersects this polygon.
Included only when the mission YAML references a geofence file.

## KML Output

`--format kml` emits the same three layers as KML Placemarks and LineStrings,
with colour-coded styles matching the energy-margin thresholds. KML is the
native format for Google Earth and many regulatory submission portals. The KML
adapter is a thin transform of the same intermediate data structure used by the
GeoJSON adapter.

## CLI Changes

```
bvlos-sim estimate mission.yaml vehicle.yaml --format geojson [--output route.geojson]
bvlos-sim estimate mission.yaml vehicle.yaml --format kml     [--output route.kml]
bvlos-sim scenario scenario.yaml             --format geojson [--output route.geojson]
```

When `--output` is omitted, writes to stdout. Existing `--format json` and
`--format markdown` are unchanged.

## File Plan

New files:

| File | Purpose |
|---|---|
| `adapters/geojson_export.py` | GeoJSON FeatureCollection builder from `MissionEstimate` |
| `adapters/kml_export.py` | KML document builder (thin wrapper over GeoJSON intermediate) |
| `tests/test_geojson_export.py` | Unit tests: feature count, layer names, coordinate order, energy_margin_pct value |

Modified files:

- `adapters/cli.py` — add `geojson` and `kml` to `--format` choices for
  `estimate` and `scenario` commands
- `adapters/__init__.py` — export `build_geojson_export`, `build_kml_export`

## Acceptance Criteria

1. `bvlos-sim estimate examples/missions/pipeline_demo_001.yaml
   examples/vehicles/quadplane_v1.yaml --format geojson` exits 0 and emits
   valid GeoJSON parseable by `json.loads`.
2. The output contains at least one `route` layer feature for every leg in
   the mission.
3. `energy_margin_pct` is present on all `route` features and is a float.
4. `--format kml` exits 0 and emits a document with `<?xml` header and
   `<kml` root element.
5. When a geofence file is referenced, the output contains at least one
   `geofences` layer feature with `conflict` boolean.
6. `--format json` and `--format markdown` are unchanged and all existing
   CLI tests pass.
7. `uv run ruff check` passes.

## Out of Scope

- 3D terrain draping in KML (requires terrain elevation per coordinate).
- Scenario timeline playback as animated KML (`<gx:Tour>`).
- Direct upload to Google My Maps or ArcGIS Online.
