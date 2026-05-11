# Ticket 010: Deterministic Energy Feasibility

Status: implemented.

## Goal

Add deterministic energy and reserve checks without expanding geometry scope.

## Current Gap

This ticket is complete. Energy feasibility and reserve-at-landing results are
part of the estimator and scenario outputs.

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

## Integrated Surfaces

- Vehicle YAML defines battery capacity, usable energy policy, reserve default,
  and phase energy parameters.
- Mission YAML can override reserve requirements with
  `constraints.min_landing_reserve_percent`.
- `estimate` and `scenario` outputs include `result.energy` /
  `estimate.energy` fields in JSON and Markdown.
- Energy assertions are available through scenario field assertions such as
  `estimate.energy.is_feasible`.
- Energy behavior composes with terrain, wind, geofence, landing-zone, and
  fidelity-v2 route expansion.

## Out of Scope

- Weather uncertainty.
- Battery degradation modeling.
- Live telemetry integration.
