# Roadmap

This roadmap tracks bvlos-sim from the current deterministic validation engine
toward a broader BVLOS simulation platform.

## Current Status

The current codebase implements Phases 1 through 4.10, plus Tickets 032, 033,
034, 035, 036, 037, 038, 039, and 040:

- estimator hardening
- static feasibility checks
- scenario runner and contingency policy outcomes
- fidelity v2 trajectory and wind features
- terrain-referenced altitude execution
- continuous spatiotemporal wind grid
- resource and communication-link feasibility abstractions
- dynamic landing-zone availability via scenario events
- computed divert route estimates on policy outcomes
- Monte Carlo uncertainty analysis via `uncertainty.v1` YAML and `sample` CLI command
- Dubins path solver and bank-angle-constrained divert distance
- fidelity v2 tangent-point offset subtraction, 3D slant path for vertical legs, and Dubins divert planar limit warning
- SITL adapter contract and `sitl-evidence.v1` evidence schema

The test suite currently passes with 435 tests.

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
- deterministic resource-system feasibility for onboard battery, external power, and hybrid power configurations
- deterministic communication-link feasibility for mission and scenario link systems
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
- observe, lost-link, wind-change, and landing-zone-unavailable events
- assertion outcomes: `passed`, `failed`, `skipped`, `unsupported`
- lost-link policy outcomes for `rtl`, `land`, `loiter`, and `divert`
- computed divert route estimates (`DivertRouteEstimate`) on `divert` policy outcomes: geodesic distance, TAS transit time, cruise-power energy, reserve after divert, and feasibility flag
- `policy_action_eq` assertions

Uncertainty modeling:

- `uncertainty.v1` YAML input schema with `normal` and `uniform` distributions
- seeded Monte Carlo sampling over wind, cruise speed, cruise power, and battery capacity
- `run_monte_carlo` Python API wrapping the deterministic estimator
- `sample` CLI command for uncertainty execution
- `uncertainty-report.v1` JSON envelope with summary statistics (mean, std, min, p5, p50, p95, max) and deterministic baseline
- Markdown rendering for uncertainty reports

Interfaces and contracts:

- `estimate` CLI command
- `scenario` CLI command
- `sample` CLI command
- `sitl` CLI command for contract-only SITL evidence bundles
- canonical estimator JSON envelope (`estimator-envelope.v5`)
- canonical scenario JSON envelope (`scenario-report.v2`)
- canonical uncertainty JSON envelope (`uncertainty-report.v1`)
- canonical SITL evidence bundle (`sitl-evidence.v1`)
- Markdown rendering for estimator, scenario, and uncertainty reports
- golden fixture regression tests

## Known Limitations

Estimator limitations:

- no known path-planning model gaps remaining after Ticket 039

Scenario limitations:

- divert Dubins path uses a planar East-North approximation; a `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning is emitted when geodesic divert distance exceeds 50 km; not accurate for routes spanning hundreds of kilometres — Ticket 044

Platform limitations:

- no live ArduPilot SITL adapter yet; Tickets 041-043 build on the Ticket 040
  evidence schema and no-op adapter boundary
- no PX4 SITL adapter yet; Tickets 045 (launch/upload) and 046 (telemetry/evidence)
- no REST API; Ticket 050
- no web UI; Ticket 050
- no live comms, UTM/U-space, Remote ID, or traffic integrations; Tickets 070
  and 071
- no batch import/export workflows; Ticket 060
- no real-world calibration pipeline; Tickets 080-084

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

### Phase 4.5: Environmental Model Extensions

Status: implemented.

Delivered:

- Ticket 032: terrain-referenced altitude execution
- Ticket 033: continuous spatiotemporal wind grid
- mission YAML asset integration for terrain and wind-grid files
- terrain and wind examples
- CLI, envelope, Markdown, and fixture coverage

Exit criterion: terrain and wind-grid inputs can be used through the same
mission YAML and `estimate` command path as existing deterministic features.

### Phase 4.6: Resource and Link Feasibility

Status: implemented.

Scope:

- Ticket 034: resource and link feasibility abstractions — implemented
- generalized resource systems for onboard battery, external/tethered or
  optical-fiber power, hybrid power, and future resource-type extension points
- generalized communication link systems for direct, mesh, cellular, satellite,
  Starlink-class, and hybrid failover architectures
- integration with mission YAML, vehicle YAML, scenario YAML, existing
  feasibility reports, scenario assertions, and later live adapter replay
  artifacts

Exit criterion: energy/resource and communication-link feasibility can be
modeled through shared deterministic abstractions instead of one-off
battery-only or lost-link-only fields.

### Phase 4.7: Scenario Contingency Model Gaps

Status: implemented.

Scope:

- Ticket 035: dynamic landing-zone availability — implemented
- Ticket 036: computed divert routing — implemented
- integration with scenario YAML, mission assets, terrain, wind, geofences,
  landing zones, resource systems, link systems, and existing scenario reports

Exit criterion: contingency outcomes can use the same configured environment
and feasibility features as baseline mission estimation.

### Phase 4.8: Uncertainty Modeling

Status: implemented.

Scope:

- Ticket 037: Monte Carlo uncertainty modeling — implemented
- `uncertainty.v1` YAML-configured uncertainty inputs
- explicit opt-in `sample` CLI command
- `uncertainty-report.v1` JSON envelope and Markdown rendering preserving deterministic baseline output

Exit criterion: uncertainty analysis composes with existing mission, vehicle,
terrain, wind, geofence, landing-zone, resource, link, energy, and scenario
behavior without changing deterministic defaults.

### Phase 4.9: Bank-Angle Model and Dubins Path Optimization

Status: implemented.

Scope:

- Ticket 038: bank-angle model and Dubins path optimization

Delivered:

- `estimator.math.dubins` Dubins path-to-point solver (RS and LS path types)
- divert route estimates use Dubins path distance (bank-angle-constrained arc +
  straight) when entry heading and `vehicle.performance.turn_radius_m` are
  available; falls back to straight-line geodesic otherwise
- fidelity v2 turn arc confirmed as the exact Dubins solution for a
  same-position heading change (`turn_radius_m * |Δθ|`); no change to v2 math
- entry heading extracted from the last completed leg's `ground_track_deg` at
  the action timeline index

Exit criterion: horizontal path planning accounts for bank-angle constraints
and heading continuity across transit, turn, and divert segments without
changing fidelity v1 behavior or existing public result field names.

### Phase 4.10: Path-Planning Model Gaps

Status: implemented.

Scope:

- Ticket 039: path-planning model gaps

Delivered:

- fidelity v2 transit legs adjacent to TURN_ARC legs subtract the
  tangent-point offset (`turn_radius_m * tan(|Δθ|/2)`) from `path_distance_m`;
  offsets clamped to zero; total path distance now matches the true Dubins-path
  length through all waypoints
- takeoff and landing-transit legs report `path_distance_m = vertical_distance_m`
  (3D slant path for purely vertical legs) in all fidelity modes
- `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning added to
  `DivertRouteEstimate.warnings` when geodesic divert distance exceeds 50 km

Exit criterion: fidelity v2 total path distance equals the sum of
offset-adjusted transit legs plus turn arc lengths; takeoff and land legs
report correct 3D slant path distance; a diagnostic warning is emitted when
Dubins divert distance exceeds the planar approximation accuracy limit.

### Phase 4.11: Geodesic Dubins Divert Path

Status: planned.

Scope:

- Ticket 044: geodesic Dubins divert path
- replace the planar East-North Dubins solver with a geodesic formulation
  accurate for divert distances up to hundreds of kilometres
- remove or retire the `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning once
  the geodesic solver is operative for all distances

Exit criterion: divert distance is accurate within 0.5 % of the true Dubins
path length on the WGS-84 ellipsoid for routes up to 500 km; the planar limit
warning is no longer emitted for correctly handled distances.

### Phase 5: SITL Integration

Status: partially implemented.

Prerequisites:

- Ticket 034: Resource and Link Feasibility Abstractions — implemented
- Ticket 035: Dynamic Landing-Zone Availability — implemented
- Ticket 036: Computed Divert Routing — implemented
- Ticket 037: Monte Carlo Uncertainty Modeling — implemented

Scope:

- Ticket 040: SITL adapter contract and evidence schema — implemented
- Ticket 041: ArduPilot SITL launch and mission upload
- Ticket 042: SITL telemetry recorder and evidence bundle
- Ticket 043: SITL scenario comparison report
- Ticket 045: PX4 SITL launch and mission upload
- Ticket 046: PX4 SITL telemetry recorder and evidence bundle
- adapter-local ArduPilot and MAVLink dependencies that stay outside core
  estimator/scenario execution
- adapter-local PX4 dependencies that stay outside core estimator/scenario
  execution
- comparison against existing deterministic `scenario` outputs

Exit criterion: a scenario can be executed against supported SITL adapters with
recorded evidence while preserving the deterministic core execution path.

### Phase 6: Product Surfaces

Status: planned.

Scope:

- REST API around estimator and scenario execution
- web map UI for route, phases, warnings, failures, and timeline playback
- consistent JSON and Markdown report outputs
- optional PDF/report export after report contracts stabilize
- shared execution path with `estimate` and `scenario`

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
- batch manifests referencing existing mission, vehicle, scenario, terrain,
  wind, geofence, and landing-zone files

Exit criterion: teams can import external plans, run batches, and compare
outputs efficiently.

### Phase 8: Operational Integration

Status: planned.

Scope:

- UTM/U-space integration seams
- live comms, Remote ID, and traffic-observation seams
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
