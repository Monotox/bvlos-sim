# Ticket 021: Comms Link Model and Contingency Policies

## Status

Implemented in May 2026.

## Goal

Make deterministic scenario testing useful for BVLOS contingencies.

## Current Gap

This ticket is complete. Lost-link events and deterministic policy outcomes are
available in scenario execution.

## Scope

- Add simple comms-link state model.
- Add lost-link policy evaluator.
- Add policy actions:
  - `rtl`
  - `land`
  - `loiter`
  - `divert`
- Integrate policy logic into scenario runner timeline.
- Add deterministic assertions against policy outcomes.

## Acceptance Criteria

- Lost-link behavior can be deterministically tested from scenario inputs.
- Policy outcomes are visible in JSON/Markdown scenario reports.

## Integrated Surfaces

- Scenario YAML configures `lost_link_policy` under `initial_conditions`.
- `lost_link` events can trigger at mission start, mission end, route item, or
  elapsed time.
- Policy actions `rtl`, `land`, `loiter`, and `divert` are represented in
  scenario event outcomes.
- `policy_action_eq` assertions validate policy decisions in the same scenario
  report as estimator assertions.
- The `scenario` CLI reports policy outcomes in canonical JSON and Markdown.
- Divert target IDs can refer to landing-zone asset IDs, while computed divert
  routes remain planned in Ticket 036.

## Out of Scope

- MAVLink execution.
- Real radios or LTE/satellite integrations.
