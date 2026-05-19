# Ticket 053: Airspace Geofence Fetch Script

## Goal

Complete the real-world data set started in Ticket 052 by adding a
`scripts/fetch_geofences.py` script that produces a `geofence-geojson.v1`
file from real airspace data. This is the only data type missing from the
Ticket 052 real-world example; once it exists the alpine demo will include
actual restricted airspace alongside real terrain, real wind, and real landing
zones.

## Prerequisite: Verify OpenAIP Access Model

OpenAIP (`https://www.openaip.net`) is the best free source of structured
airspace polygons (CTR, TMA, restricted, prohibited zones) in GeoJSON format.
As of early 2024 bulk GeoJSON downloads require a registered free-tier API
key. Before scripting, confirm:

1. Register at `https://www.openaip.net` and obtain a free API key.
2. Verify that `https://api.openaip.net/api/airspaces?bbox=<lon_min,lat_min,lon_max,lat_max>`
   accepts a bounding-box query and returns GeoJSON Polygons with `icaoClass`
   and `type` fields.
3. Confirm the free tier is sufficient for demo-scale queries (~50–200
   polygons per country).

The keyless Overpass fallback has **limited coverage**: OSM airspace data uses
`relation` geometries with complex multi-polygon shapes for most real-world
CTR/TMA/restricted zones. The `way`-only Overpass path described below will
typically return fewer polygons than OpenAIP. Operators needing complete,
authoritative airspace data should use the OpenAIP path.

The Overpass fallback uses `boundary=aeronautical` + `icao:class` tags (more
accurate than `aeroway=restricted_area`, which has very sparse OSM coverage):

```
[out:json];
(
  way["boundary"="aeronautical"]["icao:class"~"^(C|D|R|P)$"](<bbox>);
);
out geom;
```

Note: Real airspace zones are typically mapped as OSM `relation` objects with
complex geometry. This script **skips `relation` types** and prints a warning;
only `way`-based airspace (a small subset) is returned via the Overpass path.

## Script Specification

### `scripts/fetch_geofences.py`

```
uv run python scripts/fetch_geofences.py <lat_min> <lat_max> <lon_min> <lon_max> \
    [--source openaip|overpass] [--api-key KEY] [--output path]
```

**OpenAIP path:**
- Calls `https://api.openaip.net/api/airspaces?bbox=<lon_min,lat_min,lon_max,lat_max>`
  with `Authorization: Bearer <key>` header.
- Maps `icaoClass` / `type` to `kind`:
  - `RESTRICTED`, `PROHIBITED`, `DANGER` → `"forbidden"`
  - `CTR`, `TMA`, `CTA` → `"caution"`
  - All others → omit or `"caution"`.
- Returns a `geofence-geojson.v1` FeatureCollection with Polygon geometry
  and `{ "kind": "forbidden"|"caution", "name": <string> }` properties.

**Overpass fallback path (keyless):**
- Issues the bounding-box Overpass QL query above (`way` type only).
- Prints a warning to stderr: `"Warning: Overpass path returns way-based
  airspace only; relation-based zones (most CTR/TMA) are skipped. Use
  --source openaip for complete coverage."`
- Skips any element whose `type` is `relation` (geometry reconstruction
  is non-trivial and produces unreliable results for complex multi-polygon
  airspace).
- Reconstructs Polygon geometries from `way` node sequences via the `geom`
  output directive (`out geom`).
- Maps `icao:class` tag to `kind`:
  - `R`, `P` → `"forbidden"` (restricted, prohibited)
  - `C`, `D` → `"caution"` (CTR, danger)
  - Others → `"caution"` (conservative default).

## Updated Alpine Demo

- Add `examples/real_world/assets/geofences.geojson` — pre-fetched from
  OpenAIP or Overpass for the Alpine foothills bounding box.
- Wire `geofences.geojson` into `examples/real_world/alpine_mission.yaml`
  under `assets.geofence_file`.
- The alpine area includes Swiss/Austrian TMA and military restricted zones
  that will appear as `caution` and `forbidden` in the feasibility output.

## File Plan

New files:

| File | Purpose |
|---|---|
| `scripts/fetch_geofences.py` | OpenAIP / Overpass → `geofences.geojson` |
| `examples/real_world/assets/geofences.geojson` | Pre-fetched airspace data for alpine demo |

Modified files:

- `examples/real_world/alpine_mission.yaml` — add `geofence_file` asset reference
- `examples/real_world/README.md` — add fetch command for geofences, note API key requirement

## Acceptance Criteria

1. `uv run python scripts/fetch_geofences.py 46.9 47.1 7.9 8.1 --source openaip
   --api-key $OPENAIP_KEY` produces a valid `geofence-geojson.v1`
   FeatureCollection with at least one polygon.
2. `uv run python scripts/fetch_geofences.py 46.9 47.1 7.9 8.1 --source overpass`
   works with no API key and produces valid output (may return fewer polygons).
3. `uv run bvlos-sim estimate examples/real_world/alpine_mission.yaml
   examples/real_world/quadplane_v1.yaml` includes geofence check results in
   output when `geofences.geojson` is referenced.
4. Pre-fetched `geofences.geojson` is committed so the demo works offline.
5. All existing tests continue to pass.
6. `uv run ruff check` passes.

## Dependency on Ticket 052

This ticket is a direct follow-on to Ticket 052. The `scripts/` directory,
`examples/real_world/` structure, and `alpine_mission.yaml` are all created
there; this ticket extends them.

## Out of Scope

- Fetching live NOTAMs or temporary restrictions (dynamic airspace).
- Altitude-bounded geofence filtering (e.g. only restrictions below 1000 m
  AGL) — deferred to a later schema extension.
- FAA UAS Facility Map integration — a separate follow-on for US operators.
