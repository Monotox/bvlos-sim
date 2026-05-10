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

bvlos-sim exposes two commands:

- `estimate`: run deterministic mission estimation and static feasibility checks
- `scenario`: run deterministic scenario events and assertions

Command help:

```bash
uv run bvlos-sim estimate --help
uv run bvlos-sim scenario --help
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

## Python API

Use the package-root imports for stable caller code:

```python
from estimator import EstimationOptions
from estimator import FidelityMode
from estimator import LayeredWindProvider
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

Scenario example:

```python
result = run_scenario(scenario, mission, vehicle)
```

## Output Contracts

The estimator CLI emits `estimator-envelope.v4`.

The scenario CLI emits `scenario-report.v1`.

Both JSON outputs are canonical, deterministic, and regression-tested with
golden fixtures. Markdown output is supported for human-readable reports.

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
