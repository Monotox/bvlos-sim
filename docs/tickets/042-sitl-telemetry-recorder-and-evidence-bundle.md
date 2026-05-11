# Ticket 042: SITL Telemetry Recorder and Evidence Bundle

## Goal

Record ArduPilot SITL telemetry and command evidence into the versioned evidence
bundle defined by Ticket 040.

## Current Gap

After a SITL mission can run, the project still needs replayable evidence:
telemetry, command logs, timestamps, simulator metadata, input hashes, and tool
versions. Without this layer, SITL execution cannot support deterministic
comparison or release-quality debugging.

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

## Out of Scope

- Expected-vs-observed scoring.
- Flight phase segmentation.
- Real-world flight-log ingestion.
- Long-term artifact storage service.
