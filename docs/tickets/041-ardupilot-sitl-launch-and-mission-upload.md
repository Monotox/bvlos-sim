# Ticket 041: ArduPilot SITL Launch and Mission Upload

## Goal

Implement the first concrete ArduPilot SITL adapter that can launch or connect
to SITL, upload a mission derived from existing bvlos-sim YAML, and start a
controlled simulator run.

## Current Gap

Ticket 040 defines the adapter and evidence contract, but there is no concrete
ArduPilot adapter, MAVLink connection lifecycle, mission upload flow, or
deterministic SITL run setup.

## Scope

- Add an ArduPilot SITL adapter behind the contract from Ticket 040.
- Support either launching a local SITL process or connecting to an already
  running instance, with explicit configuration.
- Translate supported mission YAML route items into the MAVLink mission upload
  path.
- Upload, arm/start where appropriate, monitor run state, and stop/cleanup
  deterministically.
- Capture simulator metadata needed by the evidence bundle.
- Add tests using fakes/mocks for adapter lifecycle and mission upload behavior.
- Add documentation for local SITL prerequisites without making them required
  for default CI.

## Integration Requirements

- Use existing mission, vehicle, and scenario YAML files as inputs.
- Reuse the evidence bundle schema from Ticket 040.
- Keep ArduPilot-specific dependencies optional and adapter-local.
- Do not add MAVLink or simulator concerns to core estimator/scenario modules.
- Add SITL-focused examples only if they reuse existing mission, vehicle,
  terrain, wind, and scenario conventions.

## Acceptance Criteria

- A supported mission can be uploaded to ArduPilot SITL through the adapter.
- Adapter lifecycle behavior is covered by deterministic fake/mocked tests.
- Default test runs do not require ArduPilot, MAVLink network access, or a live
  simulator process.
- Unsupported mission actions fail with explicit adapter diagnostics.

## Out of Scope

- Telemetry normalization beyond minimal run-state monitoring.
- Scenario policy command execution.
- Expected-vs-observed comparison reports.
- PX4 support.
- Real aircraft or hardware integration.
