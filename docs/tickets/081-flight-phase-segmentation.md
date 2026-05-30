# Ticket 081: Flight Phase Segmentation

## Goal

Split real flight traces into the same kinds of phases the simulator models so calibration can happen per phase instead of only on total mission time.

## Current Gap

There is no segmentation layer to map raw/normalized flight traces into takeoff, climb, transit, loiter, descent, landing, RTL, or divert phases.

## Scope

- Add deterministic phase segmentation over normalized traces.
- Support initial v1 phase set:
  - takeoff
  - climb
  - transit
  - loiter
  - descent
  - landing
  - rtl
  - divert
- Emit segment boundaries and segment metadata.
- Record uncertain/unsegmentable portions explicitly instead of guessing.

## Integration Requirements

- Segment labels should map to existing estimator leg phases and mission actions
  wherever possible.
- Segmentation inputs must use normalized traces from Ticket 080 and retain
  links to mission, vehicle, terrain, wind, and scenario artifacts.
- Add examples that compare segmented observed phases with estimator/scenario
  phase outputs.
- Keep segmentation deterministic and replayable from stored YAML/JSON
  artifacts.

## Acceptance Criteria

- A normalized flight trace can be segmented deterministically into supported phases.
- Unknown/ambiguous segments are reported explicitly.
- Segmented phases can be compared against existing estimator legs and scenario
  timelines.

## Out of Scope

- Parameter fitting.
- Probabilistic segmentation.

## Prerequisites

Ticket 080 (flight log ingestion) is implemented. Input type: `NormalizedFlightTrace`
from `adapters.flight_log.ingest_dataflash_log` or `adapters.flight_log.load_flight_trace`.

---

## Implementation

**Status:** implemented

### New files

| File | Purpose |
|---|---|
| `schemas/phase_segment.py` | `TracePhase`, `PhaseSegment`, `SegmentationMetadata`, `PhaseSegmentResult` (schema version `phase-segments.v1`) |
| `adapters/phase_segmentation/segmenter.py` | `segment_trace` — mode-first algorithm with kinematic fallback, single-pass smoothing |
| `adapters/phase_segmentation/io.py` | `write_phase_segments`, `load_phase_segments` |
| `adapters/phase_segmentation/__init__.py` | Public package |
| `tests/test_phase_segmentation.py` | 27 tests |

`schemas/__init__.py` updated to export `TracePhase`, `PhaseSegment`, `PhaseSegmentResult`,
`SegmentationMetadata`, and `PHASE_SEGMENT_SCHEMA_VERSION`.

### Algorithm

1. Compute per-record vertical rate using finite differences (forward for first record,
   central for interior, backward for last).
2. Assign `TracePhase` to each record:
   - If `flight_mode` has a direct mapping (TAKEOFF, RTL, LAND, LOITER, …) → use it.
   - If `flight_mode` is AUTO/GUIDED → delegate to kinematic rules.
   - If `flight_mode` is absent → use kinematic rules.
   - Any other mode string → `UNKNOWN`.
3. Kinematic rules (in order):
   - `|vert_rate| ≥ 0.5 m/s AND speed < 1.5 m/s` → TAKEOFF (ascending) or LANDING (descending)
   - `|vert_rate| ≥ 0.5 m/s AND speed ≥ 1.5 m/s` → CLIMB (ascending) or DESCENT (descending)
   - `speed ≥ 3.0 m/s` → TRANSIT
   - `speed < 1.5 m/s` → LOITER
   - otherwise → UNKNOWN
4. Smooth: a single-record phase that differs from both its neighbours is replaced by
   the neighbour phase.
5. Run-length encode into `PhaseSegment` list.

### Estimator mapping

| TracePhase | estimator_leg_phase |
|---|---|
| takeoff | `vertical_takeoff` |
| transit | `transit` |
| loiter | `loiter_dwell` |
| landing | `landing_transit` |
| rtl | `rtl_transit` |
| climb / descent / divert / unknown | `null` |

### Thresholds (exported constants)

| Constant | Value | Meaning |
|---|---|---|
| `CLIMB_VERT_RATE_MPS` | 0.5 m/s | Minimum vertical rate to classify as climbing or descending |
| `LOITER_SPEED_MPS` | 1.5 m/s | Groundspeed below which a record is considered loitering |
| `TRANSIT_SPEED_MPS` | 3.0 m/s | Groundspeed at or above which a record is considered transiting |

### Public API

```python
from adapters.phase_segmentation import segment_trace, write_phase_segments

trace = ingest_dataflash_log(Path("flight.log"), trace_id="my-flight-001")
result = segment_trace(trace)
write_phase_segments(result, Path("segments.json"))
```
