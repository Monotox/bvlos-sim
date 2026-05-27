# Usage

This guide covers the supported CLI and Python API workflows for bvlos-sim.

## Prerequisites

- Python 3.12+
- Dependencies installed with `uv`

```bash
uv sync
```

Mission, vehicle, scenario, uncertainty, and batch files may be `.yaml`,
`.yml`, or `.json`. Relative asset paths are resolved from the referencing
file's directory.

Verify the CLI:

```bash
uv run bvlos-sim --help
```

## CLI Commands

bvlos-sim exposes eight commands:

- `estimate`: run deterministic mission estimation and static feasibility checks
- `scenario`: run deterministic scenario events and assertions
- `convert`: convert a QGroundControl `.plan` file to a `mission.v5` YAML
- `batch`: run batch mission estimates from a manifest file
- `sample`: run seeded Monte Carlo uncertainty sampling
- `propagate`: run time-stepped stochastic particle propagation with EKF and tracking controller
- `sitl`: build a contract-only or live SITL evidence bundle from an existing scenario
- `compare`: compare a SITL evidence bundle against deterministic scenario expectations

| Command | Exit 0 | Exit 10 | Exit 11 | Exit 12 | Exit 13 |
|---------|--------|---------|---------|---------|---------|
| estimate | success | infeasible | invalid input | unsupported | internal error |
| scenario | passed | failed | invalid input | - | internal error |
| sample | success | - | invalid input | - | internal error |
| propagate | success | - | invalid input | - | internal error |
| sitl | success | - | invalid input | - | internal/write error |
| compare | passed | drifted/failed | invalid input | unsupported (contract-only) | internal/write error |
| convert | success | - | invalid input | - | internal error |
| batch | all feasible | any infeasible | invalid input/run | - | internal error |

Mission-scoped functionality is exposed through `estimate` by mission and
vehicle YAML: fidelity settings, terrain, wind grids, geofences, landing zones,
resource systems, communication links, energy feasibility, and route geometry.
Scenario events, uncertainty sampling, and SITL evidence use `scenario`,
`sample`, and `sitl` because they require separate versioned input contracts.
SITL comparison reports are exposed through `compare` so evidence review has a
dedicated command with JSON, Markdown, and `--output` support.
Plan conversion and multi-run CI workflows are exposed through `convert` and
`batch`.
For terse terminal output, `estimate`, `scenario`, `sample`, and `propagate`
support `--format summary`. `estimate` and `scenario` support `--format geojson`
and `--format kml` for map-ready route exports. `batch` supports `--format
geojson|kml` when used with `--output-dir` to write one map file per run.
`sitl` and `compare` remain JSON/Markdown only.

Command help:

```bash
uv run bvlos-sim estimate --help
uv run bvlos-sim scenario --help
uv run bvlos-sim convert --help
uv run bvlos-sim batch --help
uv run bvlos-sim sample --help
uv run bvlos-sim propagate --help
uv run bvlos-sim sitl --help
uv run bvlos-sim compare --help
```

## QGroundControl Plan Conversion

Convert QGroundControl `.plan` JSON into a starter `mission.v5` YAML:

```bash
uv run bvlos-sim convert examples/missions/pipeline_demo_001.plan \
  --output /tmp/pipeline_converted.yaml
```

The converter reads `plannedHomePosition`, mission `cruiseSpeed` and
`hoverSpeed`, and supported MAVLink mission items: takeoff, VTOL takeoff,
waypoint, loiter-time, RTL, land, and VTOL land. Unsupported commands and
ComplexItem entries are skipped with warnings to stderr so the rest of the
route can still be converted.

The output YAML sets `vehicle_profile` to the placeholder `FIXME-vehicle-profile`
and omits policy and asset references. Replace the placeholder with the real
vehicle profile id, review route altitudes and constraints, and add any
geofence, landing-zone, terrain, or wind-grid assets before treating the
converted mission as operational input.

## Batch Estimates

Run multiple estimate jobs from a `batch.v1` manifest:

```bash
uv run bvlos-sim batch examples/batch/demo_batch.yaml
```

Manifest files are YAML or JSON:

```yaml
format_version: "batch.v1"
runs:
  - id: alpine_standard
    mission: ../real_world/alpine_mission.yaml
    vehicle: ../real_world/quadplane_v1.yaml
  - id: alpine_infeasible
    mission: ../real_world/alpine_infeasible.yaml
    vehicle: ../real_world/quadplane_small_battery.yaml
```

Paths are resolved relative to the manifest file. The command always prints a
table with run id, status, reserve margin above or below threshold, and flight
time, followed by a feasible/infeasible/error count. Use `--output-dir DIR` to
write per-run output files for CI collection; `--format` controls those files
while the table stays on stdout. Supported per-run file formats:

- `--format json` — one `estimator-envelope.v5` JSON file per run (`.json`)
- `--format markdown` — one Markdown report per run (`.md`)
- `--format summary` — one one-line summary per run (`.txt`)
- `--format geojson` — one GeoJSON map export per run (`.geojson`) with the
  same route/landing-zone/geofence layers as `estimate --format geojson`
- `--format kml` — one KML map export per run (`.kml`)

Batch exits `0` only when all runs are feasible, `10` when any run is
infeasible and no run had an input error, `11` when any run cannot load its
inputs, and `13` for unexpected internal failures.

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

Write a one-line summary:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format summary
```

Example output:

```text
FEASIBLE   reserve 281.6 %   flight 2m 49s   warnings 4
```

The `warnings N` field appears when the estimate has advisory warnings
(see [Advisory Warning Codes](#advisory-warning-codes)).

Write GeoJSON route layers:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format geojson \
  --output /tmp/bvlos-route.geojson
```

Write KML route layers:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --format kml \
  --output /tmp/bvlos-route.kml
```

### Energy Reserve Explained

The `reserve` field in `--format summary` output is the margin above (positive) or
below (negative) the reserve threshold, as a percentage of the threshold:

```
reserve_margin_% = (reserve_at_landing_wh / reserve_threshold_wh - 1) × 100
```

The reserve threshold is set in Wh and derived from a percent of battery capacity:

```
reserve_threshold_wh = battery_capacity_wh × reserve_threshold_percent / 100
```

The percent used is `mission.constraints.min_landing_reserve_percent` when set;
otherwise it falls back to `vehicle.energy.reserve_percent_default`. Set one or
both to control how much energy must remain at landing for the mission to be
considered feasible.

```yaml
# mission.yaml
constraints:
  min_landing_reserve_percent: 25.0   # 25% of battery capacity must survive landing

# vehicle.yaml
energy:
  battery_capacity_wh: 900.0
  reserve_percent_default: 20.0       # used if mission doesn't override
```

A `reserve 281.6 %` summary means landing energy was 281.6% above the threshold
(i.e., 3.8× the required reserve remained). A `reserve −12.4 %` means landing
energy was 12.4% below the threshold and the mission is `INFEASIBLE`.

## Vehicle Profiles

Reference and community vehicle profiles live under `examples/vehicles/`.
The starter community set is in `examples/vehicles/community/`:

- `dji_matrice_300_rtk.yaml`
- `wingtra_one_gen2.yaml`
- `qs_trinity_f90_plus.yaml`
- `autel_evo_max_4t.yaml`
- `generic_survey_hexacopter.yaml`

Each profile includes manufacturer-derived or typical-class values plus
`metadata.source` and calibration notes. Before using a community profile with
an existing mission, update `mission.vehicle_profile` to match the profile's
`vehicle_id`; the CLI rejects mismatches to prevent accidental vehicle swaps.
Validate any community profile against observed flight logs before operational
use.

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

Write a one-line summary:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format summary
```

Example output:

```text
PASSED 3/3   reserve 281.6 %   flight 2m 49s   warnings 4
```

The `policy <ACTION>` field appears only when a lost-link event fires and a
policy action is selected (e.g. `policy DIVERT`, `policy RTL`). The `warnings N`
field appears only when the estimate has advisory warnings.

Write GeoJSON route layers from the scenario estimate:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format geojson \
  --output /tmp/scenario-route.geojson
```

Write KML route layers from the scenario estimate:

```bash
uv run bvlos-sim scenario \
  examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format kml \
  --output /tmp/scenario-route.kml
```

### Scenario Exit Codes

- `0`: scenario passed
- `10`: scenario failed
- `11`: invalid input
- `13`: internal error

Skipped or unsupported assertions do not fail the scenario unless another
assertion fails.

### Scenario Events

Supported event kinds:

- `observe`: records that a timeline trigger fired
- `lost_link`: records link-loss timing and evaluates `lost_link_policy` when configured
- `wind_change`: changes the active wind from the trigger time onward
- `landing_zone_unavailable`: marks one or more landing zones as unavailable from this point in the timeline onward

All events require a `trigger` field. Supported triggers:

| Trigger | Extra field required |
|---------|----------------------|
| `at_mission_start` | — |
| `at_route_item` | `trigger_route_item_id` |
| `at_elapsed_time` | `trigger_elapsed_time_s` |
| `at_mission_end` | — |

`landing_zone_unavailable` events require `unavailable_zone_ids` (a list of zone IDs from the
landing-zone GeoJSON). When a zone is marked unavailable, reachability is re-evaluated from
that route item onward. Any previously reachable zone that is now unavailable causes an
infeasibility if no other zone remains reachable:

```yaml
events:
  - event_id: lz-closed
    kind: landing_zone_unavailable
    trigger: at_route_item
    trigger_route_item_id: wp1
    unavailable_zone_ids:
      - demo_landing_zone_wp1
```

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

### Lost-Link Policy

The `lost_link_policy` block defines what the vehicle does when the `lost_link` event fires.
It can be set in the mission YAML (under `policy.lost_link_policy`) or overridden per scenario
in `initial_conditions.lost_link_policy`. Set `policy.lost_link_policy: standard_lost_link_v1`
in the mission to activate the default RTL-after-loiter policy.

Inline `lost_link_policy` fields:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `action` | string | required | Contingency action: `rtl`, `land`, `loiter`, or `divert` |
| `loiter_s` | float | `0.0` | Seconds to loiter at the link-loss point before acting |
| `divert_target_id` | string | `null` | Landing zone ID to divert to; required when `action` is `divert` |

Example — loiter 30 s then RTL:

```yaml
initial_conditions:
  lost_link_policy:
    action: rtl
    loiter_s: 30.0
```

Example — divert to a named landing zone immediately:

```yaml
initial_conditions:
  lost_link_policy:
    action: divert
    loiter_s: 0.0
    divert_target_id: demo_landing_zone_wp1
```

The divert estimate (Dubins path distance, transit time, reserve remaining) is included in the
`scenario-report.v2` envelope under each `event_outcome.policy_outcome.divert_estimate`.

### Scenario Assertions

Assertions run after the estimator completes and test fields on the result envelope or
policy outcomes. Unrecognised or skipped assertions do not fail the scenario; when any
assertions are `unsupported` (unrecognised `field_path` or unsupported kind), the
`--format summary` line includes `[N unsupported]` to alert operators.

| Kind | Required fields | Passes when |
|------|-----------------|-------------|
| `estimate_succeeds` | — | `estimate.status == "success"` |
| `estimate_fails` | — | `estimate.status != "success"` |
| `field_lt` | `field_path`, `expected` | field value `< expected` |
| `field_gt` | `field_path`, `expected` | field value `> expected` |
| `field_le` | `field_path`, `expected` | field value `<= expected` |
| `field_ge` | `field_path`, `expected` | field value `>= expected` |
| `field_eq` | `field_path`, `expected` | field value `== expected` (bool or float) |
| `policy_action_eq` | `event_id`, `expected` | lost-link policy action for the event equals `expected` |

`field_path` uses dot notation against the nested estimate result. All supported paths:

```
estimate.status                              # "success" | "infeasible" | "error"
estimate.total_time_s
estimate.total_horizontal_distance_m
estimate.total_vertical_distance_m
estimate.total_path_distance_m
estimate.totals_are_partial                  # true if estimate was cut short
estimate.energy.is_feasible
estimate.energy.total_energy_wh
estimate.energy.reserve_at_landing_wh
estimate.energy.reserve_at_landing_percent
estimate.energy.reserve_threshold_wh
estimate.energy.reserve_threshold_percent
estimate.geofence.is_feasible
estimate.landing_zone.is_feasible
estimate.resource.is_feasible
estimate.link.is_feasible
```

An assertion with an unrecognised `field_path` yields `unsupported` outcome; the
`unsupported_reason` field in the JSON result lists all valid paths.

Example assertions block:

```yaml
assertions:
  - assertion_id: estimate-succeeds
    kind: estimate_succeeds
  - assertion_id: reserve-margin-ok
    kind: field_gt
    field_path: estimate.energy.reserve_at_landing_wh
    expected: 100.0
  - assertion_id: policy-is-rtl
    kind: policy_action_eq
    event_id: link-lost
    expected: rtl
```

`expected` for `field_eq` on boolean fields can be written as `true`/`false` (unquoted YAML).

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

Write Markdown:

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format markdown \
  --output /tmp/uncertainty-report.md
```

Print a one-line summary:

```bash
uv run bvlos-sim sample \
  examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format summary
```

Example output: `feasible 100%   reserve p5 823.9 Wh   p50 858.2 Wh   p95 903.3 Wh   time p50 2m 50s   n=200`

The `seed` in the uncertainty YAML makes repeated runs reproducible for the same
sample count and distributions. `feasibility_rate` is the fraction of completed
samples that remained feasible; values below the team's go/no-go threshold
should be treated as operational risk, even when the deterministic estimate
passes. Percentile fields such as `p95` describe tail behavior: for
reserve-at-landing, low-end percentiles are usually the operational concern; for
time or energy use, high-end percentiles show the conservative planning bound.

### Uncertainty YAML reference

Five parameters can be sampled independently. Unset parameters hold their
deterministic value for every sample.

| Parameter | Overrides | Example range |
|-----------|-----------|---------------|
| `wind_east_mps` | wind East component (m/s) | `mean: 0.0, std: 2.0` |
| `wind_north_mps` | wind North component (m/s) | `mean: 0.0, std: 2.0` |
| `cruise_speed_mps` | `mission.defaults.cruise_speed_mps` | `low: 14.0, high: 22.0` |
| `cruise_power_w` | `vehicle.energy.cruise_power_w` | `mean: 450.0, std: 30.0` |
| `battery_capacity_wh` | `vehicle.energy.battery_capacity_wh` | `mean: 900.0, std: 25.0` |

Two distribution kinds are supported:

```yaml
# Normal (Gaussian) — fields: mean, std (must be > 0)
wind_east_mps:
  kind: normal
  mean: 0.0
  std: 2.0

# Uniform — fields: low (inclusive), high (exclusive)
cruise_speed_mps:
  kind: uniform
  low: 14.0
  high: 22.0
```

## Stochastic Propagation

The `propagate` command runs a time-stepped particle propagator over the full
mission timeline. Each particle carries independently sampled wind, cruise
speed, cruise power, and battery capacity. Per-step `p_reserve_violation`
tracks energy risk accumulation. Emits `stochastic-envelope.v1`.

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format json \
  --output /tmp/stochastic.json
```

Write Markdown:

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format markdown \
  --output /tmp/stochastic-report.md
```

Print a one-line summary:

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic.yaml \
  --format summary
```

Example output: `feasible 100%   reserve p5 822.2 Wh   p50 858.7 Wh   p95 909.1 Wh   time 2m 49s   n=100`

The `seed` in the stochastic YAML makes repeated runs reproducible for the
same sample count and parameters. `feasibility_rate` is the fraction of
particles that landed with sufficient reserve. `reserve_at_landing_wh` gives
distribution statistics (mean, std, p5, p50, p95) over particles.

Sample accounting in the result uses three-way partitioning:
`sample_count + failed_sample_count + spatial_infeasible_count == plan.samples`.
A `spatial_infeasible_count > 0` means some particles were rejected because the
route was geometrically infeasible for that sample — for example, a sampled
battery capacity too low to afford the divert reserve to any available landing
zone. These are counted as infeasible in `feasibility_rate`. When
`--format summary` is used, non-zero counts appear as extra fields:

```
feasible 0%   time 2m 49s   n=0   spatial_infeasible=6
```

If the mission has no geofence or landing-zone assets, `spatial_infeasible_count`
is always 0.

To activate the twin-state EKF and cross-track controller, the vehicle file
must include `sensors` and `controller` blocks. Without those blocks the
propagator runs in basic mode (energy-only, no twin-state tracking) and
`estimation_error_timeline` and `cross_track_timeline` are empty. An example
EKF-equipped vehicle is provided at
`examples/vehicles/quadplane_v1_ekf.yaml`:

```bash
uv run bvlos-sim propagate \
  examples/stochastic/pipeline_demo_001_stochastic_ekf.yaml \
  --format json \
  --output /tmp/stochastic-ekf.json
```

The `stochastic.v1` YAML format accepts the same five parameters as `uncertainty.v1`
(`wind_east_mps`, `wind_north_mps`, `cruise_speed_mps`, `cruise_power_w`,
`battery_capacity_wh`) with the same `normal`/`uniform` distribution syntax.
`wind_process_noise_std_mps` adds a per-step Gaussian perturbation to each
particle's wind so wind state drifts continuously during propagation rather than
staying fixed after initial sampling:

```yaml
schema_version: stochastic.v1
propagation_id: my-propagation
mission_file: path/to/mission.yaml
vehicle_file: path/to/vehicle.yaml
dt_s: 2.0                       # time step in seconds
samples: 100                    # number of particles (max 10 000)
seed: 42                        # fixed seed for reproducibility
wind_process_noise_std_mps: 0.5 # per-step wind drift std; set 0 to disable
parameters:
  wind_east_mps:
    kind: normal
    mean: 0.0
    std: 2.0
  wind_north_mps:
    kind: normal
    mean: 0.0
    std: 2.0
  cruise_speed_mps:             # optional — omit to hold at mission default
    kind: uniform
    low: 14.0
    high: 22.0
  cruise_power_w:
    kind: normal
    mean: 450.0
    std: 30.0
  battery_capacity_wh:
    kind: normal
    mean: 900.0
    std: 25.0
```

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

If `--comparison-id` is omitted, `compare` generates the identifier as
`<evidence_id>-comparison`.

`compare` requires a completed `sitl-evidence.v1` bundle (produced with
`sitl --live`). Comparing a contract-only bundle (produced without `--live`)
exits 12 with `"summary": "unsupported"` -- this is expected and means no live
artifacts are available to compare against.

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

`compare` exits `0` only when the summary is `passed`. A `drifted` or `failed`
summary exits `10`, and an `unsupported` summary exits `12`. The JSON or
Markdown report remains the source of detail for which comparison dimension
changed.

Python adapter APIs expose the same report construction:

```python
from adapters.sitl.comparison import build_sitl_comparison_report
from adapters.sitl.comparison import render_sitl_comparison_json
from adapters.sitl.comparison_markdown import render_sitl_comparison_markdown

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

## Resource and Link Feasibility

Resource systems are configured on vehicle YAML, and communication-link systems
are configured on mission YAML. Scenario `initial_conditions.link_systems`
replaces mission link systems for that scenario run. Reports expose
`result.resource` and `result.link`, and scenario assertions can use
`estimate.resource.is_feasible` and `estimate.link.is_feasible`. Existing
battery-only vehicle files do not need changes.

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

## Advisory Warning Codes

Advisory warnings appear in `estimate`, `scenario`, `sample`, and `propagate` output when the
estimator detects a condition that does not make the mission infeasible but may affect real
operations. The `--format summary` line includes `warnings N` when any are present; the full
JSON envelope lists each warning with its `code`, `message`, and the leg or route item index
where it was raised.

| Code | Raised by | Meaning | Operator action |
|------|-----------|---------|-----------------|
| `MAX_WIND_EXCEEDED` | transit legs | Measured wind speed on a leg exceeds `vehicle.performance.max_wind_mps`. The estimator does not enforce this limit; the energy model still completes. | Review each flagged leg. If the vehicle cannot fly safely at that wind, revise the route or reschedule. |
| `RESERVE_BELOW_FAILSAFE_ABORT_THRESHOLD` | post-estimation | Predicted reserve at landing is below the vehicle's `failsafe.low_battery_abort_percent`. The autopilot may trigger an emergency landing before route completion. | Increase battery capacity, reduce distance, or add an intermediate landing. |
| `RESERVE_BELOW_FAILSAFE_WARN_THRESHOLD` | post-estimation | Predicted reserve at landing is below `failsafe.low_battery_warn_percent`. The vehicle will likely trigger a low-battery alert mid-flight. | Add reserve margin or reduce energy consumption. |
| `GEOFENCE_EVALUATED_2D_ONLY` | geofence check | Geofence intersection uses 2D lon/lat geometry. Altitude bounds in the GeoJSON are not checked. | If the geofence has altitude-dependent zones, verify altitude clearance manually. 3D altitude-bound checking is planned. |
| `DIVERT_ENERGY_TAS_ONLY` | landing-zone reachability | Landing-zone divert energy is computed from true airspeed (TAS) without wind correction. In a headwind, a zone declared reachable may not be in practice. | Add headwind margin to landing-zone distances or use a closer alternate. |
| `ROUTE_ACTIONS_AFTER_RTL` | route structure check | Route items appear after an RTL action. Those legs are estimated but operationally unreachable — the aircraft returns home before executing them. | Remove the trailing items or re-order the route so RTL is last. |
| `LOITER_RADIUS_IGNORED` | loiter legs | `loiter_radius_m` is set on a loiter item but ignored; the estimator models loiter as a station-keep hold using `max_station_keep_wind_mps` as authority. | Confirm the loiter duration in `loiter_time_s` is correct. Radius will be used in a future fidelity update. |
| `LOITER_ASSUMED_ZERO_GROUND_DISTANCE` | loiter legs | Loiter dwell is modeled as a station-keep hold with zero ground-path distance. The energy model accounts for hover power but not horizontal drift. | Acceptable for pre-flight checks. For precision loiter energy, use fidelity v2 when circular loiter support is added. |
| `LOW_GROUNDSPEED_MARGIN` | transit legs | Computed groundspeed is within 10% of `min_groundspeed_mps`. Wind is strong relative to cruise speed, which may cause navigation issues. | Reduce cruise altitude where wind is weaker, or use a route that avoids the high-wind leg. |
| `HIGH_CRAB_MARGIN` | transit legs | Crab angle is within 10% of `vehicle.performance.max_crab_angle_deg`. The cross-wind component is near the vehicle limit. | Route the mission to reduce cross-wind exposure or verify the vehicle can sustain the required crab angle. |
| `HOVER_SPEED_USED_AS_STATION_KEEP_AUTHORITY` | loiter / hover legs | `max_station_keep_wind_mps` is not set in the vehicle profile; `hover_speed_mps` is used as a fallback for station-keep wind authority. | Set `performance.max_station_keep_wind_mps` in the vehicle YAML for a more accurate station-keep check. |

Warnings are informational — the estimator still produces a result. They are attached to the
envelope's `warnings` list and counted in the `--format summary` `warnings N` field. When no
warnings are present, the field is omitted.

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

For automated pipelines, treat each step independently -- do not short-circuit
on `estimate` infeasibility before running `scenario` and `sample`, since each
command produces independent evidence. A recommended CI pattern:

```bash
uv run bvlos-sim estimate ... --output /tmp/estimate.json
ESTIMATE_EXIT=$?
uv run bvlos-sim scenario ... --output /tmp/scenario.json
SCENARIO_EXIT=$?
uv run bvlos-sim sample ... --output /tmp/uncertainty.json
```

Each command produces independent evidence. An infeasible `estimate` (exit 10)
is a pre-flight stop. A `scenario` failure (exit 10) means an assertion failed.
`compare` exiting 10 (`drifted`/`failed`) requires reviewing the changed
dimensions; exit 12 (`unsupported`) means the bundle is contract-only and
`sitl --live` must be run first.

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
from estimator import EstimationOptions
from estimator import FidelityMode
from estimator import LayeredWindProvider
from estimator import WindLayer
from estimator import estimate_mission_distance_time
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

Terrain, wind-grid, geofence, landing-zone, and scenario execution APIs accept
the same provider objects used by the CLI loaders.

Monte Carlo uncertainty example:

See `examples/uncertainty/` for complete uncertainty plan YAML files.

```python
from estimator import run_monte_carlo

mc_result = run_monte_carlo(plan, mission, vehicle)
print(mc_result.feasibility_rate)
print(mc_result.total_time_s.mean)
print(mc_result.total_time_s.p95)
```

Or via the `sample` CLI command:

```bash
uv run bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml
uv run bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml --format markdown
```

## Output Contracts

The estimator CLI emits `estimator-envelope.v5`.

The scenario CLI emits `scenario-report.v2`.

The sample CLI emits `uncertainty-report.v1`.

The propagate CLI emits `stochastic-envelope.v1`.

The SITL contract command emits `sitl-evidence.v1`.

The compare CLI and SITL comparison API emit `sitl-comparison.v1`.

Estimator, scenario, and stochastic JSON outputs are canonical and
regression-tested with golden fixtures. Stochastic output is deterministic
for a fixed seed. Markdown output is supported for human-readable estimator,
scenario, uncertainty, stochastic, and SITL comparison reports.
`estimate --format summary`, `scenario --format summary`,
`sample --format summary`, and `propagate --format summary` emit one-line
plain-text summaries for terminal checks and shell pipelines; no summary
schema or envelope is created. `estimate --format geojson|kml` and
`scenario --format geojson|kml` emit map exports directly from the computed
mission estimate instead of creating a new schema or envelope. Invalid-input
and internal-error paths still fall back to JSON envelopes so automation can
parse failures consistently.

## Verification

```bash
uv run ruff check .
uv run pytest
uv run pytest tests/test_cli.py tests/test_scenario_cli.py  # CLI subset
```
