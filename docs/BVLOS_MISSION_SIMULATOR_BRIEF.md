# BVLOS Mission Simulator Brief

## Purpose

bvlos-sim is an open-source Python library and CLI for deterministic BVLOS
mission validation. It evaluates planned drone missions from versioned mission,
vehicle, environment, and scenario inputs, then emits reproducible JSON or
Markdown reports suitable for engineering review and regression testing.

The project is designed for teams that need repeatable preflight analysis,
scenario testing, and evidence that mission assumptions and contingency policies
were evaluated before integration with a real or simulated autopilot.

## Safety Scope

bvlos-sim is not a flight-safety system, an operational approval tool, or a
complete BVLOS compliance system. Its outputs are engineering evidence and
should be reviewed alongside operational procedures, aircraft-specific
validation, regulatory requirements, and real-world flight data.

## Current Capabilities

The current codebase includes:

- deterministic mission distance and time estimation
- fidelity v1 and fidelity v2 trajectory modes
- wind-triangle correction for forward-flight transit legs
- altitude-banded layered wind and optional sub-segment sampling
- offline spatiotemporal wind grids
- terrain-referenced altitude execution with offline uniform elevation grids
- deterministic energy feasibility with reserve-at-landing outputs
- resource-system feasibility for battery, external power, and hybrid power
- communication-link feasibility for mission and scenario link systems
- static GeoJSON geofence checks
- static GeoJSON landing-zone reachability checks
- dynamic landing-zone availability in scenario runs
- deterministic scenario execution with timeline events and assertions
- scenario `wind_change` events with scalar or altitude-banded wind payloads
- lost-link policy outcomes for `rtl`, `land`, `loiter`, and `divert`
- computed Dubins divert estimates for divert policy outcomes
- Monte Carlo uncertainty sampling through the `sample` CLI command
- stochastic state propagation through the `propagate` CLI command
- twin-state stochastic observation model with true and estimated particle state
- stochastic closed-loop tracking controller with proportional cross-track error feedback, path-length excess energy accounting, and cross-track timeline outputs
- contract-only SITL evidence bundles through the `sitl` CLI command
- ArduPilot SITL telemetry evidence and comparison reports through adapter APIs
  and the `sitl` / `compare` CLI commands
- canonical JSON envelopes and optional Markdown reports
- CLI commands for estimator, scenario, uncertainty, stochastic, and SITL
  contract workflows
- golden fixture tests for stable public output contracts

## Primary Workflows

### Mission Estimation

The `estimate` command loads a mission file and a vehicle profile, evaluates the
route and static feasibility layers, and emits an estimator envelope.

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml
```

Typical output includes:

- schema and tool version metadata
- deterministic provenance for loaded inputs
- diagnostics and structured failures
- route legs with distance, time, wind, and phase details
- mission totals
- energy feasibility and reserve margin
- resource and communication-link feasibility when configured
- geofence and landing-zone feasibility artifacts when configured

### Scenario Execution

The `scenario` command loads a scenario file, its referenced mission and vehicle
files, runs the deterministic scenario engine, and emits a scenario report.

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml
```

Typical output includes:

- deterministic timeline points
- event outcomes
- assertion results
- dynamic wind-change effects where configured
- lost-link policy outcomes where configured
- embedded estimator result

## Inputs

Current input contracts:

- `mission.v6`: route, planned home, defaults, constraints, assets, policy
  references, link systems, population grids, and persisted estimator settings
- `vehicle.v4`: vehicle class, mass, performance, energy, characteristic
  dimension, resource systems, failsafe, capabilities, SITL metadata, and
  free-form notes
- `scenario.v1`: referenced mission and vehicle files, initial conditions,
  events, assertions, and metadata
- `geofence-geojson.v1`: static GeoJSON geofences
- `landing-zone-geojson.v1`: static GeoJSON landing zones
- `population-grid.v1`: offline population-density grids for SORA iGRC pre-assessment

Mission, vehicle, and scenario files may be authored as YAML or JSON.

## Outputs

Current output contracts:

- `estimator-envelope.v6`: canonical estimator JSON envelope
- `scenario-report.v2`: canonical scenario JSON envelope
- `uncertainty-report.v1`: canonical uncertainty JSON envelope
- `stochastic-envelope.v1`: canonical stochastic propagation JSON envelope
- `sitl-evidence.v1`: canonical SITL evidence bundle
- `sitl-comparison.v1`: canonical SITL comparison report
- Markdown reports for estimator, scenario, uncertainty, stochastic, and SITL
  comparison outputs

JSON rendering is deterministic and sorted, and representative outputs are
covered by golden fixture tests.

## Architecture

The codebase is intentionally split by responsibility:

```text
adapters/
  CLI commands, file loading, envelope construction, Markdown rendering
adapters/sitl/
  ArduPilot SITL adapter, artifact recording, evidence building, comparison reports

schemas/
  Pydantic input models for mission, vehicle, and scenario files

estimator/core/
  Public enums, options, result models, constants, and typed errors

estimator/execution/
  Estimator orchestration, runtime context, route execution, static checks,
  scenario runner, and policy outcome evaluation

estimator/environment/
  Wind provider abstractions

estimator/math/
  Wind-triangle and turn-arc math helpers
```

The stable Python import surface is the package root:

```python
from estimator import estimate_mission_distance_time
from estimator import try_estimate_mission_distance_time
from estimator import run_scenario
```

Callers should not couple themselves to internal module layout unless they are
contributing to the project internals.

## Modeling Approach

The estimator is deterministic. It does not use randomness, network calls, or
real-time services during core execution.

Fidelity v1 provides the stable baseline:

- geodesic leg-to-leg transit
- constant or layered wind sampling
- station-keep loiter for hover-capable vehicles
- deterministic energy by phase
- static geofence and landing-zone checks

Fidelity v2 adds:

- turn-arc legs at waypoint heading changes
- fixed-wing circular loiter support
- optional sub-segment wind sampling for long transit legs

The scenario runner builds on estimator outputs. It constructs a deterministic
timeline, resolves events against that timeline, evaluates assertions, and
records policy outcomes. Wind-change events are resolved against timeline
triggers and applied through the estimator wind-provider contract. It does not
yet run a live autopilot or physics simulator.

## Current Limitations

Known gaps in the current release:

- no NOTAM or live airspace integration; Ticket 058
- no reference inputs for calibration and import; Ticket 054
- no PX4 SITL adapter; Tickets 045, 046
- no REST API or UI; Ticket 050
- no live comms, UTM/U-space, Remote ID, or traffic integrations; Tickets 070,
  071
- no real-world calibration pipeline from flight logs; Tickets 080–084

See [tickets/README.md](./tickets/README.md) for the full planned backlog.

## Target Users

bvlos-sim is intended for:

- drone software engineers validating mission logic
- researchers comparing deterministic mission assumptions
- operators preparing engineering evidence for review
- teams building CI checks around mission files and scenario files
- developers integrating later SITL, API, or UI layers

## Relationship To Existing Drone Tools

bvlos-sim complements, rather than replaces, existing tools:

- PX4 and ArduPilot provide autopilot firmware and SITL behavior.
- QGroundControl and Mission Planner provide mission authoring and upload.
- MAVSDK and pymavlink provide MAVLink integration.
- Gazebo, JSBSim, and similar tools provide physics or sensor simulation.
- UTM and conformance tools address operational ecosystem integration.

bvlos-sim focuses on deterministic mission validation, feasibility checks,
scenario assertions, and reproducible reporting.

## Development Direction

Fetch scripts for wind, terrain, landing zones, static airspace geofences, and population grids
are implemented (Tickets 052 and 053), with a single wrapper command for the
Ticket 052 assets (`fetch_all.py <lat> <lon>`) and a pre-fetched Alpine example
in `examples/real_world/`. Ticket 059 adds a deliberately infeasible demo, and
Ticket 060 adds QGC `.plan` conversion plus batch estimate manifests for CI and
multi-vehicle comparisons.

Tickets 047, 048, and 049 are implemented: `propagate` runs a time-stepped
particle propagator with twin true/estimated particle state, GPS and
battery-meter sensor noise models, an EKF predict/update cycle, and a
proportional cross-track tracking controller. The `estimation_error_timeline`
and `cross_track_timeline` outputs are populated when the vehicle profile
includes `sensors` and `controller` blocks; see
`examples/vehicles/quadplane_v1_ekf.yaml` for a working example.

Ticket 094 is implemented: `estimate --format ground-risk` computes a SORA
iGRC pre-assessment from an offline population-density grid and the vehicle
characteristic dimension. Ticket 095 is the next regulatory pre-assessment step,
adding air risk and SAIL.

Longer-term priorities are NOTAM/live airspace integration (Ticket 058), PX4 SITL adapter
(Tickets 045–046), API/UI surfaces (Ticket 050), operational integration
(Tickets 070–071), and real-world calibration from flight logs (Tickets 080–084).

The project should continue to prioritize:

- stable versioned contracts
- deterministic output
- explicit unsupported outcomes
- focused core interfaces
- adapter layers for CLI, files, reports, SITL, API, and UI surfaces

## Related Documents

- [USAGE.md](./USAGE.md): CLI and Python API usage
- [ROADMAP.md](./ROADMAP.md): implementation status and planned phases
- [VERSIONING_POLICY.md](./VERSIONING_POLICY.md): public contract rules
- [SITL_ADAPTER_CONTRACT.md](./SITL_ADAPTER_CONTRACT.md): SITL evidence and
  adapter boundary
- [ESTIMATOR_V1_FIELD_SEMANTICS.md](./ESTIMATOR_V1_FIELD_SEMANTICS.md): operative and non-operative fields
- [CODE_STYLE.md](./CODE_STYLE.md): contribution style and architecture rules
- [tickets/README.md](./tickets/README.md): execution backlog
