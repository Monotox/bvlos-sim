# Roadmap

This roadmap tracks bvlos-sim from the current deterministic validation engine
toward a broader BVLOS simulation platform.

## Current Status

The current codebase implements 53 tickets across the deterministic,
stochastic, regulatory, and documentation tracks, including all core estimator,
feasibility, scenario, SITL, stochastic, output-format, and batch capabilities:

- estimator hardening, static feasibility checks, and scenario runner (Tickets 001–021)
- fidelity v2 trajectory, wind, terrain, resource, link, and Dubins divert (Tickets 030–039)
- SITL adapter contract, ArduPilot adapter, telemetry recording, and comparison reports (Tickets 040–043)
- stochastic state propagation, twin-state EKF observation model, and closed-loop tracking controller (Tickets 047–049)
- real-world data fetch scripts and pre-fetched Alpine demo (Tickets 052–053)
- GeoJSON/KML route exports, community vehicle profiles, and `--format summary` (Tickets 055–057)
- deliberately infeasible demo, QGC import, batch estimates, and `--format csv` (Tickets 059–060)
- 3D geofence altitude bounds, wind-corrected divert energy, and stochastic spatial infeasibility tracking (Tickets 061, 062, 065)
- `--format checklist`, `--format profile`, energy reserve sensitivity, and `size-battery` command (Tickets 072–075)

The test suite currently passes with 1116 tests and 9 skipped live or
environment-dependent tests.

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
- static GeoJSON geofence checks with optional AMSL altitude bounds
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

- `uncertainty.v2` YAML input schema; wind components accept normal or uniform
  distributions, while positive physical quantities require bounded positive
  uniform distributions
- seeded Monte Carlo sampling over wind, cruise speed, cruise power, and battery capacity
- `run_monte_carlo` Python API wrapping the deterministic estimator
- `sample` CLI command for uncertainty execution
- `uncertainty-report.v2` diagnostic JSON envelope with conditional summary
  statistics, complete sample accounting, and deterministic baseline
- Markdown rendering for uncertainty reports

Stochastic propagation:

- diagnostic open-loop sampled-parameter timelines, with per-sample routes
- twin true/estimated particle state via EKF predict/update cycle
- synthetic GPS and battery-meter sensor noise models (`SensorProfile`)
- process-wind and `ControllerProfile` propagation fail closed pending validated
  guidance and energy models
- `propagate` CLI command and `stochastic.v2` input schema
- `stochastic-envelope.v2` output contract with explicitly conditional
  timelines/distributions and `modeled_constraint_pass_rate`; no operational
  feasibility claim

Interfaces and contracts:

- `estimate` CLI command
- `scenario` CLI command
- `sample` CLI command
- `propagate` CLI command
- `sitl` CLI command for contract-only SITL evidence bundles
- canonical estimator JSON envelope (`estimator-envelope.v9`)
- canonical scenario JSON envelope (`scenario-report.v3`)
- canonical diagnostic uncertainty JSON envelope (`uncertainty-report.v2`)
- canonical diagnostic stochastic envelope (`stochastic-envelope.v2`)
- canonical SITL evidence bundle (`sitl-evidence.v1`)
- canonical SITL comparison report (`sitl-comparison.v1`)
- renderer-independent, fail-closed operational readiness for `estimate`,
  `scenario`, and `batch`, with an explicit `--engineering-only` opt-out
- ArduPilot SITL telemetry artifact recorder for completed evidence bundles
- SITL comparison report JSON and Markdown rendering through `compare` and
  adapter APIs
- Markdown rendering for estimator, scenario, and uncertainty reports
- one-line summary rendering for estimator, scenario, uncertainty, and stochastic reports
- GeoJSON and KML route export with per-leg energy-margin colouring, landing-zone reachability markers, and geofence conflict flags
- community vehicle profiles in `examples/vehicles/community/` for DJI Matrice 300 RTK, Wingtra One Gen II, QS Trinity F90+, Autel EVO Max 4T, and generic survey hexacopter
- `fetch_wind.py` (Open-Meteo archive/forecast), `fetch_terrain.py` (SRTM via `srtm.py`), and `fetch_landing_zones.py` (Overpass API) scripts with pre-fetched Alpine demo in `examples/real_world/`
- golden fixture regression tests

## Known Limitations

Estimator limitations:

- no known path-planning model gaps remaining after Ticket 044

Scenario limitations:

- no known scenario path-planning model gaps remaining after Ticket 044

Platform limitations:

- ArduPilot SITL connect/upload, telemetry evidence, and comparison reporting
  are implemented through Tickets 041-043
- no PX4 SITL adapter yet; Tickets 045 (launch/upload) and 046 (telemetry/evidence)
- no REST API; Ticket 050
- no web UI; Ticket 050
- no reference inputs for calibration and import; Ticket 054
- no NOTAM/live airspace integration; Ticket 058
- no live comms, UTM/U-space, Remote ID, or traffic integrations; Tickets 070
  and 071
- no bundled qualification corpus or aircraft-specific held-out acceptance;
  controller-log ingestion and calibration exist, but operators must supply and
  govern representative validation flights

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
- geofence loading and route conflict checks with optional altitude bounds
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
- `uncertainty.v2` YAML-configured diagnostic uncertainty inputs
- explicit opt-in `sample` CLI command
- `uncertainty-report.v2` JSON envelope and Markdown rendering preserving the
  deterministic baseline and explicit conditional/diagnostic semantics

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
- the original same-position turn placeholder was retained in this phase and
  later superseded by connected tangent fillets in Phase 4.10
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

- fidelity v2 replaces each feasible corner with a connected circular fillet;
  entry/exit points are tangent to the adjacent geodesic tracks, transit legs
  end at those points, and the arc has sampled non-zero displacement
- corners whose tangent offsets do not fit both adjacent legs fail with
  `INVALID_GEOMETRY` instead of clamping an invalid path to zero
- takeoff and landing-transit legs report `path_distance_m = vertical_distance_m`
  (3D slant path for purely vertical legs) in all fidelity modes
- `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning added as an interim
  diagnostic before Ticket 044 retired the warning emission

Exit criterion: fidelity v2 total path distance is the sum of connected,
geodesically recomputed transit portions and circular fillets; takeoff and land
legs report correct 3D slant path distance.

### Phase 4.11: Geodesic Dubins Divert Path

Status: implemented.

Scope:

- Ticket 044: geodesic Dubins divert path
- replaced the single-point planar Dubins target projection with geodesic-aware
  target geometry boundary sampling
- retired the `DUBINS_DIVERT_PLANAR_APPROXIMATION_LIMIT` warning emission

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
- Ticket 041: ArduPilot SITL launch and mission upload - implemented
- Ticket 042: SITL telemetry recorder and evidence bundle - implemented
- Ticket 043: SITL scenario comparison report - implemented
- Ticket 045: PX4 SITL launch and mission upload
- Ticket 046: PX4 SITL telemetry recorder and evidence bundle
- adapter-local ArduPilot and MAVLink dependencies that stay outside core
  estimator/scenario execution
- adapter-local PX4 dependencies that stay outside core estimator/scenario
  execution
- comparison against existing deterministic `scenario` outputs

Exit criterion: a scenario can be executed against supported SITL adapters with
recorded evidence and compared against deterministic scenario expectations
while preserving the deterministic core execution path.

### Phase 4.12: Real-World Data and Developer Experience

Status: partially implemented.
Done: Tickets 052, 053, 055, 056, and 057.
Planned: Tickets 054 and 058.

Scope:

- Ticket 052: real-world data fetch scripts — `fetch_wind.py` (Open-Meteo
  forecast with `--departure-time`), `fetch_terrain.py` (SRTM via `elevation`
  package), `fetch_landing_zones.py` (Overpass API); alpine demo example using
  pre-fetched real assets
- Ticket 053: airspace geofence fetch script — implemented with
  `fetch_geofences.py` via OpenAIP API key or keyless Overpass fallback;
  completes the static real-world asset set started in Ticket 052
- Ticket 054: reference inputs for calibration and import design — PX4 ULog
  flight logs and QGC `.plan` files committed to `reference/` with field-mapping
  design notes feeding Tickets 060 and 080
- Ticket 055: GeoJSON / KML route export — implemented with `--format geojson` and
  `--format kml` on `estimate` and `scenario` commands; legs coloured by energy
  margin; landing zones and geofence polygons as separate feature layers;
  opens directly in Google Earth and QGC
- Ticket 056: community vehicle profiles — implemented with five manufacturer-derived YAML
  profiles (DJI Matrice 300 RTK, Wingtra One Gen II, Quantum-Systems Trinity
  F90+, Autel EVO Max 4T, generic survey hexacopter) with provenance links
- Ticket 057: summary output format — implemented for `estimate` and
  `scenario` commands; single-line go/no-go digest with reserve %, flight time,
  contingency policy action, and first failing check; suitable for shell
  scripts and pre-flight checklists
- Ticket 058: NOTAM and live airspace integration — `fetch_notams.py` via FAA
  B4UFly API (US) and EUROCONTROL NOTAM service (Europe); active TFRs and
  temporary restrictions merged with static geofence output for day-of-flight
  feasibility checks

Exit criterion: a new user can fetch real terrain, wind, and airspace data for
any location in under five minutes, run a geographically realistic estimate,
and open the output in a map viewer without writing any code; community vehicle
profiles allow immediate use without placeholder values; summary output is
suitable for shell-script automation.

### Phase 6: Product Surfaces

Status: partially implemented.

Scope:

- REST API around estimator and scenario execution
- web map UI for route, phases, warnings, failures, and timeline playback
- consistent JSON and Markdown report outputs
- optional PDF/report export after report contracts stabilize
- shared execution path with `estimate` and `scenario`

Exit criterion: users can run missions and scenarios from UI or API with
consistent outputs.

### Phase 7: Stochastic State Propagation

Status: diagnostic open-loop subset implemented; process-wind and closed-loop
control disabled pending validated models.

Scope:

- Ticket 047: diagnostic stochastic parameter sweep — per-sample deterministic
  route/timing, conditional reserve timelines, `stochastic.v2` input schema,
  `propagate` CLI, and `stochastic-envelope.v2` output contract
- Ticket 048: closed-loop observation model and twin-state architecture —
  separate true state (physics) from estimated state (autopilot EKF belief);
  synthetic GPS, battery-meter, and airspeed sensor models; EKF predict/update
  cycle; policy decisions made from estimated state; `estimation_error_timeline`
  output; `SensorProfile` added to `VehicleProfile`
- Ticket 049: stochastic closed-loop control — disabled in `propagate` because
  the prototype omitted nominal along-track timing, vertical/loiter kinematics,
  and post-deviation spatial checks; `ControllerProfile` inputs fail closed
- Ticket 050: contingency trigger probability derived from the twin-state and
  cross-track timeline
- Ticket 051: SITL telemetry replay to condition the belief state
  retrospectively and validate the controller model against observed tracks

Current exit criterion: diagnostic outputs preserve per-sample routes and make
their modeled-pass conditioning explicit. Operational probability claims,
process-wind dynamics, and control feedback remain deferred until validated
against flight or higher-fidelity simulation evidence.

### Phase 8: Import, Export, and Batch Workflows

Status: partially implemented.
Done: QGroundControl `.plan` importer (`convert`) and batch estimates (`batch`).
Planned: Tickets 054 and 058.

Scope:

- QGroundControl `.plan` importer — implemented as `bvlos-sim convert`
- broader mission/action compatibility
- batch-run support — implemented as `bvlos-sim batch` with `batch.v1`
  estimate manifests
- performance profiling
- report comparison and diff tooling
- batch manifests referencing existing mission, vehicle, scenario, terrain,
  wind, geofence, and landing-zone files

Exit criterion: teams can import external plans, run batches, and compare
outputs efficiently.

### Phase 9: Operational Integration

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

- DataFlash text/binary and PX4 ULog ingestion (done, Tickets 080 and 102)
- trace normalization (done, Ticket 080)
- flight phase segmentation (done, Ticket 081)
- predicted-vs-observed metrics (done, Ticket 082)
- calibration profile fitting (done, Ticket 083)
- holdout validation reports

SITL is not a substitute for real-world validation. SITL checks behavioral
consistency; real logs calibrate and validate model assumptions.

## Ticket Backlog

The detailed execution backlog is in [tickets/README.md](./tickets/README.md).
