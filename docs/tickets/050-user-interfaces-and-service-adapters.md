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

## Acceptance Criteria

- CLI, API, and UI all execute the same core path and produce consistent results.

## Out of Scope

- New domain rules in UI/API layers.
- UI-only estimation logic.
