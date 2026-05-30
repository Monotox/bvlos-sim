# Ticket 082: Predicted vs Observed Validation Metrics

## Goal

Measure how well simulator outputs match real flight traces.

## Current Gap

The project has no validation metrics layer for comparing estimator outputs to observed flights.

## Scope

- Add predicted-vs-observed comparison engine.
- Compute metrics at mission level and phase level:
  - predicted time vs actual time
  - predicted distance vs actual distance
  - predicted climb/descent timing vs actual
  - predicted groundspeed vs actual
  - predicted reserve vs actual, once energy model exists
- Add validation report schema.
- Keep calibration and validation datasets separate in output/reporting.

## Integration Requirements

- Predicted outputs must come from existing `estimate` and `scenario` runs.
- Observed inputs must come from normalized traces and phase segments from
  Tickets 080 and 081.
- Validation reports must preserve links to mission, vehicle, terrain, wind,
  geofence, landing-zone, and scenario YAML inputs.
- Add examples that run the full path from YAML mission inputs to validation
  metrics without manual data translation.
- Keep validation reporting separate from calibration updates.

## Acceptance Criteria

- A real flight trace and a matching mission/vehicle input can produce a structured validation report.
- Metrics are available per mission and per phase.
- Validation metrics can be produced for missions using existing terrain, wind,
  geofence, landing-zone, energy, and scenario features.

## Out of Scope

- Parameter fitting itself.
- Automatic optimization loops.

## Prerequisites

Ticket 080 (flight log ingestion) is implemented: `NormalizedFlightTrace` from
`adapters.flight_log`.
Ticket 081 (phase segmentation) is implemented: `PhaseSegmentResult` from
`adapters.phase_segmentation`. Both are required for per-phase validation metrics.
