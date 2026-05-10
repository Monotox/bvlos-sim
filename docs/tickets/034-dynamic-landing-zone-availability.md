# Ticket 034: Dynamic Landing-Zone Availability

## Goal

Allow landing-zone availability to change over a scenario timeline while
preserving deterministic reachability checks.

## Current Gap

Landing zones are static. The estimator can check reachability, but scenarios
cannot mark landing zones unavailable due to time, policy, weather, occupancy,
or other deterministic events.

## Scope

- Add scenario inputs for landing-zone availability changes.
- Resolve availability changes against the scenario timeline.
- Apply availability state to landing-zone reachability checks.
- Add structured diagnostics for no available reachable landing zone.
- Document precedence between static assets and scenario availability events.
- Add scenario, estimator, CLI, and fixture coverage.

## Acceptance Criteria

- A scenario can make a landing zone unavailable before a divert decision.
- Reachability outputs identify which zones were considered available.
- Static landing-zone behavior remains unchanged when no availability events are
  configured.

## Out of Scope

- Live landing-zone occupancy feeds.
- Suitability scoring based on surface condition, weather, or obstacle surveys.
- Operator dispatch workflows.
