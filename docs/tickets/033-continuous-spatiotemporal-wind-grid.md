# Ticket 033: Continuous Spatiotemporal Wind Grid

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

## Out of Scope

- Live weather API calls from core estimation.
- Probabilistic weather ensembles.
- Meteorological forecast validation.
