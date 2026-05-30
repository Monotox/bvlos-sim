# Ticket 061 — 3D Geofence with Altitude Floor and Ceiling

## Status: Implemented

## Problem

Geofence feasibility was previously 2D (lon/lat only). A forbidden zone
at 100–400 m AMSL would not block a route that flies through it at 150 m.
UTM corridors, class-D airspace, and restricted areas all have vertical
bounds. Operators need altitude-aware airspace checks for corridor-based BVLOS
planning.

The envelope assumption now states that static geofence feasibility uses 2D
lon/lat segments and additionally applies `floor_m`/`ceiling_m` altitude bands
when zones declare them.

## Acceptance Criteria

1. `GeofenceZone` schema accepts optional `floor_m` and `ceiling_m`
   fields (altitude in metres AMSL).
2. When floor/ceiling are absent the zone behaves as today (full
   vertical extent; backwards compatible).
3. The estimator checks each route leg's altitude range against the
   zone altitude bounds before testing 2D intersection.
4. A forbidden zone with floor/ceiling that does not overlap the leg's
   altitude band is not considered a conflict.
5. A required zone that does not cover the leg altitude band is
   considered a violation.
6. GeoJSON import preserves altitude bounds if present in feature
   properties (`floor_m`, `ceiling_m`).
7. All existing geofence tests pass unchanged.
8. At least 4 new tests cover altitude-bounded forbidden and required
   zones.
9. Golden fixture is updated if the assumption text changes.

## Scope

- `estimator/core/geofence.py` — add `floor_m`, `ceiling_m` to
  `GeofenceZone`
- `estimator/execution/geofence.py` — altitude overlap check before
  2D intersection
- `adapters/assets/geofence_geojson.py` — import floor_m/ceiling_m from
  GeoJSON feature properties
- `docs/USAGE.md` — document the new fields
- `tests/test_geofence.py` — new altitude-bound tests

## Notes

- Leg altitude is already in `LegEstimate.start_alt_amsl_m` /
  `end_alt_amsl_m`; the check just needs to compare the leg altitude
  range [min(start, end), max(start, end)] against [floor, ceiling].
- This is the most-requested gap by any operator doing corridor-based
  BVLOS approval.
