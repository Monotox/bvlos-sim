# Ticket 040: SITL Adapter Contract and Evidence Schema

## Status

Implemented.

## Goal

Define the deterministic adapter boundary, CLI shape, and evidence artifact
contract for SITL comparison without coupling simulator-specific code to the
core estimator or scenario runner.

## Current Gap

Before this ticket, there was no SITL adapter contract, no versioned evidence
bundle format, and no clear boundary between deterministic expected behavior
and simulator-observed behavior.

Ticket 040 previously covered adapter design, ArduPilot startup, MAVLink
mission execution, telemetry recording, policy command execution, and comparison
reporting in one ticket. That scope is too large for reliable agent execution,
so this ticket now establishes the shared contract used by the follow-on SITL
tickets.

## Scope

- Define a SITL adapter interface that can run outside core estimator modules.
- Define a versioned evidence bundle schema containing:
  - input mission, vehicle, and scenario documents
  - deterministic expected estimator/scenario outputs
  - simulator metadata
  - telemetry artifact references
  - command log references
  - tool and adapter versions
- Define a CLI command shape for SITL execution without fully implementing
  ArduPilot control.
- Add placeholder adapters or no-op fixtures only where needed to prove the
  contract.
- Add docs describing where live simulator dependencies are allowed and where
  they are forbidden.
- Add tests for evidence schema validation and deterministic serialization.

## Integration Requirements

- Drive SITL from existing mission, vehicle, and scenario YAML files rather than
  introducing a parallel scenario format.
- Keep deterministic `estimate`, `scenario`, and `sample` outputs as the source
  of expected behavior.
- Keep all live simulator dependencies outside default estimator tests and
  default CI.
- Keep the core estimator and scenario runner adapter-agnostic.
- Design the evidence schema so Tickets 041-043 can fill in ArduPilot execution,
  telemetry recording, policy command execution, and comparison reports without
  changing the initial artifact shape unnecessarily.

## Acceptance Criteria

- A versioned SITL evidence bundle schema exists.
- The planned SITL command and adapter boundary are documented.
- The evidence schema can reference existing mission, vehicle, scenario,
  terrain, wind-grid, geofence, landing-zone, uncertainty, and report artifacts.
- Core estimator and scenario tests remain independent of live simulator
  dependencies.

## Implementation Notes

- `schemas.sitl` defines the `sitl-evidence.v1` bundle schema, artifact
  references, simulator metadata, expected-output payloads, and observed
  telemetry/command artifact slots.
- `adapters.sitl.evidence` defines the adapter boundary plus a no-op
  `NoopSitlAdapter` used to prove the contract without live simulator
  dependencies.
- The `sitl` CLI command loads an existing `scenario.v1`, runs the deterministic
  scenario report as expected behavior, and emits a contract-only evidence
  bundle.
- Live ArduPilot launch, MAVLink upload, telemetry recording, command execution,
  and comparison metrics were delivered by Tickets 041-043.

## Out of Scope

- Launching ArduPilot SITL.
- MAVLink mission upload.
- Telemetry recording.
- Policy command execution.
- Expected-vs-observed comparison metrics.
- PX4 support (Ticket 045).
- Real aircraft or hardware integration.
