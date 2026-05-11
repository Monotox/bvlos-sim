# Ticket 011: Static Geofence Feasibility

Status: implemented.

## Goal

Add deterministic route-vs-zone validation.

## Current Gap

This ticket is complete. Static GeoJSON geofence feasibility is available from
the estimator, scenario runner, and CLI paths.

## Scope

- Add core geofence model independent of GeoJSON.
- Add GeoJSON importer adapter.
- Add route segment vs polygon checks.
- Handle explicitly:
  - boundary touching
  - invalid polygons
  - coordinate order
  - holes, if supported
  - multipolygons, if supported
- Add diagnostics:
  - `route_enters_forbidden_zone`
  - `route_exits_required_zone`
  - `invalid_geometry`
  - `unsupported_geometry_type`

## Acceptance Criteria

- A supported mission route can be deterministically checked against supported geofence geometry.
- Unsupported geometry is rejected explicitly.

## Implementation Notes

- Core geofence models are independent of GeoJSON and use lat/lon domain coordinates.
- The GeoJSON adapter supports `Polygon` and `MultiPolygon`, including holes, and reads coordinates in `[lon, lat]` order.
- Static feasibility is evaluated after kinematic route expansion and deterministic energy feasibility.
- Forbidden zones use intersection semantics, so boundary touching is a conflict.
- Required zones are evaluated as a union and use cover semantics, so route contact with the required-zone boundary is allowed.
- JSON envelope versions were bumped to `estimator-envelope.v3` and `mission.v3` because `assets.geofences_file` is now operative and the result shape includes `result.geofence`.

## Integrated Surfaces

- Mission YAML references geofence GeoJSON through `assets.geofences_file`.
- Geofence examples live under `data/geofences/` and are used by mission
  examples.
- `estimate` and `scenario` load geofence assets from the mission file
  directory and pass domain `GeofenceZone` objects into the core engine.
- JSON and Markdown reports include geofence feasibility, checked-zone counts,
  checked-leg counts, and conflicts.
- Scenario field assertions can validate `estimate.geofence.is_feasible`.

## Out of Scope

- Dynamic airspace feeds.
- UTM/U-space.
- Terrain or obstacle avoidance.
