# Ticket 100: Obstacle Database and Vertical Clearance Checks

## Status

Implemented.

## Goal

Add an optional obstacle layer (vertical structures: towers, masts, wires,
cranes, buildings) and a deterministic clearance check that flags route legs
passing within configurable horizontal/vertical separation of an obstacle —
including terrain clearance along the leg, not just at waypoints.

## Why This Is High Impact

This is the most dangerous current blind spot. Today a route is "clear" if it
does not cross a 2D geofence polygon (and even that is altitude-blind — see
Ticket 061). Nothing models physical obstacles: a 48 m antenna 200 m ahead of a
49 m AGL leg is invisible to the tool. For low-altitude BVLOS, obstacle and
wire strike is a primary risk; a feasibility tool that ignores it cannot be
trusted near infrastructure, and "feasible" is actively misleading.

Terrain is already loaded (`assets.terrain_file`) but only resolved per waypoint
for altitude reference — there is no along-leg clearance check, so a leg can
clip a ridge between two waypoints and still pass.

## Current gap

- No obstacle schema or provider anywhere in `estimator/environment/`.
- `estimator/execution/altitude.py` resolves terrain-referenced altitude at
  waypoints but does not verify clearance along the sampled leg.
- Geofence is 2D (`GEOFENCE_EVALUATED_2D_ONLY`); 3D bounds are Ticket 061.

## Scope

### Obstacle input

A GeoJSON obstacle layer referenced from the mission, reusing the existing
asset-loading pattern (`adapters/assets/`):

```yaml
assets:
  obstacles_file: assets/obstacles.geojson   # Points/LineStrings/Polygons with height_m (+ optional radius_m, uncertainty_m)
```

A `fetch_obstacles.py` script (opt-in, like the other fetch scripts) can seed it
from open sources (e.g. OSM `man_made=mast/tower`, power lines); obstacle data
quality is the operator's responsibility and documented as such.

### Clearance check

- New `estimator/execution/obstacle.py` returning an evaluation object
  (`.failure` + an `ObstacleEstimate` result block), threaded into the engine
  exactly like the other feasibility checks (energy/geofence/...).
- Samples each leg (reusing the sub-segment machinery) and checks 3D separation
  against each obstacle: horizontal distance and the leg's AMSL altitude vs
  `obstacle.height_m` plus a configurable safety buffer
  (`constraints.min_obstacle_clearance_m`).
- Terrain clearance: along the sampled leg, verify AMSL altitude minus terrain
  elevation ≥ `constraints.min_terrain_clearance_m` when a terrain provider is
  configured.
- New `FailureCode`s: `OBSTACLE_CLEARANCE_VIOLATED`, `TERRAIN_CLEARANCE_VIOLATED`.

### Surfacing

- `ObstacleEstimate` block in the JSON envelope, a checklist row
  (`Obstacle clearance` PASS/FAIL/N-A), a summary field, a Markdown section, and
  an optional GeoJSON obstacle layer in the export.

### Files to create or modify

| File | Change |
|---|---|
| `estimator/core/obstacle.py` | New — obstacle value objects |
| `estimator/environment/obstacle.py` | New — obstacle provider Protocol + grid/list impl |
| `adapters/assets/obstacle_geojson.py` | New — loader (mirrors geofence/LZ loaders) |
| `estimator/execution/obstacle.py` | New — clearance evaluation |
| `estimator/core/results.py` | `ObstacleEstimate` result block (exclude_if default) |
| `estimator/core/enums.py` | New failure codes |
| `estimator/execution/engine.py` | Thread the obstacle check into the pipeline |
| `adapters/checklist_markdown.py`, `adapters/summary.py`, `adapters/markdown.py`, `adapters/geojson_export.py` | Surface the block consistently |
| `schemas/mission.py` | `assets.obstacles_file`, clearance constraints |
| `scripts/fetch_obstacles.py` | New — opt-in obstacle fetch |
| `docs/USAGE.md`, `docs/ESTIMATOR_V1_FIELD_SEMANTICS.md` | Document inputs, checks, limits |
| `tests/test_obstacle_clearance.py` | New — clearance feasible/infeasible, terrain clip, missing-data |

### Acceptance criteria

1. A route leg passing within the configured buffer of an obstacle returns
   `INFEASIBLE` with `OBSTACLE_CLEARANCE_VIOLATED`, attributed to the leg and
   obstacle id.
2. A leg that clips terrain between two waypoints returns
   `TERRAIN_CLEARANCE_VIOLATED` even when both waypoint altitudes are clear.
3. With no `obstacles_file` and no terrain clearance constraint, output is
   unchanged (block is `None`, fixtures unaffected).
4. The obstacle block appears consistently in JSON, checklist, summary, Markdown,
   and (when present) the GeoJSON export.
5. Obstacle-data provenance/quality limitations are documented; no live lookups
   in the core.
