# Ticket 040: SITL Integration - ArduPilot First

## Goal

Compare internal scenario behavior against ArduPilot SITL evidence.

## Current Gap

There is no SITL adapter, no MAVLink mission execution path, and no evidence
bundle for comparing deterministic scenario expectations against simulator
behavior.

## Scope

- Add ArduPilot SITL adapter.
- Add MAVLink mission upload/start/monitor flow.
- Add telemetry recorder.
- Add policy command execution.
- Add evidence bundle containing:
  - input mission
  - simulator output
  - SITL telemetry
  - command log
  - tool versions
- Add comparison report between expected and observed behavior.

## Integration Requirements

- Drive SITL from existing mission, vehicle, and scenario YAML files rather than
  introducing a parallel scenario format.
- Support the same mission assets used by `estimate`, including geofences,
  landing zones, terrain files, and wind-grid files where they affect expected
  simulator behavior.
- Add SITL-focused YAML examples under `examples/` that reuse existing mission,
  vehicle, terrain, wind, and scenario conventions.
- Keep the deterministic `estimate` and `scenario` commands as the source of
  expected behavior; SITL comparison should wrap those outputs.
- Add any new SITL command as an adapter command that consumes the same schemas
  and emits a versioned evidence/report artifact.
- Keep live simulator dependencies out of core estimator tests and default CI.

## Acceptance Criteria

- One deterministic scenario can be executed against ArduPilot SITL with a reproducible evidence bundle.
- The same YAML inputs can be run through deterministic scenario execution and
  SITL comparison without manual translation.

## Out of Scope

- PX4 support.
- Real aircraft/hardware integration.
