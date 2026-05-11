# Ticket 071: Live Comms, Remote ID, and Traffic Integrations

## Goal

Add optional adapter boundaries for live operational signals while keeping core
estimation and scenario execution deterministic by default.

## Current Gap

There are no live comms adapters, Remote ID inputs, traffic feeds, or UTM/U-space
runtime integrations. Existing operational-integration work only defines seams
and governance concepts.

## Scope

- Add adapter interfaces for live comms-link state.
- Add adapter interfaces for Remote ID observations.
- Add adapter interfaces for traffic or detect-and-avoid observations.
- Add UTM/U-space runtime adapter shape after Ticket 070 defines the seams.
- Normalize live inputs into replayable evidence artifacts.
- Ensure core estimation can replay captured inputs without live network access.

## Integration Requirements

- Live adapters must produce replayable YAML/JSON artifacts or evidence bundles
  that existing `estimate`, `scenario`, validation, and report tooling can read.
- Captured comms, Remote ID, traffic, and UTM/U-space data must connect to the
  operational seams from Ticket 070 rather than bypassing them.
- Add examples that combine live-input replay with existing mission, vehicle,
  terrain, wind, geofence, landing-zone, and scenario files.
- Keep live network dependencies optional and outside deterministic core
  execution.
- Reports must distinguish live-captured data from deterministic mission inputs.

## Acceptance Criteria

- Live operational inputs can be captured and replayed deterministically.
- Core tests do not require external networks or live services.
- Runtime integrations remain optional adapter layers.
- Replay artifacts can be evaluated together with existing YAML-configured
  mission and scenario behavior.

## Out of Scope

- Replacing certified detect-and-avoid systems.
- Claiming operational approval or regulatory compliance.
- Mandatory live-service dependencies in core CI.
