# Ticket 080: Flight Log Ingestion and Trace Normalization

## Goal

Create the first real-world validation input pipeline by ingesting flight logs into a stable internal trace format.

## Current Gap

The simulator has no real-flight data ingestion layer. There is no normalized flight trace model for comparing predicted and observed behavior.

## Scope

- Add log ingestion adapter for one autopilot/log format first.
- Add normalized flight trace schema containing:
  - timestamp
  - lat/lon/alt
  - groundspeed
  - heading
  - battery/current/remaining fields where available
  - flight mode
  - wind estimate if available
  - mission item index if available
- Add metadata for:
  - raw log file identity
  - source format
  - parsing assumptions
  - missing fields
- Store normalized traces as versioned artifacts.

## Integration Requirements

- Normalized traces must reference existing mission and vehicle YAML where a
  matching planned flight is available.
- Trace artifacts should be consumable by validation tooling without changing
  `estimate` or `scenario` input schemas.
- Add examples that pair a mission, vehicle, terrain, wind, and trace artifact
  for validation workflows.
- Preserve provenance linking raw logs, parsed traces, tool versions, and
  mission/scenario inputs.

## Acceptance Criteria

- At least one real log format can be ingested into a deterministic internal trace model.
- The normalized trace format is documented and versioned.
- Ingested traces can be used alongside existing estimator and scenario outputs.

## Out of Scope

- Parameter fitting.
- Validation metrics.
- SITL telemetry ingestion parity.

---

## Implementation

**Status:** implemented

### Format

ArduPilot DataFlash text (`.log`). No new dependencies — text format is self-describing
via `FMT` records, robust across firmware versions.

### New files

| File | Purpose |
|---|---|
| `schemas/flight_log.py` | `FlightTraceRecord`, `FlightTraceProvenance`, `FlightTraceMissionRef`, `NormalizedFlightTrace` (schema version `flight-trace.v1`) |
| `adapters/flight_log/dataflash.py` | `ingest_dataflash_log` — FMT-driven column parsing, GPS + BAT + MODE + NKF6 carry-forward merge, missing-field detection, `FlightLogIngestionError` |
| `adapters/flight_log/io.py` | `write_flight_trace`, `read_flight_trace`, `load_flight_trace` (canonical JSON, `InputDocument` provenance) |
| `adapters/flight_log/__init__.py` | Public package |
| `tests/fixtures/synthetic_dataflash.log` | Minimal self-contained DataFlash text fixture |
| `tests/test_flight_log_ingestion.py` | 16 tests |
| `examples/real_world/trace_pipeline_demo.json` | Example trace paired with `pipeline_demo_001.yaml` |

`schemas/__init__.py` updated to export `NormalizedFlightTrace`, `FlightTraceRecord`,
`FlightTraceProvenance`, `FlightTraceMissionRef`, and `FLIGHT_TRACE_SCHEMA_VERSION`.

### Parsing algorithm

1. Read bytes → SHA-256 (provenance).
2. Scan `FMT` lines to build per-message-type column maps.
3. Collect GPS, BAT, MODE, NKF6/XKF6 rows using column maps (falls back to hardcoded
   positions when `FMT` is absent for a message type).
4. Carry-forward merge: each GPS record inherits the latest BAT/MODE/NKF6 sample
   with `TimeUS ≤ GPS.TimeUS`.
5. Timestamps: `(TimeUS − first_GPS.TimeUS) / 1_000_000` → elapsed seconds.
6. Detect and record missing fields; record parsing assumptions in provenance.

### Public API

```python
from adapters.flight_log import ingest_dataflash_log, load_flight_trace, write_flight_trace
from schemas.flight_log import NormalizedFlightTrace, FLIGHT_TRACE_SCHEMA_VERSION

trace = ingest_dataflash_log(
    Path("flight.log"),
    trace_id="my-flight-001",
    mission_ref=FlightTraceMissionRef(mission_file="missions/my_mission.yaml"),
)
write_flight_trace(trace, Path("trace.json"))
```

### Prerequisites for 081–084

Tickets 081 (phase segmentation), 082 (validation metrics), 083 (calibration), and 084
(holdout reports) all consume `NormalizedFlightTrace` produced by this adapter.
Binary DataFlash (`.bin`) and other formats (MAVLink tlog, PX4 ULog) are deferred to
those tickets or future work.
