# Ticket 020: Scenario Runner Core

## Goal

Execute deterministic scenario tests on top of the existing core models.

## Current Gap

There is no scenario schema, no timeline model, and no deterministic event injection.

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

## Out of Scope

- SITL.
- Live comms.
- UTM integration.
