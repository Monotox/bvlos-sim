# Ticket 045: PX4 SITL Adapter

## Status

Planned.

## Goal

Add PX4 SITL support behind the same adapter contract and `sitl-evidence.v1`
bundle introduced by Ticket 040, without creating a parallel simulator-specific
mission or scenario workflow.

## Current Gap

Ticket 040 defines a simulator-neutral evidence contract and no-op adapter.
Tickets 041-043 cover the first live ArduPilot path. PX4 SITL remains
unsupported: there is no PX4 launch/connect lifecycle, PX4 mission upload path,
PX4 simulator metadata capture, or documented adapter boundary for PX4-specific
diagnostics.

## Scope

- Add a PX4 SITL adapter behind the Ticket 040 `SitlAdapter` contract.
- Support either launching a local PX4 SITL process or connecting to an already
  running instance, with explicit configuration.
- Translate supported bvlos-sim mission YAML route items into the PX4/MAVLink
  mission upload path.
- Reuse existing `scenario.v1`, mission, vehicle, terrain, wind-grid,
  geofence, landing-zone, resource, and link inputs.
- Populate `sitl-evidence.v1` simulator metadata and artifact references using
  the same evidence bundle shape used by ArduPilot adapters.
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
- Evidence bundles emitted by PX4 and ArduPilot adapters must remain readable by
  the same later comparison tooling from Ticket 043.
- PX4 examples, if added, must reuse existing mission, vehicle, terrain, wind,
  geofence, landing-zone, resource, link, and scenario conventions.

## Acceptance Criteria

- A supported mission can be uploaded to PX4 SITL through the adapter.
- Adapter lifecycle behavior is covered by deterministic fake/mocked tests.
- Default tests and CI do not require PX4, MAVLink network access, or a live
  simulator process.
- Unsupported route actions or vehicle capabilities produce explicit adapter
  diagnostics.
- The emitted evidence bundle validates against `sitl-evidence.v1`.

## Out of Scope

- ArduPilot adapter implementation.
- Expected-vs-observed comparison scoring.
- Real aircraft or hardware integration.
- PX4-specific UI workflows.
