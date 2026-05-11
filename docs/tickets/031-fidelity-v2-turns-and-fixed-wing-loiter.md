# Ticket 031: Fidelity v2 Core - Turn Dynamics and Fixed-Wing Loiter

## Status

Implemented in May 2026.

## Goal

Improve trajectory realism where v1 currently uses simple leg-to-leg geodesics.

## Current Gap

This ticket is complete. Turn-arc dynamics and fixed-wing circular loiter are
available when fidelity v2 is selected.

## Scope

- Add turn-dynamics estimate.
- Add fixed-wing circular loiter model.
- Add compatibility mode preserving v1 behavior.
- Add tests for v1/v2 behavior separation.

## Acceptance Criteria

- Fixed-wing circular loiter and turn-aware estimates are available behind explicit fidelity selection.
- v1-compatible mode remains stable.

## Integrated Surfaces

- Mission YAML enables the behavior with `estimation.fidelity: v2`.
- Scenario YAML enables the behavior with `initial_conditions.fidelity: v2`.
- The `estimate` CLI enables the behavior with `--fidelity v2`.
- Fidelity v2 route expansion feeds the same downstream energy, geofence,
  landing-zone, terrain, wind, scenario assertion, JSON, and Markdown paths.
- v1 remains the default compatibility mode for existing examples and golden
  fixtures unless explicitly overridden.

## Out of Scope

- SITL comparison logic.
- Full flight-dynamics simulation.
