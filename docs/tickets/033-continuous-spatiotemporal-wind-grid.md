# Ticket 033: Continuous Spatiotemporal Wind Grid

Status: implemented.

## Goal

Model wind as a deterministic function of position, altitude, and elapsed time
beyond the current constant, altitude-layered, and scenario wind-change models.

## Current Gap

Wind can be constant, altitude-banded, or changed at scenario event times. There
is no continuous spatial or temporal wind grid and no adapter for gridded
weather products.

## Scope

- Add a deterministic spatiotemporal wind provider interface.
- Define a versioned wind-grid input format.
- Add interpolation rules for latitude, longitude, altitude, and elapsed time.
- Add bounds and missing-data diagnostics.
- Keep existing `ConstantWindProvider`, `LayeredWindProvider`, and scenario
  `wind_change` behavior compatible.
- Add estimator, scenario, CLI, and fixture coverage.

## Acceptance Criteria

- Users can run deterministic estimates against an offline wind grid.
- Every wind sample is reproducible for a given input grid and route state.
- Unsupported or incomplete grid data fails explicitly.

## Delivered

- `SpatiotemporalWindProvider` in `estimator/environment/wind.py` — quadrilinear interpolation across time, altitude, lat, and lon axes; flat tuple storage with stride-based indexing; clamping at domain boundaries
- `_lerp` and `_interp_index` module-level helpers using `bisect.bisect_right`
- `wind_provider_id` updated to return `"spatiotemporal_grid"` for `SpatiotemporalWindProvider`
- `adapters/wind_grid.py` — `load_wind_grid` and `WindGridLoadError` for YAML/JSON grid files
- Load-time validation: axis monotonicity, minimum 2 entries per axis, exact `values` shape check
- `assets.wind_grid_file` field on `MissionAssets` schema
- CLI loads wind grid from `assets.wind_grid_file`; `--wind-layer` flags take precedence
- `WIND_GRID_SCHEMA_VERSION = "wind-grid.v1"` and `wind_grid` provenance in `EnvelopeInputs`
- `SpatiotemporalWindProvider` exported from `estimator`
- `examples/wind/pipeline_wind_grid.yaml` example grid
- Golden fixture scenario `tests/fixtures/golden/spatiotemporal_wind/`
- 22 new tests in `tests/test_wind_spatiotemporal.py`

## Out of Scope

- Live weather API calls from core estimation.
- Probabilistic weather ensembles.
- Meteorological forecast validation.
