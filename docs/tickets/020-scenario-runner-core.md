# Ticket 020: Scenario Runner Core

## Status

Implemented in May 2026.

## Goal

Execute deterministic scenario tests on top of the existing core models.

## Current Gap

This ticket is complete. Scenario schemas, deterministic timeline execution,
event outcomes, assertion results, and scenario reports are implemented.

## Scope

- Add scenario schema:
  - events
  - assertions
  - initial conditions
  - expected outcomes
- Add deterministic event injection.
- Add internal timeline model.
- Add canonical JSON scenario report.
- Add optional Markdown scenario report.
- Add assertion outcomes:
  - `passed`
  - `failed`
  - `skipped`
  - `unsupported`

## Acceptance Criteria

- Scenario runs are repeatable.
- Assertions are machine-readable.
- Scenario runner depends on core interfaces, not CLI/API/UI code.

## Integrated Surfaces

- Scenario YAML uses `schema_version: scenario.v1`, `mission_file`,
  `vehicle_file`, `initial_conditions`, `events`, and `assertions`.
- Scenario paths are resolved from the scenario file directory; referenced
  mission assets are resolved from the mission file directory.
- The `scenario` CLI command loads mission, vehicle, terrain, wind-grid,
  geofence, and landing-zone inputs before calling `run_scenario`.
- Scenario envelopes include scenario, mission, vehicle, and loaded asset
  provenance when those inputs are present.
- Scenario assertions can inspect estimator status, totals, energy, geofence,
  and landing-zone fields.
- Example scenarios live under `examples/scenarios/`, including an integrated
  example that composes scenario execution with mission assets.

## Out of Scope

- SITL.
- Live comms.
- UTM integration.
