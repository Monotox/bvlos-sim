# Ticket 041: ArduPilot SITL Launch and Mission Upload

## Status

Implemented.

## Goal

Implement the first concrete ArduPilot SITL adapter that can connect to a
running SITL instance, upload a mission derived from existing bvlos-sim YAML,
and start a controlled simulator run.

## Resolved Gap

Ticket 040 defined the adapter and evidence contract. This ticket added the
concrete ArduPilot adapter, MAVLink connection lifecycle, mission upload and
execution flow, and deterministic fake-tested adapter behavior.

## Scope

- Add an ArduPilot SITL adapter behind the contract from Ticket 040.
- Support connecting to an already running SITL instance, with explicit
  configuration.
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
- A live run arms, enters AUTO, and reaches an explicit MAVLink mission-complete
  state before its evidence bundle can be marked completed.
- Adapter lifecycle behavior is covered by deterministic fake/mocked tests.
- Default test runs do not require ArduPilot, MAVLink network access, or a live
  simulator process.
- Unsupported mission actions fail with explicit adapter diagnostics.

## Implementation Notes

- `adapters.sitl.ardupilot` defines the ArduPilot execution adapter.
- `ArduPilotSitlAdapter` satisfies the Ticket 040 `SitlAdapter` evidence
  boundary while keeping all MAVLink imports lazy and adapter-local.
- Supported mission route items map to `MISSION_ITEM_INT` uploads using the
  pinned MAVLink command and altitude-frame IDs.
- The optional `sitl` dependency group contains `pymavlink`; core dependencies
  and default tests remain independent of live simulator tooling.
- The adapter records mission-progress and position telemetry plus command,
  simulator, and adapter logs for the evidence bundle.
- The CLI maps live adapter connection, upload, execution, telemetry, and
  timeout failures to exit `13` (`INTERNAL_ERROR`); only input/schema/asset
  failures use `11` (`INVALID_INPUT`).

## Out of Scope

- Controller-log normalization beyond the SITL evidence message contract.
- Launching a local ArduPilot subprocess from the Python adapter.
- Scenario policy command execution.
- Expected-vs-observed comparison reports.
- PX4 support (Ticket 045).
- Real aircraft or hardware integration.
