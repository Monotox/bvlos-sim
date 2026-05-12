# Ticket 046: PX4 SITL Telemetry Recorder and Evidence Bundle

## Status

Planned.

## Goal

After a PX4 SITL mission run (Ticket 045), record live telemetry and command
logs and assemble a complete `sitl-evidence.v1` bundle that includes the
observed artifacts alongside the deterministic expected outputs. The bundle
must remain readable by the comparison tooling from Ticket 043.

## Current Gap

Ticket 045 establishes the PX4 adapter lifecycle and mission upload path.
Without telemetry recording, the PX4 adapter can only produce
`SitlEvidenceStatus.CONTRACT_ONLY` bundles (same as the no-op adapter). This
ticket closes that gap by wiring in the PX4 telemetry capture path and
populating `SitlObservedArtifacts` with real log references.

## Scope

- After a mission upload and run, subscribe to PX4 telemetry streams
  (position, attitude, battery, mode, arm state) via MAVLink or MAVSDK.
- Record telemetry to a canonical log file (e.g. JSON lines or CSV) with
  monotone timestamps.
- Record all uploaded and received MAVLink command IDs and acknowledgements.
- Populate `SitlObservedArtifacts` with `SitlArtifactReference` entries
  pointing to the recorded log files.
- Set `SitlEvidenceStatus` to `OBSERVED` in the completed evidence bundle.
- Keep recording and MAVLink/MAVSDK dependencies optional and adapter-local.
- Add deterministic fake/mocked tests for the recording path and bundle
  assembly using pre-recorded log fixtures.
- Reuse existing mission, vehicle, scenario, terrain, wind, geofence,
  landing-zone, resource, link, and scenario conventions.

## Integration Requirements

- Use the `SitlAdapter` contract from Ticket 040: `observed_artifacts()` must
  return a fully populated `SitlObservedArtifacts`.
- Evidence bundles emitted by the PX4 adapter must validate against
  `sitl-evidence.v1` and remain readable by the Ticket 043 comparison tooling.
- Do not add telemetry recording behavior to estimator core, scenario core,
  mission schemas, or deterministic envelope construction.
- Preserve `estimate`, `scenario`, and `sample` behavior.
- Default tests and CI must not require PX4, MAVLink network access, or a live
  simulator process.

## Acceptance Criteria

- After a PX4 SITL run, a `sitl-evidence.v1` bundle with
  `status: observed` and populated `observed.telemetry_log` and
  `observed.command_log` artifact references is written to disk.
- The bundle validates against `sitl-evidence.v1`.
- Recording behavior is covered by deterministic fake/mocked tests using
  pre-recorded log fixtures.
- Default tests and CI do not require live PX4 or MAVLink dependencies.

## Out of Scope

- PX4 adapter lifecycle and mission upload — Ticket 045.
- ArduPilot telemetry recording — Ticket 042.
- Expected-vs-observed comparison scoring — Ticket 043.
- Real aircraft or hardware integration.
- PX4-specific UI workflows.
