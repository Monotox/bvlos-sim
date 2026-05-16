# SITL Adapter Contract

This document defines the SITL boundary introduced by Ticket 040. The current
implementation supports contract-only evidence bundles, ArduPilot connect/upload
and telemetry recording, and adapter-level comparison reports.

## Contract

The versioned evidence bundle is `sitl-evidence.v1`. It contains:

- input artifact references for scenario, mission, vehicle, and mission assets
- embedded deterministic scenario output used as expected behavior
- embedded deterministic estimator result from the scenario output
- simulator and adapter metadata
- telemetry, command-log, simulator-log, and adapter-log artifact references
- tool and adapter versions

The no-op adapter emits `status: contract_only` and leaves observed artifact
lists empty. Live adapters can emit `status: completed` with telemetry,
command-log, simulator-log, and adapter-log artifact references.

The versioned comparison report is `sitl-comparison.v1`. It compares a
`sitl-evidence.v1` bundle against the embedded deterministic scenario report and
emits ordered comparison items plus a summary.

## CLI Shape

Build a contract-only evidence bundle from an existing scenario:

```bash
uv run bvlos-sim sitl examples/scenarios/pipeline_demo_001_integrated_scenario.yaml
```

Write the bundle to a file:

```bash
uv run bvlos-sim sitl \
  examples/scenarios/pipeline_demo_001_integrated_scenario.yaml \
  --output /tmp/sitl-evidence.json
```

The command reuses existing scenario inputs. There is no parallel SITL scenario
format.

## Comparison API

Comparison report construction is currently a Python adapter API rather than a
CLI command:

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

`adapters.sitl_evidence.compare_sitl_evidence_bundle(...)` provides the same
comparison entry point from the evidence module.

## Adapter Boundary

SITL adapters live outside the deterministic estimator core. Adapter code may
depend on simulator, MAVLink, process-control, telemetry, or networking
packages only in adapter modules and optional integration environments.

Allowed:

- adapter modules under `adapters/` or future optional adapter packages
- CLI entry points that call adapter modules
- tests using no-op adapters, synthetic telemetry, or fixtures
- optional local workflows outside default CI

Forbidden:

- importing simulator or MAVLink packages from `estimator/core`,
  `estimator/execution`, or `schemas`
- requiring live simulator dependencies for the default test suite
- making estimator, scenario, or uncertainty outputs depend on a live simulator
- treating SITL output as real-world calibration or operational approval

## Follow-On Tickets

- Ticket 041 adds the concrete ArduPilot launch/connect and mission-upload
  adapter behind this contract. Implemented.
- Ticket 042 records telemetry and command artifacts into the evidence bundle.
  Implemented.
- Ticket 043 compares deterministic scenario expectations against SITL evidence
  through `sitl-comparison.v1`. Implemented.
- Ticket 045 adds PX4 SITL support behind the same adapter and evidence
  contract.
