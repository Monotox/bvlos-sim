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

## Acceptance Criteria

- At least one real log format can be ingested into a deterministic internal trace model.
- The normalized trace format is documented and versioned.

## Out of Scope

- Parameter fitting.
- Validation metrics.
- SITL telemetry ingestion parity.
