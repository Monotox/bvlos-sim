# Ticket 042: SITL Telemetry Recorder and Evidence Bundle

## Status

Implemented.

## Goal

Record ArduPilot SITL telemetry and command evidence into the versioned evidence
bundle defined by Ticket 040.

## Current Gap

After a SITL mission can run, the project needs replayable evidence: telemetry,
command logs, timestamps, simulator metadata, input hashes, and tool versions.
This ticket adds the artifact layer needed for later deterministic comparison
and release-quality debugging.

## Scope

- Add telemetry recording for the ArduPilot adapter from Ticket 041.
- Normalize recorded telemetry into a replayable artifact format.
- Capture command logs and simulator lifecycle events.
- Store input references and checksums for mission, vehicle, scenario, terrain,
  wind-grid, geofence, landing-zone, and uncertainty inputs when present.
- Emit a complete evidence bundle matching the schema from Ticket 040.
- Add tests using synthetic telemetry streams and adapter fakes.
- Document artifact layout and retention expectations.

## Integration Requirements

- Evidence bundles must be readable without a live simulator.
- Evidence bundles must preserve deterministic expected outputs from
  `estimate`, `scenario`, or `sample` where applicable.
- Recorded telemetry should be compatible with the later flight-log ingestion
  and trace-normalization track when practical.
- Keep artifact writing in adapters; do not add file I/O to core estimator or
  scenario execution.

## Acceptance Criteria

- A SITL run can produce a self-contained evidence bundle.
- The evidence bundle includes telemetry, command log, simulator metadata,
  input provenance, and tool versions.
- Synthetic telemetry tests prove deterministic serialization.
- Missing or malformed telemetry produces explicit adapter diagnostics.

## Implementation Notes

- `adapters.sitl_artifacts` writes deterministic JSON artifacts for telemetry,
  command logs, simulator events, and adapter events.
- `ArduPilotSitlAdapter` can record telemetry from an existing MAVLink
  connection into an artifact directory and reports the generated artifact
  references through the Ticket 040 adapter boundary.
- `build_sitl_evidence_bundle()` marks bundles with observed artifacts as
  `completed` while preserving `contract_only` for no-op or pre-recording
  adapter runs.
- SITL input provenance now accepts an optional `uncertainty.v2` input
  reference when a caller has one.

## Out of Scope

- Expected-vs-observed scoring.
- Flight phase segmentation.
- Real-world flight-log ingestion.
- Long-term artifact storage service.
