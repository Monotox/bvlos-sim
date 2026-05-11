# Ticket 001: Estimator CLI and Result Envelope

## Status

Implemented in May 2026.

## Goal

Make the current estimator callable from the command line and safe to consume by machines.

## Current Gap

This ticket is complete. Follow-on output contract hardening, schema/versioning policy, and golden compatibility fixtures moved to [002-versioning-and-golden-fixtures.md](./002-versioning-and-golden-fixtures.md).

Implementation note:
- Keep the package-root `estimator` API stable.
- CLI and rendering work should sit on top of the current `estimator/core`, `estimator/execution`, `estimator/environment`, and `estimator/math` split rather than pushing CLI concerns back into domain modules.
- Internal estimator modules should stay adapter-agnostic; concrete CLI concerns belong in `adapters/`.

## Scope

- Add CLI command for estimator execution.
- Load mission and vehicle YAML/JSON from file paths.
- Emit canonical JSON to stdout or file.
- Add optional Markdown rendering adapter.
- Add result envelope metadata:
  - `schema_version`
  - `tool_version`
  - `input_schema_versions`
  - `status`
  - `diagnostics`
  - `assumptions`
  - `result validity/completeness`
  - `provenance`
  - `determinism metadata`
- Define CLI exit codes for success, infeasible, invalid input, unsupported input, internal error.

## Acceptance Criteria

- A user can run the estimator from CLI with mission and vehicle files.
- JSON output is canonical and deterministic.
- Failed and partial results are impossible to confuse with complete success.

## Integrated Surfaces

- Mission and vehicle YAML/JSON are loaded through `bvlos-sim estimate`.
- The command composes with mission asset references for geofences,
  landing zones, terrain grids, and wind grids.
- Canonical JSON and Markdown outputs use the same envelope construction path
  as golden fixture tests.
- CLI exit codes remain part of the public contract and are covered by tests.
- The package-root estimator API remains the core execution surface used by
  adapters rather than embedding estimation logic in the CLI.

## Out of Scope

- Energy feasibility.
- Geofences.
- SITL.
- UI/API.
