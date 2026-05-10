# Ticket 003: Technical Debt Hardening Before Feature Work

## Status

Implemented in May 2026.

## Goal

Reduce the current maintenance and contract risk in the estimator baseline before adding new capabilities.

## Current Gap

This ticket is complete.

Implementation note:
- Keep the package-root `estimator` API stable while simplifying internal boundaries.
- Keep accepted-but-non-operative schema fields documented in [Estimator v1 field semantics](../ESTIMATOR_V1_FIELD_SEMANTICS.md).

Implemented in:
- [docs/VERSIONING_POLICY.md](../VERSIONING_POLICY.md)
- [docs/ESTIMATOR_V1_FIELD_SEMANTICS.md](../ESTIMATOR_V1_FIELD_SEMANTICS.md)
- [tests/test_contract_golden.py](../../tests/test_contract_golden.py)

Follow-up hardening completed after the initial package-boundary cleanup:
- route-item target invariants are shared between schema validation and estimator runtime, so partial coordinate pairs and ignored altitude references fail consistently
- mission/vehicle profile id mismatches now fail before context construction
- runtime action dispatch now verifies full `MissionAction` coverage across schema requirements and executors
- leg phases and source identifiers moved away from raw strings where practical, and the mission-default cruise speed identifier was corrected
- mission totals now use a named aggregate instead of positional tuple unpacking
- envelope construction paths now share one base builder
- route-item invariant failures now cross the schema/runtime boundary as typed errors instead of plain message-only `ValueError`s
- wind-provider metadata now uses stable provider ids instead of leaking implementation class names
- envelope diagnostic codes and result-validity scope now use closed enum sets instead of raw strings
- derived runtime models are frozen where mutation is not intended
- CLI output-write failures now fall back through a typed internal-error path instead of retrying brittle writes blindly
- Markdown output is now pinned by golden fixtures alongside JSON envelope coverage
- stale hard-coded test-count claims were removed from top-level docs

## Scope

- Audit and simplify public/internal import surfaces:
  - reduce redundant compatibility facades in `estimator/core/`
  - remove the lazy import workaround in `estimator/execution/__init__.py`
  - reduce schema re-export indirection where it no longer provides real compatibility value
- Harden the public result contract:
  - define schema/versioning policy
  - add golden fixtures for canonical JSON outputs
  - add regression tests for invalid-input and internal-error envelopes
  - stop leaking unstable dependency/runtime exception text into public machine-facing outputs
- Reconcile schema surface with implemented behavior:
  - identify every accepted field that is currently ignored by the estimator path
  - either wire it into runtime behavior, reject it explicitly, or document it as reserved/non-operative
  - align constraint, energy, failsafe, and mission-policy semantics with current implementation reality
- Tighten API consistency:
  - remove unnecessary `str` widenings where enum types are the intended contract
  - make CLI/result status handling consistent across package and adapter surfaces
- Sync documentation with reality:
  - update code layout descriptions
  - update test-count/status claims
  - document the post-refactor module boundaries and compatibility guarantees

## Acceptance Criteria

- Internal package boundaries are simpler and no longer depend on lazy import hacks.
- Remaining compatibility shims are minimal, intentional, and documented.
- Public JSON envelope behavior is pinned by golden tests and versioning rules.
- Machine-facing error envelopes do not depend on unstable third-party exception wording.
- No schema field is silently accepted without a clear implemented meaning, explicit rejection, or documented reserved status.
- README, roadmap, and ticket backlog reflect the actual current architecture and test status.

## Out of Scope

- New estimator capabilities or new mission feature support.
- Energy-feasibility modeling beyond what is required to reconcile current schema/runtime semantics.
- UI, API, SITL, or broader simulator platform work.
