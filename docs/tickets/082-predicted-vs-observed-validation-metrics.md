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

---

## Implementation

**Status:** implemented

### New files

| File | Purpose |
|---|---|
| `schemas/validation.py` | `MetricComparison`, `MissionValidationMetrics`, `PhaseValidation`, `ValidationReport` (current schema version `validation-report.v2`; v2 adds the required acceptance gate) |
| `adapters/validation/validator.py` | `build_validation_report` — deterministic predicted-vs-observed comparison engine |
| `adapters/validation/io.py` | `write_validation_report`, `load_validation_report` |
| `adapters/validation/__init__.py` | Public package |
| `adapters/validation_markdown.py` | `render_validation_markdown` — Markdown report renderer |
| `adapters/commands/validate.py` | `validate` CLI command |
| `examples/flight_logs/pipeline_demo_001.log` | Synthetic DataFlash log paired with the pipeline demo mission |
| `examples/flight_logs/pipeline_demo_001_trace.json` | Ingested `flight-trace.v1` for the demo |
| `tests/test_validation_metrics.py` | 13 tests |

`schemas/__init__.py` updated to export the validation models; `adapters/cli.py`
registers the `validate` command.

### The phase bridge

Predicted legs (`LegEstimate.phase`) and observed trace segments
(`PhaseSegment.estimator_leg_phase`, populated by Ticket 081) are grouped on the
**same estimator leg-phase keys**, so predicted and observed quantities line up
without manual translation. Observed segments whose phase has no estimator
counterpart (climb, descent, divert, unknown) are reported in `notes`, not
silently dropped.

### Metrics

Mission level: total time, total horizontal distance (WGS-84 geodesic over trace
records, the same model the estimator uses), mean groundspeed (time-weighted over
legs, sample-mean over records), and reserve at landing (estimator reserve %
vs the trace's final `battery_remaining_pct`). Per phase: total time, mean
groundspeed, and predicted-leg / observed-segment counts. Each comparison carries
`predicted`, `observed`, `abs_error`, and `pct_error` (relative to observed,
omitted when observed is absent or zero).

### CLI

```bash
bvlos-sim validate MISSION.yaml VEHICLE.yaml TRACE.json          # Markdown report
bvlos-sim validate MISSION.yaml VEHICLE.yaml TRACE.json --format json
```

The estimate is computed from the same mission/vehicle inputs and assets
(terrain, wind, geofences, landing zones, obstacles, population) as `estimate`
and `sora`, so validation composes with every existing feasibility feature.
Deterministic: identical inputs produce byte-identical canonical JSON.

### Out of scope (kept for later tickets)

Parameter fitting / calibration updates (Ticket 083) and held-out validation
reporting (Ticket 084) build on this report but are not part of it.
