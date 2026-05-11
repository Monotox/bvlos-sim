# Ticket 050: User Interfaces and Service Adapters

## Goal

Expose stable core functionality without moving domain logic into surfaces.

## Current Gap

There is no REST API, no web UI, and no report browser over the core execution
path.

## Scope

- Add REST API adapter.
- Add web map UI.
- Add timeline playback.
- Add warnings/failures display.
- Add report browser.
- Keep JSON and Markdown as first-class outputs.
- Add PDF export only if it remains adapter-only and cheap.

## Integration Requirements

- REST API endpoints must call the same core paths as `estimate` and `scenario`.
- UI workflows must load and present existing mission, vehicle, scenario,
  terrain, wind, geofence, and landing-zone YAML/JSON inputs.
- Add examples or fixtures showing API/UI execution with combined terrain,
  wind-grid, landing-zone, geofence, and scenario features.
- Preserve canonical JSON envelopes and Markdown reports as stable output
  surfaces for API and UI downloads.
- Do not add UI-only estimation, routing, policy, wind, terrain, or feasibility
  logic.

## Acceptance Criteria

- CLI, API, and UI all execute the same core path and produce consistent results.
- A mission/scenario that works from CLI can be run from API/UI without changing
  schemas or asset layout.

## Out of Scope

- New domain rules in UI/API layers.
- UI-only estimation logic.
