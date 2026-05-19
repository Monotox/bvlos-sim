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
- resource and communication-link feasibility abstractions
- golden fixture regression tests
- package-root public Python API
- dynamic landing-zone availability via scenario `landing_zone_unavailable` events
- computed divert route estimates on `CommsLinkPolicyOutcome.divert_estimate` (distance, time, energy, reserve, feasibility)
- Monte Carlo uncertainty sampling via `uncertainty.v1` YAML and `sample` CLI command; seeded reproducible runs varying wind, cruise speed, cruise power, and battery capacity
- Dubins path solver for bank-angle-constrained divert routing; divert distance uses RS/LS arc + straight when entry heading and turn radius are available
- fidelity v2 tangent-point offset subtraction on transit legs adjacent to TURN_ARC legs for true Dubins-path total distance
- 3D slant path distance for takeoff and landing-transit legs (`path_distance_m = vertical_distance_m`)
- geodesic-aware Dubins divert sampling with the planar-limit warning retired
- SITL adapter contract and `sitl-evidence.v1` evidence schema
- connect-mode ArduPilot SITL adapter with MAVLink mission upload support
- SITL telemetry, command, simulator, and adapter artifact recording for
  ArduPilot evidence bundles
- SITL scenario comparison reports through `sitl-comparison.v1` and `compare`
- passing Linux estimator/schema/CLI/scenario/SITL comparison test suite with
  491 tests and 9 skipped live or environment-dependent tests

## Implemented Integration Validation

Implemented tickets are expected to operate together through the same runtime
path rather than through isolated examples. Current validation includes:

- `estimate` loading mission YAML, vehicle YAML, terrain YAML, wind-grid YAML,
  geofence GeoJSON, and landing-zone GeoJSON together.
- `scenario` loading the same mission asset stack before executing events,
  policies, assertions, and reports.
- Integrated examples under `examples/missions/` and `examples/scenarios/`
  combining fidelity v2, terrain, spatiotemporal wind, geofence checks,
  landing-zone checks, energy feasibility, resource systems, link systems, and
  lost-link policy assertions.
- Golden fixtures and CLI tests covering canonical JSON, Markdown, exit codes,
  provenance, and deterministic outputs.

## Main Execution Backlog

### Implemented

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
13. [034-resource-and-link-feasibility-abstractions.md](./034-resource-and-link-feasibility-abstractions.md) - implemented
14. [035-dynamic-landing-zone-availability.md](./035-dynamic-landing-zone-availability.md) - implemented
15. [036-computed-divert-routing.md](./036-computed-divert-routing.md) - implemented
16. [037-monte-carlo-uncertainty-modeling.md](./037-monte-carlo-uncertainty-modeling.md) - implemented
17. [038-bank-angle-and-dubins-path-optimization.md](./038-bank-angle-and-dubins-path-optimization.md) - implemented
18. [039-path-planning-model-gaps.md](./039-path-planning-model-gaps.md) - implemented
19. [040-sitl-adapter-contract-and-evidence-schema.md](./040-sitl-adapter-contract-and-evidence-schema.md) - implemented
20. [041-ardupilot-sitl-launch-and-mission-upload.md](./041-ardupilot-sitl-launch-and-mission-upload.md) - implemented
21. [042-sitl-telemetry-recorder-and-evidence-bundle.md](./042-sitl-telemetry-recorder-and-evidence-bundle.md) - implemented
22. [043-sitl-scenario-comparison-report.md](./043-sitl-scenario-comparison-report.md) - implemented
23. [057-summary-output-format.md](./057-summary-output-format.md) - implemented

### Planned

24. [055-geojson-kml-route-export.md](./055-geojson-kml-route-export.md) — planned
25. [056-community-vehicle-profiles.md](./056-community-vehicle-profiles.md) — planned
26. [052-real-world-data-fetch-scripts.md](./052-real-world-data-fetch-scripts.md) — planned
27. [053-airspace-geofence-fetch-script.md](./053-airspace-geofence-fetch-script.md) — planned
28. [058-notam-live-airspace-integration.md](./058-notam-live-airspace-integration.md) — planned
29. [047-stochastic-state-propagation.md](./047-stochastic-state-propagation.md) — planned
30. [048-observation-model-and-twin-state.md](./048-observation-model-and-twin-state.md) — planned
31. [049-stochastic-closed-loop-control.md](./049-stochastic-closed-loop-control.md) — planned
32. [044-geodesic-dubins-divert.md](./044-geodesic-dubins-divert.md) — planned
33. [054-reference-inputs-for-calibration-and-import.md](./054-reference-inputs-for-calibration-and-import.md) — planned
34. [045-px4-sitl-launch-and-mission-upload.md](./045-px4-sitl-launch-and-mission-upload.md) — planned
35. [046-px4-sitl-telemetry-recorder-and-evidence-bundle.md](./046-px4-sitl-telemetry-recorder-and-evidence-bundle.md) — planned
36. [050-user-interfaces-and-service-adapters.md](./050-user-interfaces-and-service-adapters.md) — planned
37. [060-import-export-and-batch-workflows.md](./060-import-export-and-batch-workflows.md) — planned
38. [070-operational-integration-seams.md](./070-operational-integration-seams.md) — planned
39. [071-live-comms-remote-id-and-traffic-integrations.md](./071-live-comms-remote-id-and-traffic-integrations.md) — planned

## Limitation Coverage and Status

- SITL adapter contract and evidence schema: Ticket 040, implemented.
- ArduPilot SITL connect/upload integration: Ticket 041, implemented.
- ArduPilot SITL telemetry evidence: Ticket 042, implemented.
- SITL comparison reporting through adapter APIs and `compare`:
  Ticket 043, implemented.
- Geodesic-aware Dubins divert path sampling: Ticket 044, planned.
- No PX4 SITL adapter yet: Tickets 045 (launch/upload) and 046 (telemetry/evidence).
- No stochastic state propagation yet: Ticket 047 (propagator), 048 (twin-state
  EKF observation model), 049 (closed-loop tracking controller).
- No REST API or UI: Ticket 050.
- No real-world data fetch scripts yet: Ticket 052 (wind/terrain/LZ), 053
  (geofences), 054 (reference inputs for calibration and import design).
- No GeoJSON/KML route export: Ticket 055.
- No community vehicle profiles: Ticket 056.
- Terse `estimate` and `scenario` summary output: Ticket 057, implemented.
- No NOTAM/live airspace integration: Ticket 058.
- No batch import/export workflows or report diff tooling: Ticket 060.
- No live comms, UTM/U-space, Remote ID, or traffic integrations: Tickets 070
  and 071.
- No real-world calibration pipeline: Tickets 080-084.

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

- mission, vehicle, scenario, resource, link, terrain, wind, geofence, and
  landing-zone YAML/JSON schemas
- examples under `examples/missions`, `examples/vehicles`,
  `examples/scenarios`, `examples/terrain`, and `examples/wind`
- existing CLI commands such as `estimate`, `scenario`, `sample`, and `sitl`, or
  adapter commands that reuse the same core execution path
- canonical JSON envelopes, Markdown reports, golden fixtures, and regression
  tests
- package-root Python APIs and existing estimator/scenario execution contracts

New capabilities should work together with previously implemented pieces rather
than requiring separate one-off input formats or isolated commands.
