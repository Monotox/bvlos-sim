# Ticket 032: Terrain-Referenced Altitude Execution

Status: implemented.

## Goal

Support mission legs whose altitude reference is terrain-relative while keeping
estimator outputs deterministic and auditable.

## Current Gap

Terrain-referenced altitude inputs are rejected as unsupported. The estimator
does not load terrain data, resolve ground elevation along a route, or report
terrain-derived altitude assumptions.

## Scope

- Add a deterministic terrain provider interface.
- Add at least one offline terrain-data adapter.
- Resolve terrain-relative route-item altitudes into AMSL altitudes.
- Add diagnostics when required terrain coverage is missing.
- Record terrain provider metadata in estimator outputs.
- Add focused schema, estimator, CLI, and golden-fixture coverage.

## Acceptance Criteria

- Missions using terrain-referenced altitude can run when terrain coverage is
  available.
- Missing or unsupported terrain data fails with structured diagnostics.
- Existing AMSL and relative-home behavior remains stable.

## Delivered

- `TerrainProvider` Protocol in `estimator/environment/terrain.py`
- `ConstantElevationProvider` — fixed elevation for all positions
- `GridTerrainProvider` — uniform elevation grid with bilinear interpolation
- `terrain_provider_id` utility matching the wind provider pattern
- `adapters/terrain_grid.py` — `load_terrain_grid` and `TerrainGridLoadError` for YAML/JSON grid files
- `assets.terrain_file` field on `MissionAssets` schema
- CLI loads terrain from `assets.terrain_file` and passes it to the engine
- `terrain_provider` parameter on `estimate_mission_distance_time` and `try_estimate_mission_distance_time`
- `TERRAIN_COVERAGE_MISSING` failure code for out-of-bounds queries
- `terrain_provider_id` recorded in result metadata
- `TerrainProvider`, `ConstantElevationProvider`, `GridTerrainProvider` exported from `estimator`
- `examples/terrain/flat_polder.yaml` example grid
- Golden fixture scenario `tests/fixtures/golden/terrain/`
- 19 new tests in `tests/test_terrain_altitude.py`

## Out of Scope

- Online terrain service calls during core estimation.
- Obstacle clearance modeling.
- Regulatory terrain/obstacle compliance claims.
