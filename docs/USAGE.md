# Usage

This guide covers the supported CLI and Python API workflows for bvlos-sim.

## Prerequisites

- Python 3.12+
- Dependencies installed with `uv`

```bash
uv sync
```

Verify the CLI:

```bash
uv run bvlos-sim --help
```

## CLI Commands

bvlos-sim exposes five commands:

- `estimate`: run deterministic mission estimation and static feasibility checks
- `scenario`: run deterministic scenario events and assertions
- `sample`: run seeded Monte Carlo uncertainty sampling
- `sitl`: build a contract-only or live SITL evidence bundle from an existing scenario
- `compare`: compare a SITL evidence bundle against deterministic scenario expectations

Mission-scoped functionality is exposed through `estimate` by mission and
vehicle YAML: fidelity settings, terrain, wind grids, geofences, landing zones,
resource systems, communication links, energy feasibility, and route geometry.
Scenario events, uncertainty sampling, and SITL evidence use `scenario`,
`sample`, and `sitl` because they require separate versioned input contracts.
SITL comparison reports are exposed through `compare` so evidence review has a
dedicated command with JSON, Markdown, and `--output` support.

Command help:

```bash
uv run bvlos-sim estimate --help
uv run bvlos-sim scenario --help
uv run bvlos-sim sample --help
uv run bvlos-sim sitl --help
uv run bvlos-sim compare --help
```

## Mission Estimation

Run the example mission:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml
```

By default, the command writes canonical JSON to stdout.

Write JSON to a file:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --output /tmp/bvlos-report.json
```

Write Markdown:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format markdown \
  --output /tmp/bvlos-report.md
```

### Estimator Exit Codes

- `0`: success
- `10`: infeasible
- `11`: invalid input
- `12`: unsupported input
- `13`: internal error

## Scenario Execution

Run the example scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml
```

Run the fidelity v2 scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_v2_scenario.yaml
```

Run the integrated scenario that combines fidelity v2, terrain, wind-grid,
geofence, landing-zone, energy, and lost-link policy checks:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml
```

Run the integrated resource/link scenario:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_resource_link_scenario.yaml
```

Write Markdown:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format markdown \
  --output /tmp/scenario-report.md
```

### Scenario Exit Codes

- `0`: scenario passed
- `10`: scenario failed
- `11`: invalid input
- `13`: internal error

Skipped or unsupported assertions do not fail the scenario unless another
assertion fails.

## Monte Carlo Sampling

The `sample` command runs a seeded uncertainty plan and emits
`uncertainty-report.v1`. Use it when wind, speed, power, or other configured
inputs need distribution bounds rather than a single deterministic estimate.

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format json \
  --output /tmp/uncertainty.json
```

The `seed` in the uncertainty YAML makes repeated runs reproducible for the same
sample count and distributions. `feasibility_rate` is the fraction of completed
samples that remained feasible; values below the team's go/no-go threshold
should be treated as operational risk, even when the deterministic estimate
passes. Percentile fields such as `p95` describe tail behavior: for
reserve-at-landing, low-end percentiles are usually the operational concern; for
time or energy use, high-end percentiles show the conservative planning bound.

### Sample Exit Codes

- `0`: report written
- `11`: invalid input
- `13`: internal error

## SITL Evidence Contract

The `sitl` command reuses an existing `scenario.v1` file, runs the deterministic
scenario output as expected behavior, and emits a `sitl-evidence.v1` bundle.
By default it is contract-only. Add `--live` to connect to a running ArduPilot
SITL instance, upload the mission, record telemetry, and emit a completed
evidence bundle.

### Contract-Only Evidence

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml \
  --format json \
  --output /tmp/sitl-evidence.json
```

Write a Markdown evidence summary:

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml \
  --format markdown \
  --output /tmp/sitl-evidence.md
```

The no-op contract adapter writes `status: contract_only`, includes mission,
vehicle, scenario, and loaded asset references, embeds the deterministic
scenario report, and leaves telemetry and command-log artifact lists empty for
live adapters to populate.

### Live SITL Evidence

For a running ArduPilot SITL endpoint, `--live` requires an artifact directory.
The directory is created if it does not exist and receives `telemetry.json`,
`command_log.json`, `simulator_log.json`, and `adapter_log.json`.
Live recording emits progress lines to stderr for connection, mission upload,
telemetry recording, and evidence writing; stdout remains JSON-safe unless
`--output` is used.

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --live \
  --host 127.0.0.1 \
  --port 5760 \
  --artifact-dir /tmp/bvlos-artifacts \
  --telemetry-samples 20 \
  --telemetry-timeout-s 30.0 \
  --output /tmp/sitl-evidence.json
```

### SITL Comparison Reports

`sitl-comparison.v1` reports compare a `sitl-evidence.v1` bundle against the
embedded deterministic scenario report. Render one through `compare` from an
already-written evidence bundle:

```bash
uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --comparison-id pipeline-demo-sitl-comparison \
  --output /tmp/sitl-comparison.json
```

Write Markdown with the same entry point:

```bash
uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --format markdown \
  --output /tmp/sitl-comparison.md
```

`compare` exits `0` only when the summary is `passed`. A `drifted`, `failed`, or
`unsupported` summary exits `10` so shell and CI workflows do not accidentally
mark a drifted validation as passing. The JSON or Markdown report remains the
source of detail for which comparison dimension changed.

Python adapter APIs expose the same report construction:

```python
from adapters.sitl_comparison import build_sitl_comparison_report
from adapters.sitl_comparison import render_sitl_comparison_json
from adapters.sitl_comparison_markdown import render_sitl_comparison_markdown

report = build_sitl_comparison_report(
    comparison_id="pipeline-demo-sitl-comparison",
    bundle=evidence_bundle,
)
json_report = render_sitl_comparison_json(report)
markdown_report = render_sitl_comparison_markdown(report)
```

Reports include deterministic scenario assertions, mission item count,
telemetry record count, heartbeat presence, adapter lifecycle, simulator
lifecycle, and position proximity when `GLOBAL_POSITION_INT` telemetry is
available.

### SITL Exit Codes

- `0`: evidence bundle written
- `11`: invalid input
- `13`: internal or output-write error

### Scenario Events

Supported event kinds:

- `observe`: records that a timeline trigger fired
- `lost_link`: records link-loss timing and evaluates `lost_link_policy` when configured
- `wind_change`: changes the active wind from the trigger time onward

`wind_change` events accept either scalar wind:

```yaml
events:
  - event_id: wind-shift
    kind: wind_change
    trigger: at_elapsed_time
    trigger_elapsed_time_s: 120.0
    wind_east_mps: 4.0
    wind_north_mps: -1.0
```

or altitude-banded wind layers:

```yaml
events:
  - event_id: layered-wind
    kind: wind_change
    trigger: at_route_item
    trigger_route_item_id: wp1
    wind_layers:
      - altitude_m: 0.0
        wind_east_mps: 2.0
        wind_north_mps: 0.0
      - altitude_m: 120.0
        wind_east_mps: 5.0
        wind_north_mps: -1.0
```

## Input Files

Mission, vehicle, and scenario inputs may be:

- `.yaml`
- `.yml`
- `.json`

Unsupported extensions are rejected as invalid input.

Relative asset paths are resolved from the file that references them:

- mission assets are resolved from the mission file directory
- scenario `mission_file` and `vehicle_file` are resolved from the scenario file directory
- the `scenario` command loads mission-referenced terrain, wind-grid,
  geofence, and landing-zone assets before executing scenario events and
  assertions

## Resource and Link Feasibility

Explicit resource systems are configured on vehicle YAML:

```yaml
resource_systems:
  - resource_id: fiber-power-primary
    kind: external_power
    delivery: optical_fiber
    continuous_power_w: 2000.0
    max_tether_length_m: 2500.0
```

Communication-link systems are configured on mission YAML:

```yaml
link_systems:
  - link_id: mesh-primary
    kind: mesh_network
    max_range_m: 5000.0
  - link_id: starlink-backup
    kind: starlink
    priority: 1
    max_range_m: 100000.0
```

Scenario `initial_conditions.link_systems` replaces mission link systems for
that scenario run. Reports expose `result.resource` and `result.link`, and
scenario assertions can use `estimate.resource.is_feasible` and
`estimate.link.is_feasible`.

Existing battery-only vehicle files do not need changes. To make the legacy
battery budget explicit, add an `onboard_battery` resource system and omit
`battery_capacity_wh` / `reserve_percent` on the resource entry to reuse
`vehicle.energy` and the mission reserve policy.

## Estimator Options

Estimator options can be provided through:

- mission `estimation` YAML
- scenario `initial_conditions` YAML
- CLI flags for the `estimate` command
- Python `EstimationOptions`

Runtime options take precedence over mission `estimation` values.

### Fidelity Mode

Fidelity v1 is the default. Fidelity v2 adds turn-arc dynamics and fixed-wing
circular loiter.

CLI:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --fidelity v2
```

Mission YAML:

```yaml
estimation:
  fidelity: v2
```

Scenario YAML:

```yaml
initial_conditions:
  fidelity: v2
```

### Constant Wind

Mission YAML:

```yaml
estimation:
  wind_east_mps: 2.0
  wind_north_mps: -1.0
```

Scenario YAML:

```yaml
initial_conditions:
  wind_east_mps: 2.0
  wind_north_mps: -1.0
```

### Layered Wind

Layered wind uses altitude bands. The highest layer whose `altitude_m` is less
than or equal to the query altitude is used. Below all configured layers, the
lowest layer is used.

CLI:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --wind-layer "0:2.0:0.0" \
  --wind-layer "500:6.0:-1.0" \
  --wind-layer "1500:12.0:-3.0"
```

Mission YAML:

```yaml
estimation:
  wind_layers:
    - altitude_m: 0.0
      wind_east_mps: 2.0
      wind_north_mps: 0.0
    - altitude_m: 500.0
      wind_east_mps: 6.0
      wind_north_mps: -1.0
```

When `wind_layers` is present, scalar `wind_east_mps` and `wind_north_mps` are
accepted but ignored.

### Sub-Segment Sampling

Sub-segment sampling divides each transit leg into deterministic sub-segments
and samples wind at each midpoint.

CLI:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --max-segment-length-m 500
```

YAML:

```yaml
estimation:
  max_segment_length_m: 500.0
```

Values must be greater than zero.

### Combined CLI Options

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --fidelity v2 \
  --wind-layer "0:2.0:0.0" \
  --wind-layer "500:6.0:-1.0" \
  --max-segment-length-m 500
```

If runtime options are used while mission `wind_layers` are present and no
explicit wind provider is supplied, the estimator records that the mission
layers were ignored in result metadata.

### Terrain-Referenced Altitude

Route items with `altitude_reference: terrain` resolve their altitude above the
ground elevation at each waypoint position. This requires an offline elevation
grid asset file.

The grid format is a YAML or JSON file with these fields:

```yaml
origin_lat: 51.990
origin_lon: 3.990
step_lat_deg: 0.001
step_lon_deg: 0.001
elevations_m:
  - [10.0, 10.5, 11.0]
  - [10.2, 10.7, 11.1]
  - [10.3, 10.8, 11.2]
```

Reference the grid from the mission file:

```yaml
assets:
  terrain_file: terrain/flat_polder.yaml
```

Set the default altitude reference for the whole route:

```yaml
defaults:
  altitude_reference: terrain
```

Or per route item:

```yaml
route:
  - id: wp1
    action: waypoint
    lat: 52.001
    lon: 4.002
    altitude_m: 120.0
    altitude_reference: terrain
```

When terrain coverage is missing for a route-item position, the estimator
fails with structured diagnostics (`TERRAIN_COVERAGE_MISSING`). When no
terrain file is configured but a terrain reference is used, the estimator
fails with `UNSUPPORTED_ALTITUDE_REFERENCE_TERRAIN`.

See `examples/terrain/flat_polder.yaml` for a working example grid.
See `examples/missions/pipeline_demo_001_integrated.yaml` for a mission that
uses the terrain grid together with geofence, landing-zone, wind-grid, and
fidelity-v2 settings.

### Spatiotemporal Wind Grid

A spatiotemporal wind grid provides wind as a deterministic function of elapsed
time, altitude, latitude, and longitude. It uses quadrilinear interpolation
and clamps at domain boundaries.

The grid format is a YAML or JSON file:

```yaml
axes:
  time_s: [0.0, 600.0]
  altitude_m: [0.0, 200.0]
  lat: [51.990, 52.000, 52.010]
  lon: [3.990, 4.000, 4.010]
values:
  # values[time_idx][alt_idx][lat_idx][lon_idx] = [wind_east_mps, wind_north_mps]
  - - - [[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]
      - [[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]
      - [[2.0, 0.0], [2.0, 0.0], [2.0, 0.0]]
    - - [[3.0, -0.5], [3.0, -0.5], [3.0, -0.5]]
      - [[3.0, -0.5], [3.0, -0.5], [3.0, -0.5]]
      - [[3.0, -0.5], [3.0, -0.5], [3.0, -0.5]]
  - - - [[2.5, 0.0], [2.5, 0.0], [2.5, 0.0]]
      - [[2.5, 0.0], [2.5, 0.0], [2.5, 0.0]]
      - [[2.5, 0.0], [2.5, 0.0], [2.5, 0.0]]
    - - [[3.5, -0.5], [3.5, -0.5], [3.5, -0.5]]
      - [[3.5, -0.5], [3.5, -0.5], [3.5, -0.5]]
      - [[3.5, -0.5], [3.5, -0.5], [3.5, -0.5]]
```

Each axis must be strictly monotonically increasing with at least 2 entries.

Reference the grid from the mission file:

```yaml
assets:
  wind_grid_file: wind/pipeline_wind_grid.yaml
```

The CLI `--wind-layer` flags take precedence over `wind_grid_file` when both
are present. `wind_grid_file` takes precedence over `estimation.wind_layers`.
Scenario YAML initial wind settings take precedence over a mission wind grid;
when a scenario leaves initial wind unset, the `scenario` command can inherit
the mission's `assets.wind_grid_file`.

See `examples/wind/pipeline_wind_grid.yaml` for a working example grid.

## Flight Team Workflow

A typical evidence workflow keeps deterministic checks and live SITL artifacts
separate, then compares them explicitly:

```bash
# 1. Pre-flight estimate
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --output /tmp/estimate.json

# 2. Scenario assertions
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --output /tmp/scenario.json

# 3. Monte Carlo bounds
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --output /tmp/uncertainty.json

# 4. Live SITL validation
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --live --host 127.0.0.1 --port 5760 \
  --artifact-dir /tmp/bvlos-artifacts \
  --output /tmp/sitl-evidence.json

uv run bvlos-sim compare /tmp/sitl-evidence.json \
  --comparison-id pipeline-demo-live \
  --output /tmp/sitl-comparison.json
```

Interpret the workflow outputs in order. A successful `estimate` means the
static mission model is feasible under deterministic assumptions; an infeasible
estimate is a pre-flight stop. A `scenario` failure means an assertion or policy
expectation failed and should be resolved before live validation. In `sample`,
a low `feasibility_rate` or weak tail reserve means uncertainty has eroded the
deterministic margin. For `compare`, `passed` means live SITL artifacts agreed
with the embedded expectations for supported dimensions; `drifted` means review
the changed dimensions, usually mission upload count, telemetry presence,
adapter lifecycle, or position proximity, before treating the run as evidence.

## Python API

Use the package-root imports for stable caller code:

```python
from estimator import ConstantElevationProvider
from estimator import EstimationOptions
from estimator import FidelityMode
from estimator import GridTerrainProvider
from estimator import LayeredWindProvider
from estimator import SpatiotemporalWindProvider
from estimator import TerrainProvider
from estimator import WindLayer
from estimator import estimate_mission_distance_time
from estimator import run_scenario
```

Layered wind example:

```python
provider = LayeredWindProvider([
    WindLayer(altitude_m=0.0, wind_east_mps=2.0, wind_north_mps=0.0),
    WindLayer(altitude_m=500.0, wind_east_mps=6.0, wind_north_mps=-1.0),
])

result = estimate_mission_distance_time(
    mission,
    vehicle,
    wind_provider=provider,
    options=EstimationOptions(
        fidelity=FidelityMode.V2,
        max_segment_length_m=500.0,
    ),
)
```

Scenario execution can receive the same providers and static domain inputs as
mission estimation:

```python
result = run_scenario(
    scenario,
    mission,
    vehicle,
    wind_provider=wind_provider,
    terrain_provider=terrain_provider,
    geofences=geofences,
    landing_zones=landing_zones,
)
```

Terrain example:

```python
from adapters.terrain_grid import load_terrain_grid

terrain_provider, _ = load_terrain_grid(Path("terrain/flat_polder.yaml"))

result = estimate_mission_distance_time(
    mission,
    vehicle,
    terrain_provider=terrain_provider,
)
```

Or with a constant elevation (useful when ground elevation is uniform):

```python
provider = ConstantElevationProvider(elevation_m=10.0)

result = estimate_mission_distance_time(
    mission,
    vehicle,
    terrain_provider=provider,
)
```

Spatiotemporal wind grid example:

```python
from adapters.wind_grid import load_wind_grid

wind_provider, _ = load_wind_grid(Path("wind/pipeline_wind_grid.yaml"))

result = estimate_mission_distance_time(
    mission,
    vehicle,
    wind_provider=wind_provider,
)
```

Scenario example:

```python
result = run_scenario(scenario, mission, vehicle)
```

Monte Carlo uncertainty example:

```python
from estimator import run_monte_carlo
from schemas.uncertainty import UncertaintyPlan, UncertaintyParameters, NormalDistribution

plan = UncertaintyPlan(
    schema_version="uncertainty.v1",
    uncertainty_id="my-run",
    mission_file="mission.yaml",
    vehicle_file="vehicle.yaml",
    samples=200,
    seed=42,
    parameters=UncertaintyParameters(
        wind_east_mps=NormalDistribution(kind="normal", mean=0.0, std=2.0),
        wind_north_mps=NormalDistribution(kind="normal", mean=0.0, std=2.0),
    ),
)

mc_result = run_monte_carlo(plan, mission, vehicle)
print(mc_result.feasibility_rate)
print(mc_result.total_time_s.mean)
print(mc_result.total_time_s.p95)
```

Or via the `sample` CLI command:

```bash
bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml
bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml --format markdown
```

## Output Contracts

The estimator CLI emits `estimator-envelope.v5`.

The scenario CLI emits `scenario-report.v2`.

The sample CLI emits `uncertainty-report.v1`.

The SITL contract command emits `sitl-evidence.v1`.

The compare CLI and SITL comparison API emit `sitl-comparison.v1`.

Estimator and scenario JSON outputs are canonical, deterministic, and
regression-tested with golden fixtures. Markdown output is supported for
human-readable estimator, scenario, uncertainty, and SITL comparison reports.

## Verification

Run the linter:

```bash
uv run ruff check .
```

Run all tests:

```bash
uv run pytest
```

Run targeted CLI tests:

```bash
uv run pytest tests/test_cli.py tests/test_scenario_cli.py
```
