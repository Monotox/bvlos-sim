# Ticket 058: NOTAM and Live Airspace Integration

## Goal

Add a `scripts/fetch_notams.py` script that queries live NOTAM and temporary
flight restriction (TFR) data for a given bounding box and time window, then
writes a `geofence-geojson.v1` file containing only the active restrictions.
When wired into a mission YAML, the geofence feasibility check will reflect
actual airspace on the planned flight date — not just permanent airspace
structure from static OpenAIP/Overpass data (Tickets 052–053).

## Motivation

Static geofences (CTR, TMA, restricted areas) represent permanent airspace
structure. Real pre-flight checks also require:
- **NOTAMs**: temporary restrictions for events, military exercises, VIP
  movement, drone-specific hazards
- **TFRs** (FAA): pop-up security or emergency restrictions
- **UAS GEO zones** (EASA): dynamic flight-restriction zones active at a
  specific time

Without this, a green feasibility result from bvlos-sim may be invalidated by
a NOTAM issued 48 hours before flight — a common operational failure mode.

## Sources

### FAA (US): B4UFly Preflight API

```
GET https://uat.faa.gov/uas/resources/b4ufly/preflight/
    ?latitude=<lat>&longitude=<lon>&radius=<nm>
```

Returns JSON with `features` array of GeoJSON geometries for active
restrictions. No API key required for the public endpoint. Covers TFRs, NSUFRs,
and UAS facility map restrictions. Geometry varies: Point (radius), Polygon,
or LineString buffer.

### EUROCONTROL SWIM / NOTAM Service

EUROCONTROL's `https://notaminfo.com` and the official SWIM `AIXM 5.1`
NOTAM feed expose active European NOTAMs. The `notaminfo.com` API (free,
registration required) returns JSON-wrapped NOTAM text with decoded Q-line
geometry fields (`lat/lon/radius` for circular NOTAMs, polygon coordinates
for area NOTAMs).

Parsing NOTAM geometry is the main complexity of this ticket: Q-line radii
(circular buffer around a VOR/fix), explicit polygon coordinates, and
referenced airspace boundaries all require different handling.

### Fallback: ICAO NOTAMSearch API

`https://www.notams.faa.gov/dinsQueryWeb/` provides NOTAM text for any
ICAO area code. Geometry must be parsed from NOTAM text (fragile; last resort).

## Script Specification

### `scripts/fetch_notams.py`

```
uv run python scripts/fetch_notams.py <lat_min> <lat_max> <lon_min> <lon_max> \
    --departure-time "YYYY-MM-DD HH:MM" \
    --duration-hours N \
    [--region faa|eurocontrol] \
    [--api-key KEY] \
    [--output path]
```

- Fetches active restrictions overlapping the bounding box during the time
  window `[departure_time, departure_time + duration_hours]`.
- Transforms each restriction to a GeoJSON Feature:
  - **Circular NOTAM**: Point geometry with `radius_m` property (note:
    `geofence-geojson.v1` uses Polygons; approximate circle as 32-point
    polygon)
  - **Area NOTAM / TFR polygon**: Polygon geometry directly
  - **Altitude-bounded restriction**: include `alt_lower_m` and `alt_upper_m`
    as properties (bvlos-sim geofence schema ignores these for now; they are
    preserved for future altitude-bounded geofence support)
- Assigns `"kind": "forbidden"` to prohibited/restricted features,
  `"kind": "caution"` to advisory features.
- Merges with existing static geofence file if `--merge path/to/static.geojson`
  is provided, deduplicating by feature name.
- Writes a single `geofence-geojson.v1` FeatureCollection.

## Known Complexity

NOTAM geometry parsing is messy:
- Q-line `W/` field specifies radius in nautical miles around a lat/lon or
  ICAO fix — requires ICAO fix database lookup or online resolution.
- Some NOTAMs reference named airspace volumes without explicit coordinates —
  require cross-reference with static airspace data.
- Altitude bounds in NOTAM text use non-standard formats (FL, AGL, AMSL,
  "SFC").

The MVP handles only:
1. Explicit polygon coordinates in the response (FAA B4UFly Polygon features)
2. Circular restrictions with explicit lat/lon centre and radius (Q-line with
   known fix)

NOTAMs requiring fix database lookup or free-text parsing are logged as
warnings and skipped rather than silently dropped.

## File Plan

New files:

| File | Purpose |
|---|---|
| `scripts/fetch_notams.py` | NOTAM / TFR fetch → `geofence-geojson.v1` |
| `tests/test_fetch_notams.py` | Unit tests with mocked API responses for polygon and circular NOTAM cases |

Modified files:

- `examples/real_world/README.md` — add optional NOTAM fetch step before
  estimate command

## Acceptance Criteria

1. `uv run python scripts/fetch_notams.py 46.9 47.1 7.9 8.1
   --departure-time "2025-06-15 14:00" --duration-hours 4 --region faa`
   exits 0 and produces valid GeoJSON (even if empty FeatureCollection when
   no NOTAMs active).
2. A mocked polygon TFR response produces a GeoJSON Polygon feature with
   `"kind": "forbidden"`.
3. A mocked circular NOTAM produces a 32-point approximated Polygon.
4. NOTAMs with unresolvable geometry produce a warning log line and are
   omitted from output (not a fatal error).
5. `--merge static.geojson` merges features from both files into a single
   FeatureCollection.
6. All existing tests continue to pass.
7. `uv run ruff check` passes.

## Relationship to Other Tickets

- **Ticket 052**: provides `fetch_terrain.py`, `fetch_wind.py`,
  `fetch_landing_zones.py` — same `scripts/` directory and usage pattern.
- **Ticket 053**: provides `fetch_geofences.py` for static airspace — NOTAM
  output is intended to be merged with static output via `--merge`.

## Out of Scope

- Parsing free-text NOTAM body for geometry — too fragile for MVP.
- Real-time websocket NOTAM feeds — polling on demand is sufficient.
- EASA U-Space Dynamic Geofence API — deferred to Ticket 070.
- Altitude-bounded geofence enforcement in the feasibility check — the
  `alt_lower_m` / `alt_upper_m` properties are preserved in output but not
  yet consumed by the estimator.
