# Ticket 002: Versioning Policy and Golden Fixtures

## Status

Implemented in May 2026.

## Goal

Stabilize estimator outputs before building more layers on top.

## Current Gap

This ticket is complete.

Implementation note:
- Golden fixtures should exercise the package-root `estimator` API and documented output contract.
- Avoid coupling fixtures to internal subpackage boundaries so internal refactors do not create false compatibility breaks.

Implemented in:
- [docs/VERSIONING_POLICY.md](../design.md)
- [tests/test_contract_golden.py](https://github.com/Monotox/bvlos-sim/blob/main/tests/test_contract_golden.py)
- [tests/fixtures/golden/](https://github.com/Monotox/bvlos-sim/tree/main/tests/fixtures/golden)

## Scope

- Define lightweight schema/versioning policy.
- Document unknown-field behavior.
- Version public output schemas.
- Add golden input/output fixtures for:
  - successful estimate
  - failed estimate
  - partial estimate
- Add compatibility test harness comparing current outputs to stored golden fixtures.

## Integrated Surfaces

- Golden fixtures cover estimator JSON and Markdown reports.
- Scenario report golden fixtures cover deterministic scenario envelopes and
  Markdown rendering.
- Contract tests exercise adapters on top of package-root APIs so public output
  changes are caught without freezing internal implementation details.
- Versioning policy applies to mission, vehicle, scenario, envelope, terrain,
  wind-grid, geofence, and landing-zone public surfaces.

## Acceptance Criteria

- Golden output tests fail on unintended contract changes.
- Public schema/versioning rules are documented and enforced in tests.

## Out of Scope

- New estimator features.
- Adapter-specific output formatting beyond canonical JSON/Markdown.
