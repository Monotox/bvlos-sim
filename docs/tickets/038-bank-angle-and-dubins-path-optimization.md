# Ticket 038: Bank-Angle Model and Dubins Path Optimization

## Status

Implemented.

## Goal

Replace the straight-line geodesic divert path and the fidelity v2 turn-arc
approximation with a proper bank-angle-constrained Dubins path model for all
horizontal path planning: divert routing, transit legs, and turn segments.

## Current Gap

There are three related path-planning limitations in the current codebase:

- Divert routing (`CommsLinkPolicyOutcome.divert_estimate`) uses straight-line
  geodesic distance with no bank-angle constraint, no heading continuity, and
  no turn cost.
- Fidelity v2 turn arcs use a circular arc path-length approximation
  (`turn_radius_m * abs(delta_heading_rad)`) but do not enforce a Dubins-path
  entry/exit heading constraint between segments.
- Vertical-only route items (`takeoff`, `land`) do not add 3D slant path
  distance. Horizontal distance is zero even when the vehicle climbs or
  descends with non-zero horizontal displacement.

## Scope

- Implement a Dubins path solver (`RSR`, `LSL`, `RSL`, `LSR`, `RLR`, `LRL`)
  using `vehicle.performance.turn_radius_m` and
  `vehicle.performance.max_crab_angle_deg`.
- Replace `divert.py` straight-line distance with Dubins path distance when
  entry heading is available.
- Replace fidelity v2 turn-arc approximation with Dubins segment length that
  includes correct entry and exit heading constraints.
- Optionally add 3D slant path distance for vertical legs. This may be deferred
  as out of scope if needed.
- Add unit tests for Dubins path geometry and regression tests against existing
  fidelity v2 golden fixtures.
- Update [ESTIMATOR_V1_FIELD_SEMANTICS.md](../ESTIMATOR_V1_FIELD_SEMANTICS.md)
  Divert Routing Semantics and Fidelity Semantics sections when the bank-angle
  model becomes operative.
- Update golden fixtures if public result contracts change.

## Integration Requirements

- Reuse `vehicle.performance.turn_radius_m`.
- Expose through existing `estimate`, `scenario`, and `sample` commands without
  new flags.
- Keep fidelity v1 behavior unchanged.
- Keep divert routing result fields (`distance_m`, `time_s`, `energy_wh`, and
  related fields) stable; only their values change.

## Acceptance Criteria

- Divert distance accounts for bank-angle-constrained heading change when entry
  heading is known.
- Fidelity v2 turn segments satisfy Dubins path entry/exit heading constraints.
- Fidelity v1 behavior is unchanged.
- The existing test suite passes; new Dubins geometry tests are added.

## Out of Scope

- Real-time obstacle avoidance.
- 3D Dubins paths.
- Vertical slant path, if deferred to a separate ticket.
