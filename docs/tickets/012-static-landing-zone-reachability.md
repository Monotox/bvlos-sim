# Ticket 012: Static Landing Zone Reachability

Status: implemented.

## Goal

Add deterministic contingency reachability checks for landing alternatives.

## Current Gap

This ticket is complete. Static landing-zone reachability is available from the
estimator, scenario runner, and CLI paths.

## Scope

- Add core landing zone model.
- Add GeoJSON landing zone importer adapter if needed.
- Add straight-line reachability calculation from route samples or waypoints.
- Add remaining-energy-to-divert estimate.
- Document v1 limits explicitly:
  - no terrain
  - no obstacles
  - no dynamic landing-zone availability
  - no landing suitability scoring
  - no comms dependency
- Add diagnostics:
  - `no_reachable_landing_zone`
  - `landing_zone_reachable_but_below_reserve`
  - `unsupported_landing_zone_geometry`

## Acceptance Criteria

- Supported missions report whether deterministic landing alternatives exist under the v1 model.

## Implementation Notes

- Core landing-zone models are independent of GeoJSON and use lat/lon domain coordinates.
- The GeoJSON adapter supports `Point`, `Polygon`, and `MultiPolygon`, including holes, and reads coordinates in `[lon, lat]` order.
- Reachability is evaluated after deterministic energy and geofence feasibility.
- The v1 route states are route leg end states.
- Reachable distance uses straight-line geodesic distance to a point zone or nearest polygon point.
- Divert energy uses resolved cruise TAS and deterministic cruise power.
- Reserve after divert is compared to the same reserve threshold used by deterministic energy feasibility.
- JSON envelope versions were bumped to `estimator-envelope.v4` and `mission.v4` because `assets.landing_zones_file` and `constraints.min_distance_to_landing_zone_m` are now operative and the result shape includes `result.landing_zone`.

## Integrated Surfaces

- Mission YAML references landing-zone GeoJSON through
  `assets.landing_zones_file`.
- Landing-zone examples live under `data/landing_zones/` and are used by
  mission examples.
- `estimate` and `scenario` load landing-zone assets from the mission file
  directory and pass domain `LandingZone` objects into the core engine.
- JSON and Markdown reports include landing-zone feasibility, nearest zone
  data, reachability, and reserve-after-divert values.
- Scenario field assertions can validate `estimate.landing_zone.is_feasible`.

## Out of Scope

- Dynamic suitability scoring.
- Terrain-based landing analysis.
- Weather-dependent landing scoring.
