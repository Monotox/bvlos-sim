# Ticket 031: Fidelity v2 Core - Turn Dynamics and Fixed-Wing Loiter

## Goal

Improve trajectory realism where v1 currently uses simple leg-to-leg geodesics.

## Current Gap

There is no turn-dynamics estimate and no fixed-wing circular loiter model.

## Scope

- Add turn-dynamics estimate.
- Add fixed-wing circular loiter model.
- Add compatibility mode preserving v1 behavior.
- Add tests for v1/v2 behavior separation.

## Acceptance Criteria

- Fixed-wing circular loiter and turn-aware estimates are available behind explicit fidelity selection.
- v1-compatible mode remains stable.

## Out of Scope

- SITL comparison logic.
- Full flight-dynamics simulation.
