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
- contract-only SITL evidence bundles through the `sitl` CLI command
- canonical JSON envelopes and optional Markdown reports
- CLI commands for estimator, scenario, uncertainty, and SITL contract workflows
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

- `mission.v5`: route, planned home, defaults, constraints, assets, policy
  references, link systems, and persisted estimator settings
- `vehicle.v3`: vehicle class, mass, performance, energy, resource systems,
  failsafe, capabilities, SITL metadata, and free-form notes
- `scenario.v1`: referenced mission and vehicle files, initial conditions,
  events, assertions, and metadata
- `geofence-geojson.v1`: static GeoJSON geofences
- `landing-zone-geojson.v1`: static GeoJSON landing zones

Mission, vehicle, and scenario files may be authored as YAML or JSON.

## Outputs

Current output contracts:

- `estimator-envelope.v5`: canonical estimator JSON envelope
- `scenario-report.v2`: canonical scenario JSON envelope
- `uncertainty-report.v1`: canonical uncertainty JSON envelope
- `sitl-evidence.v1`: canonical SITL evidence bundle
- Markdown reports for estimator and scenario outputs

JSON rendering is deterministic and sorted, and representative outputs are
covered by golden fixture tests.

## Architecture

The codebase is intentionally split by responsibility:

```text
adapters/
  CLI commands, file loading, envelope construction, Markdown rendering

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

Known limitations are deliberate for the current release:

- no live SITL integration yet; the evidence contract and no-op adapter
  boundary are implemented, with ArduPilot live execution tracked by Tickets
  041-043
- no PX4 SITL adapter yet; Ticket 045
- no REST API or UI; Ticket 050
- no batch import/export workflows or report diff tooling; Ticket 060
- long-distance Dubins divert still uses a planar approximation pending a
  geodesic solver; Ticket 044
- no live comms, UTM, Remote ID, or traffic integrations; Tickets 070 and 071
- no real-world calibration pipeline; Tickets 080-084

See [ROADMAP.md](./ROADMAP.md) for planned expansion.

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

The next major project area is live SITL integration behind the existing
evidence contract, starting with ArduPilot and tracking PX4 as a separate
adapter ticket. The longer-term roadmap includes API/UI surfaces,
import/export workflows, batch operations, operational integration, and
real-world validation and calibration from flight logs.

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
