# Ticket 102: Binary Flight-Log Ingestion (ArduPilot .bin, PX4 ULog)

## Status

Planned.

## Goal

Ingest the binary flight-log formats that real operators and public datasets
actually produce — ArduPilot DataFlash binary (`.bin`) and PX4 ULog (`.ulg`) —
into the existing `NormalizedFlightTrace`, so calibration (Ticket 082) is not
limited to the rare hand-exported DataFlash *text* (`.log`) format.

## Current Gap

`adapters/flight_log/` only parses ArduPilot DataFlash **text** (`.log`). In
practice:

- ArduPilot flight controllers record **binary `.bin`**; `.log` is a manual
  conversion most operators never produce.
- PX4 / the public **Flight Review** log database (review.px4.io) — the largest
  source of real logs with battery current/voltage — uses **ULog (`.ulg`)**.

So the ingestion path cannot consume the formats needed to calibrate against
real, publicly available flights.

## Scope

- Introduce a format-dispatch entry point that selects an adapter by content
  (header magic bytes) with extension as a fallback, rather than assuming text.
  - ArduPilot `.bin`: head bytes `0xA3 0x95`.
  - ULog `.ulg`: magic `0x55 0x4C 0x6F 0x67 0x01 0x12 0x35` (`ULog\x01\x12\x35`).
- Add an ArduPilot DataFlash **binary** adapter producing the same
  `NormalizedFlightTrace` as the text adapter (reuse the row→record
  normalization, missing-field detection, GPS-fix filtering, and provenance).
- Add a PX4 **ULog** adapter mapping PX4 topics to the normalized record fields
  (`vehicle_gps_position`, `battery_status`, `vehicle_local_position` /
  `wind_estimate`, `vehicle_status` flight mode, etc.).
- Record the concrete source format in `FlightTraceProvenance.source_format`
  (e.g. `ardupilot_dataflash_binary`, `px4_ulog`).
- Preserve determinism: identical input bytes yield byte-identical canonical
  output.

## Dependency Decision (resolve in this ticket)

Two viable approaches; pick one explicitly and record the rationale:

1. **Library-backed** — `pymavlink` (`DFReader` handles both `.bin` and `.log`)
   and `pyulog` for ULog. Least hand-written parsing and most robust to format
   edge cases; adds dependencies (acceptable in principle — `mavsdk` is already
   a dependency — but `pymavlink`/`pyulog` enlarge the footprint and must be
   carried into the bvlos-mission-control worker image).
2. **Hand-rolled** — parse the self-describing `FMT`/format messages directly.
   No new dependencies and matches the existing text adapter's style, but ULog
   in particular is intricate (subscriptions, multi-id topics, appended data)
   and risky to fully cover without real sample files.

Recommendation: library-backed for ULog (correctness density is high), and
either approach for `.bin`. Decide and note the choice before implementing.

## Integration Requirements

- Public API stays `adapters.flight_log` — add binary adapters behind the
  dispatch; existing `ingest_dataflash_log` text path is unchanged.
- Reuse `FlightTraceRecord` / `NormalizedFlightTrace` / `FlightTraceProvenance`
  and the canonical-JSON writer; no schema-version bump unless a new field is
  required.
- Add synthetic binary fixtures (build minimal `.bin` / `.ulg` byte streams in
  tests) so the adapters are tested without checking in large real logs.
- Keep arbitrary-file-read and resource constraints consistent with the
  bvlos-mission-control subprocess boundary.

## Acceptance Criteria

- A `.bin` and a `.ulg` file each ingest into a valid `NormalizedFlightTrace`
  with GPS position, groundspeed, altitude, battery, flight mode, and wind where
  present.
- Format is auto-detected from content; an unknown/unsupported file raises a
  clear `FlightLogIngestionError`.
- `source_format` distinguishes text, binary, and ULog inputs.
- GPS-fix filtering, missing-field reporting, and provenance behave identically
  to the text adapter.
- Deterministic: re-ingesting the same file produces identical canonical JSON.

## Out of Scope

- Parameter fitting / calibration math (Ticket 082).
- Non-ArduPilot / non-PX4 autopilot formats.
- Live/streaming telemetry ingestion.

## Prerequisites

Ticket 080 (text ingestion) and Ticket 081 (segmentation) are implemented and
provide the normalization, GPS-fix filtering, and provenance this ticket reuses.
