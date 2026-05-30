# Ticket 053: Airspace Geofence Fetch Script

Status: implemented.

## Goal

Complete the real-world data set started in Ticket 052 by adding
`scripts/fetch_geofences.py`. The script writes a standard GeoJSON
FeatureCollection accepted by `adapters/assets/geofence_geojson.py`, with
`Polygon` or `MultiPolygon` features and `kind` / `name` properties for each
zone.

The Alpine demo now includes a committed `geofences.geojson` asset alongside
real terrain, real wind, and real landing zones.

## Sources

OpenAIP (`https://www.openaip.net`) is the primary source for structured
airspace polygons such as CTR, TMA, restricted, prohibited, and danger zones.
It requires a registered free-tier API key.

The keyless Overpass fallback has limited coverage. OSM airspace data often
uses `relation` geometries with complex multi-polygon shapes for real-world
CTR/TMA/restricted zones. The implemented Overpass path intentionally reads
way-based airspace only and prints a warning so operators know to prefer
OpenAIP when complete coverage matters.

The Overpass fallback uses `boundary=aeronautical` + `icao:class` tags:

```text
[out:json];
(
  way["boundary"="aeronautical"]["icao:class"~"^(C|D|R|P)$"](<bbox>);
);
out geom;
```

## Implemented Script

```bash
uv run python scripts/fetch_geofences.py <lat_min> <lat_max> <lon_min> <lon_max> \
  [--source openaip|overpass] [--api-key KEY] [--output PATH]
```

**OpenAIP path:**

- Calls `https://api.openaip.net/api/airspaces` with
  `bbox=<lon_min>,<lat_min>,<lon_max>,<lat_max>`.
- Sends the API key as `x-openaip-api-key: <key>`.
- Requires `--api-key` before any network call when `--source openaip`.
- Maps `icaoClass` / `type` to `kind`:
  - `RESTRICTED`, `PROHIBITED`, `DANGER` -> `"forbidden"`
  - `CTR`, `TMA`, `CTA`, and all others -> `"caution"`
- Skips non-Polygon and non-MultiPolygon features.

**Overpass fallback path:**

- Posts the bounding-box Overpass QL query above.
- Prints this warning to stderr:
  `"Warning: Overpass path returns way-based airspace only; relation-based zones
  (most CTR/TMA) are skipped. Use --source openaip for complete coverage."`
- Converts way geometry nodes into closed GeoJSON Polygon rings.
- Maps `icao:class` to `kind`:
  - `R`, `P` -> `"forbidden"`
  - `C`, `D`, and all others -> `"caution"`
- Skips ways with fewer than three geometry nodes.

## Updated Alpine Demo

- `examples/real_world/assets/geofences.geojson` is committed so the demo runs
  offline. The committed asset was produced through the Overpass fallback and
  may be an empty FeatureCollection when the bounded area has no way-based
  aeronautical boundaries.
- `examples/real_world/alpine_mission.yaml` references the asset under
  `assets.geofences_file`.
- `examples/real_world/README.md` documents both the OpenAIP primary command
  and the Overpass fallback command.

## File Plan

New files:

| File | Purpose |
|---|---|
| `scripts/fetch_geofences.py` | OpenAIP / Overpass -> `geofences.geojson` |
| `examples/real_world/assets/geofences.geojson` | Pre-fetched static airspace data for the Alpine demo |

Modified files:

- `examples/real_world/alpine_mission.yaml` -- add `geofences_file` asset reference.
- `examples/real_world/README.md` -- document geofence fetch commands and API key requirement.

## Acceptance Criteria

1. `uv run python scripts/fetch_geofences.py 46.9 47.2 8.1 8.4 --source overpass`
   exits successfully and writes a valid GeoJSON FeatureCollection. It may be
   empty because the Overpass path is way-based.
2. `uv run python scripts/fetch_geofences.py 46.9 47.2 8.1 8.4 --source openaip`
   exits with a clear `--api-key` error before making any network call.
3. `uv run bvlos-sim estimate examples/real_world/alpine_mission.yaml
   examples/real_world/quadplane_v1.yaml` reads `geofences.geojson` and includes
   geofence check results.
4. Pre-fetched `geofences.geojson` is committed so the demo works offline.
5. All existing tests continue to pass.
6. `uv run ruff check .` passes.

## Dependency on Ticket 052

This ticket is a direct follow-on to Ticket 052. The `scripts/` directory,
`examples/real_world/` structure, and `alpine_mission.yaml` are created there;
this ticket extends them with static airspace geofences.

## Out of Scope

- Fetching live NOTAMs or temporary restrictions (dynamic airspace).
- Altitude-bounded geofence filtering, such as only restrictions below
  1000 m AGL.
- FAA UAS Facility Map integration.
