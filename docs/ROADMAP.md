# Roadmap

This roadmap tracks bvlos-sim from the current deterministic validation engine
toward a broader BVLOS simulation platform.

## Current Status

The current `v0.2.0` release implements Phases 1 through 4, plus Tickets 032 and 033:

- estimator hardening
- static feasibility checks
- scenario runner and contingency policy outcomes
- fidelity v2 trajectory and wind features
- terrain-referenced altitude execution
- continuous spatiotemporal wind grid

The test suite currently passes with 304 tests.

bvlos-sim remains an engineering validation tool. It is not a flight-safety
system, operational approval tool, or complete BVLOS compliance system.

## Implemented Capabilities

Estimator:

- deterministic mission distance and time estimation
- raising and non-raising Python APIs
- structured failures for invalid, unsupported, and infeasible cases
- partial-result handling
- fidelity v1 baseline behavior
- fidelity v2 turn arcs and fixed-wing circular loiter

Static feasibility:

- deterministic phase-based energy model
- reserve-at-landing output
- reserve threshold failures
- static GeoJSON geofence checks
- static GeoJSON landing-zone reachability checks

Wind and trajectory fidelity:

- `ConstantWindProvider`
- `LayeredWindProvider`
- `SpatiotemporalWindProvider` with quadrilinear interpolation (offline wind grid)
- optional transit sub-segment wind sampling
- wind-triangle correction for forward-flight transit
- station-keep loiter for hover-capable vehicles

Terrain:

- `TerrainProvider` interface
- `ConstantElevationProvider`
- `GridTerrainProvider` with bilinear interpolation (offline uniform elevation grid)
- terrain-referenced altitude resolution from mission asset file
- structured diagnostics for missing provider and missing coverage

Scenario runner:

- `scenario.v1` input schema
- deterministic timeline construction
- observe, lost-link, and wind-change events
- assertion outcomes: `passed`, `failed`, `skipped`, `unsupported`
- lost-link policy outcomes for `rtl`, `land`, `loiter`, and `divert`
- `policy_action_eq` assertions

Interfaces and contracts:

- `estimate` CLI command
- `scenario` CLI command
- canonical estimator JSON envelope (`estimator-envelope.v4`)
- canonical scenario JSON envelope (`scenario-report.v1`)
- Markdown rendering for estimator and scenario reports
- golden fixture regression tests

## Known Limitations

Estimator limitations:

- no Monte Carlo uncertainty model
- no bank-angle model or Dubins path optimization
- vertical-only movement does not add 3D slant path distance

Scenario limitations:

- `divert` policy outcomes record the target ID but do not compute a divert route
- no dynamic landing-zone availability model

Platform limitations:

- no SITL adapter yet
- no REST API
- no web UI
- no UTM/U-space integration
- no batch import/export workflows
- no real-world calibration pipeline

## Phase Plan

### Phase 1: Estimator Hardening

Status: implemented.

Delivered:

- estimator CLI
- canonical result envelope
- stable exit codes
- schema/versioning policy
- golden fixtures
- package boundary cleanup
- structured error-envelope behavior

Exit criterion: estimator runs from CLI with deterministic versioned output.

### Phase 2: Static Feasibility Layer

Status: implemented.

Delivered:

- deterministic energy feasibility
- reserve-at-landing checks
- geofence loading and route conflict checks
- landing-zone loading and reachability checks
- structured diagnostics for feasibility failures

Exit criterion: missions can be accepted or rejected by deterministic static
feasibility checks with machine-readable diagnostics.

### Phase 3: Scenario Runner and Contingency Policies

Status: implemented.

Delivered:

- scenario schema
- deterministic scenario runner
- timeline model
- event outcomes
- assertion outcomes
- scenario JSON and Markdown reports
- lost-link policy outcome model
- policy action assertions
- dynamic `wind_change` event injection

Exit criterion: repeatable scenario execution and machine-readable assertion
outcomes.

### Phase 4: Wind and Trajectory Fidelity v2

Status: implemented.

Delivered:

- layered wind provider
- sub-segment wind sampling
- fidelity mode selection
- turn-arc legs
- fixed-wing circular loiter
- metadata showing the fidelity mode used

Exit criterion: improved fidelity modes are available without breaking v1
contracts.

### Phase 5: SITL Integration

Status: planned.

Scope:

- ArduPilot SITL backend first
- MAVLink mission upload/start/monitor flow
- telemetry recorder
- policy command execution through MAVLink
- replay and evidence bundle generation

Exit criterion: a scenario can be executed against ArduPilot SITL with recorded
evidence.

### Phase 6: Product Surfaces

Status: planned.

Scope:

- REST API around estimator and scenario execution
- web map UI for route, phases, warnings, failures, and timeline playback
- consistent JSON and Markdown report outputs
- optional PDF/report export after report contracts stabilize

Exit criterion: users can run missions and scenarios from UI or API with
consistent outputs.

### Phase 7: Import, Export, and Batch Workflows

Status: planned.

Scope:

- QGroundControl `.plan` importer
- broader mission/action compatibility
- batch-run support
- performance profiling
- report comparison and diff tooling

Exit criterion: teams can import external plans, run batches, and compare
outputs efficiently.

### Phase 8: Operational Integration

Status: planned.

Scope:

- UTM/U-space integration seams
- operational intent and conformance check interfaces
- schema migration guidance
- reproducibility and evidence standards

Exit criterion: outputs are operationally integrable, reproducible, and
governance-ready.

## Real-World Validation Track

This track is separate from platform surface area. It improves model credibility
through observed flight data.

Planned work:

- flight log ingestion
- trace normalization
- flight phase segmentation
- predicted-vs-observed metrics
- calibration profile fitting
- holdout validation reports

SITL is not a substitute for real-world validation. SITL checks behavioral
consistency; real logs calibrate and validate model assumptions.

## Ticket Backlog

The detailed execution backlog is in [tickets/README.md](./tickets/README.md).
