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

## Acceptance Criteria

- A real flight trace and a matching mission/vehicle input can produce a structured validation report.
- Metrics are available per mission and per phase.

## Out of Scope

- Parameter fitting itself.
- Automatic optimization loops.
