# Ticket 035: Computed Divert Routing

## Goal

Compute deterministic divert route estimates for lost-link and contingency
policy outcomes instead of recording only the selected divert target ID.

## Current Gap

The lost-link policy outcome can record a `divert_target_id`, but it does not
compute a route, time, energy, geofence interaction, or landing-zone feasibility
for the divert action.

## Scope

- Add deterministic divert-route construction from the policy action point.
- Estimate divert distance, time, energy, and reserve after divert.
- Reuse landing-zone reachability and geofence checks where applicable.
- Add policy outcome fields or a versioned result extension for divert details.
- Add tests for reachable, infeasible, and missing-target divert cases.
- Update golden fixtures if public result contracts change.

## Acceptance Criteria

- `divert` policy outcomes include deterministic route and feasibility evidence.
- Infeasible divert actions produce structured diagnostics.
- Existing non-divert lost-link policy behavior remains stable.

## Out of Scope

- Real-time route replanning against live airspace.
- Obstacle-aware path planning.
- Operator command execution.
