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

## Acceptance Criteria

- One deterministic scenario can be executed against ArduPilot SITL with a reproducible evidence bundle.

## Out of Scope

- PX4 support.
- Real aircraft/hardware integration.
