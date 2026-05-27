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
- one-line `--format summary` output for `estimate` and `scenario` with reserve %, flight time, policy action, and first failing check
- `--format geojson` and `--format kml` route exports with per-leg energy-margin layers, landing-zone reachability markers, and geofence conflict flags
- five community vehicle profiles in `examples/vehicles/community/` (DJI Matrice 300 RTK, Wingtra One Gen II, QS Trinity F90+, Autel EVO Max 4T, generic survey hexacopter) with manufacturer-derived values and provenance links
- `fetch_all.py` (one-command wrapper), `fetch_wind.py`, `fetch_terrain.py`, `fetch_landing_zones.py`, and `fetch_geofences.py` scripts for real SRTM terrain, Open-Meteo wind forecast, Overpass landing zones, and static airspace geofences; pre-fetched Alpine example in `examples/real_world/`
- deliberately infeasible demo mission (`alpine_infeasible.yaml` + `quadplane_small_battery.yaml`) with README explanation of what failed and how to fix it
- `bvlos-sim convert` QGC `.plan` importer and `bvlos-sim batch` multi-run estimate command with `batch.v1` manifest schema
- stochastic state propagation via particle sampling with `propagate` CLI command and `stochastic-envelope.v1` output
- twin-state stochastic observation model with per-particle estimated state and estimation-error timeline outputs
- stochastic closed-loop tracking controller with proportional cross-track / along-track error feedback, per-particle true-state deviation, path-length excess accounting, and cross-track timeline outputs
- advisory warnings for `MAX_WIND_EXCEEDED`, `RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD`, and `RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD` emitted when vehicle failsafe or max_wind thresholds are crossed
- MAV_CMD_NAV_TAKEOFF (fixed-wing) normalization diagnostic in the QGC `.plan` importer
- denominator-correct stochastic feasibility and reserve-violation rates (use particle count, not requested sample count)
- geofence/landing-zone spatial infeasibility tracked in stochastic propagation: `spatial_infeasible_count` in `StochasticPropagationResult`; three-way accounting `sample_count + failed_sample_count + spatial_infeasible_count == plan.samples`
- `loiter_time_s` validated as strictly positive at schema load time; `loiter_radius_m` emits `LOITER_RADIUS_IGNORED` warning when set
- `ROUTE_ACTIONS_AFTER_RTL` warning emitted when actions follow an RTL item (operationally unreachable legs)
- `--format summary` output now includes a `warnings N` field when the estimate has advisory warnings
- bug fix: `EstimationOptions.fidelity` is now optional; `--max-segment-length-m` without `--fidelity` no longer silently downgrades `estimation.fidelity: v2` missions to v1
- batch summary table now includes a `warnings` column
- wind-triangle correction applied to divert route estimates when a wind provider is available; DIVERT_ENERGY_TAS_ONLY warning suppressed when wind is corrected
- `--format summary` for `sample` and `propagate` commands (feasibility rate, p5/p50/p95 reserve, time, sample count)
- `policy_divert_feasible` assertion kind: evaluates whether the computed divert route for a lost-link event is energy-feasible; graceful SKIPPED when event didn't fire, no policy, or action isn't divert
- `not_fired_reason` field on `ScenarioEventOutcome`: human-readable explanation when a trigger didn't match (e.g. route item not found, elapsed time exceeded mission duration)
- scenario markdown report: assertion count summary line (`N passed, N failed, N skipped`) in header; human-readable flight time (`Xm YYs`) throughout estimate, scenario, stochastic, and uncertainty markdown reports
- `route_item_id` included in GeoJSON route leg properties and KML placemark names so map tools can correlate legs with named waypoints
- circular import between `schemas.stochastic` and `estimator.__init__` resolved; `test_scenario_schemas.py` now passes when run in isolation
- `--validate-only` flag on `estimate`, `scenario`, and `propagate` commands: validates all input files against their schemas and exits 0 (OK) or 11 (invalid input) without running the estimator; CI-friendly for catching schema errors early
- `--format checklist` output for `estimate` and `scenario` commands: pre-flight
  go/no-go checklist with ✓/✗/◌ icon per feasibility category and `Status: GO/NO-GO`
- `--format profile` output for `estimate` and `scenario` commands: per-leg altitude
  table with terrain elevation and clearance columns when a terrain provider is configured
- `--validate-only` flag on `sample` command matching `propagate`, `estimate`, and
  `scenario`; validates uncertainty, mission, and vehicle files without running the sampler
- `--format csv` output for `batch` command: comma-separated table importable into
  spreadsheets (id, status, reserve_margin_percent, flight_time_s, warning_count)
- `--format sensitivity` output for `estimate`: deterministic reserve sweep across
  cruise power, headwind, and battery-capacity variations with ROBUST/MARGINAL status
- passing Linux estimator/schema/CLI/scenario/SITL comparison test suite with
  853 passing tests and 9 skipped live or environment-dependent tests

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

1. [001-estimator-cli-and-envelope.md](./001-estimator-cli-and-envelope.md)
2. [002-versioning-and-golden-fixtures.md](./002-versioning-and-golden-fixtures.md)
3. [003-technical-debt-hardening.md](./003-technical-debt-hardening.md)
4. [010-deterministic-energy-feasibility.md](./010-deterministic-energy-feasibility.md)
5. [011-static-geofence-feasibility.md](./011-static-geofence-feasibility.md)
6. [012-static-landing-zone-reachability.md](./012-static-landing-zone-reachability.md)
7. [020-scenario-runner-core.md](./020-scenario-runner-core.md)
8. [021-comms-link-and-contingency-policies.md](./021-comms-link-and-contingency-policies.md)
9. [030-fidelity-v2-layered-wind-and-subsegments.md](./030-fidelity-v2-layered-wind-and-subsegments.md)
10. [031-fidelity-v2-turns-and-fixed-wing-loiter.md](./031-fidelity-v2-turns-and-fixed-wing-loiter.md)
11. [032-terrain-referenced-altitude-execution.md](./032-terrain-referenced-altitude-execution.md)
12. [033-continuous-spatiotemporal-wind-grid.md](./033-continuous-spatiotemporal-wind-grid.md)
13. [034-resource-and-link-feasibility-abstractions.md](./034-resource-and-link-feasibility-abstractions.md)
14. [035-dynamic-landing-zone-availability.md](./035-dynamic-landing-zone-availability.md)
15. [036-computed-divert-routing.md](./036-computed-divert-routing.md)
16. [037-monte-carlo-uncertainty-modeling.md](./037-monte-carlo-uncertainty-modeling.md)
17. [038-bank-angle-and-dubins-path-optimization.md](./038-bank-angle-and-dubins-path-optimization.md)
18. [039-path-planning-model-gaps.md](./039-path-planning-model-gaps.md)
19. [040-sitl-adapter-contract-and-evidence-schema.md](./040-sitl-adapter-contract-and-evidence-schema.md)
20. [041-ardupilot-sitl-launch-and-mission-upload.md](./041-ardupilot-sitl-launch-and-mission-upload.md)
21. [042-sitl-telemetry-recorder-and-evidence-bundle.md](./042-sitl-telemetry-recorder-and-evidence-bundle.md)
22. [043-sitl-scenario-comparison-report.md](./043-sitl-scenario-comparison-report.md)
23. [057-summary-output-format.md](./057-summary-output-format.md)
24. [055-geojson-kml-route-export.md](./055-geojson-kml-route-export.md)
25. [056-community-vehicle-profiles.md](./056-community-vehicle-profiles.md)
26. [052-real-world-data-fetch-scripts.md](./052-real-world-data-fetch-scripts.md)
27. [053-airspace-geofence-fetch-script.md](./053-airspace-geofence-fetch-script.md)
28. [059-infeasible-demo-mission.md](./059-infeasible-demo-mission.md)
29. [060-import-export-and-batch-workflows.md](./060-import-export-and-batch-workflows.md)
30. [047-stochastic-state-propagation.md](./047-stochastic-state-propagation.md)
31. [048-observation-model-and-twin-state.md](./048-observation-model-and-twin-state.md)
32. [049-stochastic-closed-loop-control.md](./049-stochastic-closed-loop-control.md)
33. [062-wind-corrected-divert-energy.md](./062-wind-corrected-divert-energy.md) *(divert estimate; landing-zone energy TAS-only remaining)*
34. [065-geofence-and-lz-in-stochastic.md](./065-geofence-and-lz-in-stochastic.md)
35. [073-preflight-checklist-output.md](./073-preflight-checklist-output.md)
36. [072-route-altitude-profile-report.md](./072-route-altitude-profile-report.md)
37. [074-energy-reserve-sensitivity.md](./074-energy-reserve-sensitivity.md)

### Planned

38. [075-minimum-battery-sizing.md](./075-minimum-battery-sizing.md)
39. [076-departure-window-finder.md](./076-departure-window-finder.md)
40. [077-mission-comparison-report.md](./077-mission-comparison-report.md)
41. [069-per-event-lost-link-policy-override.md](./069-per-event-lost-link-policy-override.md)
42. [066-stochastic-geojson-export.md](./066-stochastic-geojson-export.md)
43. [067-propagation-progress-feedback.md](./067-propagation-progress-feedback.md)
44. [068-divert-route-geojson-layer.md](./068-divert-route-geojson-layer.md)
45. [063-rth-reserve-check.md](./063-rth-reserve-check.md)
46. [061-3d-geofence-altitude-bounds.md](./061-3d-geofence-altitude-bounds.md)
47. [064-batch-scenario-and-propagate.md](./064-batch-scenario-and-propagate.md)
48. [044-geodesic-dubins-divert.md](./044-geodesic-dubins-divert.md)
49. [054-reference-inputs-for-calibration-and-import.md](./054-reference-inputs-for-calibration-and-import.md)
50. [045-px4-sitl-launch-and-mission-upload.md](./045-px4-sitl-launch-and-mission-upload.md)
51. [046-px4-sitl-telemetry-recorder-and-evidence-bundle.md](./046-px4-sitl-telemetry-recorder-and-evidence-bundle.md)
52. [058-notam-live-airspace-integration.md](./058-notam-live-airspace-integration.md)
53. [050-user-interfaces-and-service-adapters.md](./050-user-interfaces-and-service-adapters.md)
54. [070-operational-integration-seams.md](./070-operational-integration-seams.md)
55. [071-live-comms-remote-id-and-traffic-integrations.md](./071-live-comms-remote-id-and-traffic-integrations.md)

## Current Gaps

- No minimum battery sizing calculator (`size-battery` command): Ticket 075.
- No departure window finder for time-varying forecasts: Ticket 076.
- No side-by-side mission comparison (`diff` command): Ticket 077.
- Lost-link events share one global policy; no per-event override: Ticket 069.
- No GeoJSON/KML export for stochastic propagation results: Ticket 066.
- No progress feedback during long particle propagation runs: Ticket 067.
- No divert-route visual layer in scenario GeoJSON/KML export: Ticket 068.
- No RTH reserve check from every route point: Ticket 063.
- Geofence feasibility is 2D only (no altitude bounds): Ticket 061.
- Batch only supports estimate runs (no scenario or propagate): Ticket 064.
- Divert estimate now applies wind-triangle correction when wind provider is available; landing-zone reachability energy still uses TAS only (remaining scope of Ticket 062).
- No geodesic-aware Dubins divert path sampling: Ticket 044.
- No NOTAM/live airspace integration: Ticket 058.
- No reference inputs for calibration and import: Ticket 054.
- No PX4 SITL adapter: Tickets 045 (launch/upload) and 046 (telemetry/evidence).
- No REST API or UI: Ticket 050.
- No live comms, UTM/U-space, Remote ID, or traffic integrations: Tickets 070
  and 071.
- No real-world calibration pipeline: Tickets 080–084.

## Validation and Calibration Track

1. [080-flight-log-ingestion-and-trace-normalization.md](./080-flight-log-ingestion-and-trace-normalization.md)
2. [081-flight-phase-segmentation.md](./081-flight-phase-segmentation.md)
3. [082-predicted-vs-observed-validation-metrics.md](./082-predicted-vs-observed-validation-metrics.md)
4. [083-calibration-profile-data-and-fitting.md](./083-calibration-profile-data-and-fitting.md)
5. [084-holdout-validation-reports.md](./084-holdout-validation-reports.md)

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
