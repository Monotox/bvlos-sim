# Ticket 035: Dynamic Landing-Zone Availability

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

## Integration Requirements

- Extend `scenario.v1` YAML in a backward-compatible way or bump the scenario
  schema version if result behavior changes.
- Keep static landing-zone assets loaded from mission YAML through
  `assets.landing_zones_file`.
- Add scenario YAML examples that combine landing-zone availability with
  lost-link policy, `divert`, wind changes, terrain assets, and wind-grid assets
  where relevant.
- Apply resource and link feasibility abstractions from Ticket 034 when
  availability depends on command-and-control continuity, external power,
  tether constraints, or other configured resource/link state.
- Ensure the `scenario` CLI command exercises availability changes through the
  same runner path used by library callers.
- Ensure the `estimate` command remains compatible with static landing-zone
  assets when no scenario availability events are configured.
- Update JSON/Markdown reports and golden fixtures when availability state
  becomes part of public outputs.

## Acceptance Criteria

- A scenario can make a landing zone unavailable before a divert decision.
- Reachability outputs identify which zones were considered available.
- Static landing-zone behavior remains unchanged when no availability events are
  configured.
- Existing mission, vehicle, terrain, wind, landing-zone, resource, and link
  YAML examples still run together without special-case commands.

## Out of Scope

- Live landing-zone occupancy feeds.
- Suitability scoring based on surface condition, weather, or obstacle surveys.
- Operator dispatch workflows.
