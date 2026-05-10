# Ticket 010: Deterministic Energy Feasibility

Status: implemented.

## Goal

Add deterministic energy and reserve checks without expanding geometry scope.

## Current Gap

Distance/time estimation exists, but no energy feasibility or reserve-at-landing logic is implemented.

## Scope

- Add phase-based deterministic energy model:
  - takeoff
  - transit
  - loiter
  - landing
- Extend vehicle energy schema with:
  - battery capacity
  - usable energy policy
  - reserve threshold
  - phase consumption parameters
- Add energy result breakdown and reserve-at-landing calculation.
- Add diagnostics:
  - `insufficient_energy`
  - `reserve_below_threshold`
  - `missing_energy_model`
  - `unsupported_phase_energy_model`
  - `invalid_energy_model`
  - `invalid_energy_policy`
- Add Markdown feasibility rendering adapter.

## Acceptance Criteria

- Supported missions can be deterministically accepted or rejected for energy feasibility.
- Output clearly separates kinematic estimation from feasibility judgment.

## Implementation Notes

- Energy is evaluated after route kinematics complete.
- The result contains a per-leg energy breakdown, total mission energy, usable energy, reserve threshold, and reserve at landing.
- Mission reserve is an optional override; vehicle reserve default is used when the mission omits it.
- Energy feasibility failures keep kinematic totals complete when the full route was already estimated.
- JSON envelope versions were bumped to `estimator-envelope.v2`, `mission.v2`, and `vehicle.v2` because input semantics and result shape changed.

## Out of Scope

- Weather uncertainty.
- Battery degradation modeling.
- Live telemetry integration.
