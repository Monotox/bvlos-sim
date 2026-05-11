# Ticket Backlog

This directory contains the project execution backlog. Completed tickets are
kept as historical implementation records; open tickets describe planned work.

## Implemented Baseline

The current codebase includes:

- mission, vehicle, and scenario schemas
- deterministic distance and time estimation
- deterministic energy feasibility
- static GeoJSON geofence feasibility
- static GeoJSON landing-zone reachability
- estimator and scenario CLI commands
- canonical JSON envelopes and Markdown reports
- deterministic scenario runner with lost-link policy outcomes
- scenario wind-change events
- layered wind, sub-segment sampling, turn arcs, and fixed-wing circular loiter
- terrain-referenced altitude with offline uniform elevation grid
- continuous spatiotemporal wind grid with quadrilinear interpolation
- golden fixture regression tests
- package-root public Python API
- dynamic landing-zone availability via scenario `landing_zone_unavailable` events
- computed divert route estimates on `CommsLinkPolicyOutcome.divert_estimate` (distance, time, energy, reserve, feasibility)
- passing estimator/schema/CLI/scenario test suite with 338 tests

## Implemented Integration Validation

Implemented tickets are expected to operate together through the same runtime
path rather than through isolated examples. Current validation includes:

- `estimate` loading mission YAML, vehicle YAML, terrain YAML, wind-grid YAML,
  geofence GeoJSON, and landing-zone GeoJSON together.
- `scenario` loading the same mission asset stack before executing events,
  policies, assertions, and reports.
- Integrated examples under `examples/missions/` and `examples/scenarios/`
  combining fidelity v2, terrain, spatiotemporal wind, geofence checks,
  landing-zone checks, energy feasibility, and lost-link policy assertions.
- Golden fixtures and CLI tests covering canonical JSON, Markdown, exit codes,
  provenance, and deterministic outputs.

## Main Execution Backlog

1. [001-estimator-cli-and-envelope.md](./001-estimator-cli-and-envelope.md) - implemented
2. [002-versioning-and-golden-fixtures.md](./002-versioning-and-golden-fixtures.md) - implemented
3. [003-technical-debt-hardening.md](./003-technical-debt-hardening.md) - implemented
4. [010-deterministic-energy-feasibility.md](./010-deterministic-energy-feasibility.md) - implemented
5. [011-static-geofence-feasibility.md](./011-static-geofence-feasibility.md) - implemented
6. [012-static-landing-zone-reachability.md](./012-static-landing-zone-reachability.md) - implemented
7. [020-scenario-runner-core.md](./020-scenario-runner-core.md) - implemented
8. [021-comms-link-and-contingency-policies.md](./021-comms-link-and-contingency-policies.md) - implemented
9. [030-fidelity-v2-layered-wind-and-subsegments.md](./030-fidelity-v2-layered-wind-and-subsegments.md) - implemented
10. [031-fidelity-v2-turns-and-fixed-wing-loiter.md](./031-fidelity-v2-turns-and-fixed-wing-loiter.md) - implemented
11. [032-terrain-referenced-altitude-execution.md](./032-terrain-referenced-altitude-execution.md) - implemented
12. [033-continuous-spatiotemporal-wind-grid.md](./033-continuous-spatiotemporal-wind-grid.md) - implemented
13. [034-resource-and-link-feasibility-abstractions.md](./034-resource-and-link-feasibility-abstractions.md) - planned
14. [035-dynamic-landing-zone-availability.md](./035-dynamic-landing-zone-availability.md) - implemented
15. [036-computed-divert-routing.md](./036-computed-divert-routing.md) - implemented
16. [037-monte-carlo-uncertainty-modeling.md](./037-monte-carlo-uncertainty-modeling.md) - planned
17. [040-sitl-ardupilot-first.md](./040-sitl-ardupilot-first.md) - planned
18. [050-user-interfaces-and-service-adapters.md](./050-user-interfaces-and-service-adapters.md) - planned
19. [060-import-export-and-batch-workflows.md](./060-import-export-and-batch-workflows.md) - planned
20. [070-operational-integration-seams.md](./070-operational-integration-seams.md) - planned
21. [071-live-comms-remote-id-and-traffic-integrations.md](./071-live-comms-remote-id-and-traffic-integrations.md) - planned

## Limitation Coverage and Status

- No SITL integration yet: Ticket 040.
- No REST API or UI: Ticket 050.
- No generalized resource and link feasibility abstraction: Ticket 034.
- No Monte Carlo uncertainty modeling: Ticket 037.
- Terrain-referenced altitude execution: Ticket 032, implemented.
- Continuous spatial and temporal wind grid support: Ticket 033, implemented.
- Dynamic landing-zone availability via scenario `landing_zone_unavailable` events: Ticket 035, implemented.
- Computed divert route estimates on `CommsLinkPolicyOutcome.divert_estimate`: Ticket 036, implemented.
- No live comms, UTM/U-space, Remote ID, or traffic integrations: Tickets 070
  and 071.

## Validation and Calibration Track

1. [080-flight-log-ingestion-and-trace-normalization.md](./080-flight-log-ingestion-and-trace-normalization.md) - planned
2. [081-flight-phase-segmentation.md](./081-flight-phase-segmentation.md) - planned
3. [082-predicted-vs-observed-validation-metrics.md](./082-predicted-vs-observed-validation-metrics.md) - planned
4. [083-calibration-profile-data-and-fitting.md](./083-calibration-profile-data-and-fitting.md) - planned
5. [084-holdout-validation-reports.md](./084-holdout-validation-reports.md) - planned

## Backlog Rules

- Keep core execution deterministic.
- Add adapter layers only after core contracts are clear.
- Keep schemas and public outputs versioned.
- Reject unsupported inputs explicitly instead of approximating silently.
- Do not add live external dependencies to core CI.
- Update docs, tests, and fixtures in the same change when public behavior changes.

## Integration Standard

Every new ticket must explain how the work composes with existing functionality.
Unless a ticket explicitly states otherwise, implementation should integrate
through the established surfaces:

- mission, vehicle, scenario, terrain, wind, geofence, and landing-zone YAML/JSON
  schemas
- examples under `examples/missions`, `examples/vehicles`,
  `examples/scenarios`, `examples/terrain`, and `examples/wind`
- existing CLI commands such as `estimate` and `scenario`, or adapter commands
  that reuse the same core execution path
- canonical JSON envelopes, Markdown reports, golden fixtures, and regression
  tests
- package-root Python APIs and existing estimator/scenario execution contracts

New capabilities should work together with previously implemented pieces rather
than requiring separate one-off input formats or isolated commands.
