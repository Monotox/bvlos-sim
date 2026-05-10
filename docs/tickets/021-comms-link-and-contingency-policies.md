# Ticket 021: Comms Link Model and Contingency Policies

## Goal

Make deterministic scenario testing useful for BVLOS contingencies.

## Current Gap

There is no comms-link state model, no lost-link policy evaluator, and no policy action layer.

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

## Out of Scope

- MAVLink execution.
- Real radios or LTE/satellite integrations.
