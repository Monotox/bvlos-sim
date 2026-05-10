# Ticket 030: Fidelity v2 Core - Layered Wind and Sub-Segment Sampling

## Goal

Improve model fidelity without breaking v1 estimator contracts.

## Current Gap

Only constant wind is supported and long legs are sampled once.

## Scope

- Add `LayeredWindProvider`.
- Add optional fixed sub-segment sampling for long legs.
- Add deterministic sampling policy and compatibility mode for v1 behavior.
- Add schema flags for fidelity mode selection.

## Acceptance Criteria

- Users can choose v1-compatible mode or layered/sub-segment mode.
- Existing v1 golden outputs remain stable unless explicitly running the v2 mode.

## Out of Scope

- Weather grids.
- Stochastic sampling.
- Turn dynamics.
