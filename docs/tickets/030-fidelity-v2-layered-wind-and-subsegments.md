# Ticket 030: Fidelity v2 Core - Layered Wind and Sub-Segment Sampling

## Status

Implemented in May 2026.

## Goal

Improve model fidelity without breaking v1 estimator contracts.

## Current Gap

This ticket is complete. Fidelity v2, layered wind, and sub-segment sampling
are available through mission YAML, scenario YAML, CLI flags, and Python APIs.
They are separate controls: fidelity v2 enables neither layered wind nor
straight-leg sub-segment sampling by itself.

## Scope

- Add `LayeredWindProvider`.
- Add optional fixed sub-segment sampling for long legs.
- Add deterministic sampling policy and compatibility mode for v1 behavior.
- Add independent schema controls for fidelity and maximum segment length.

## Acceptance Criteria

- Users can choose fidelity and layered/sub-segment behavior independently.
- Existing v1 golden outputs remain stable unless explicitly running the v2 mode.

## Integrated Surfaces

- Mission YAML configures `estimation.fidelity`, `estimation.wind_layers`,
  `estimation.max_segment_length_m`, and `estimation.min_groundspeed_mps`.
- Scenario YAML configures the same estimator controls through
  `initial_conditions`.
- The `estimate` CLI exposes `--fidelity`, repeated `--wind-layer`, and
  `--max-segment-length-m` options.
- `scenario` execution honors scenario initial conditions and can use mission
  asset wind providers when no explicit scenario wind is set.
- Layered wind and sub-segment sampling compose with energy, geofence,
  landing-zone, terrain, wind-grid, and result-envelope behavior.

## Out of Scope

- Weather grids.
- Stochastic sampling.
- Turn dynamics.
