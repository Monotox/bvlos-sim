# Ticket 045: PX4 SITL Launch and Mission Upload

## Status

Planned.

## Goal

Add PX4 SITL adapter lifecycle and mission upload support behind the same
adapter contract and `sitl-evidence.v1` bundle introduced by Ticket 040,
without creating a parallel simulator-specific mission or scenario workflow.

## Current Gap

Ticket 040 defines a simulator-neutral evidence contract and no-op adapter.
Tickets 041-043 cover the first live ArduPilot path. PX4 SITL remains
unsupported: there is no PX4 launch/connect lifecycle, PX4 mission upload path,
PX4 simulator metadata capture, or documented adapter boundary for PX4-specific
diagnostics. Ticket 046 will cover PX4 telemetry recording and evidence bundle
assembly; this ticket focuses solely on the lifecycle and upload path.

## Scope

- Add a PX4 SITL adapter behind the Ticket 040 `SitlAdapter` contract.
- Support either launching a local PX4 SITL process or connecting to an already
  running instance, with explicit configuration.
- Translate supported bvlos-sim mission YAML route items into the PX4/MAVLink
  mission upload path.
- Populate `SitlSimulatorMetadata` with PX4-specific adapter kind, frame, and
  autopilot fields using the same evidence bundle shape used by ArduPilot
  adapters.
- Keep PX4, MAVLink, simulator, process-control, and networking dependencies
  optional and adapter-local.
- Add deterministic fake/mocked tests for lifecycle, mission translation, and
  explicit unsupported-action diagnostics.
- Document local PX4 SITL prerequisites without making them required for
  default CI.

## Integration Requirements

- Use the existing `sitl` command or a compatible adapter-selection extension
  that still executes the established scenario and evidence path.
- Do not add PX4-specific behavior to estimator core, scenario core, mission
  schemas, or deterministic envelope construction.
- Preserve `estimate`, `scenario`, and `sample` behavior.
- The `SitlSimulatorMetadata` emitted by the PX4 adapter must be readable by
  the comparison tooling from Ticket 043.
- PX4 examples, if added, must reuse existing mission, vehicle, terrain, wind,
  geofence, landing-zone, resource, link, and scenario conventions.

## Acceptance Criteria

- A supported mission can be uploaded to PX4 SITL through the adapter.
- Adapter lifecycle behavior is covered by deterministic fake/mocked tests.
- Default tests and CI do not require PX4, MAVLink network access, or a live
  simulator process.
- Unsupported route actions or vehicle capabilities produce explicit adapter
  diagnostics.

## Out of Scope

- PX4 telemetry recording and evidence bundle assembly — Ticket 046.
- ArduPilot adapter implementation — Tickets 041-043.
- Expected-vs-observed comparison scoring — Ticket 043.
- Real aircraft or hardware integration.
- PX4-specific UI workflows.
