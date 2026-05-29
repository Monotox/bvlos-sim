# Contribution Style Guide

This guide defines the technical standards for changes to bvlos-sim. It is
intended for contributors working on schemas, estimator logic, adapters,
reports, tests, or documentation.

## Goals

Prefer changes that:

- preserve explicit package boundaries
- keep public contracts stable
- move invariants into typed models and enums
- keep tests behavior-focused
- improve maintainability without adding unnecessary abstraction

## Package Boundaries

Current responsibilities:

- `schemas/`: Pydantic input models for mission, vehicle, and scenario files
- `estimator/core/`: public enums, options, result models, constants, and typed errors
- `estimator/execution/`: deterministic estimation, static feasibility, scenario execution, and runtime context
- `estimator/environment/`: wind provider abstractions
- `estimator/math/`: pure math and geometry helpers
- `adapters/`: CLI, file loading, envelopes, output rendering, and Markdown reports
- `adapters/sitl/`: ArduPilot SITL adapter, artifact recording, evidence building, and comparison report logic

Rules:

- Do not move execution-only behavior into `estimator/core/`.
- Do not let `schemas/` depend on adapters or execution internals.
- Do not put domain rules in CLI code.
- Keep package-root `estimator` imports stable.
- Prefer a focused module over a mixed-responsibility file.

## Public Contracts

Treat these as stable:

- package-root `estimator` imports
- `mission.v6`
- `vehicle.v4`
- `scenario.v1`
- `uncertainty.v1`
- `estimator-envelope.v7`
- `scenario-report.v2`
- `uncertainty-report.v1`
- `sitl-evidence.v1`
- `geofence-geojson.v1`
- `landing-zone-geojson.v1`
- `population-grid.v1`
- CLI exit-code semantics
- Markdown report output covered by golden fixtures

If a public contract changes intentionally, update:

1. `docs/VERSIONING_POLICY.md`
2. golden fixtures
3. regression tests
4. user-facing documentation

## Validation Ownership

Use schema validation for:

- field shape
- required and optional fields
- numeric bounds
- route-item authoring invariants
- scenario authoring invariants

Use runtime validation for:

- cross-object consistency
- execution-time feasibility
- defensive checks against mutated model instances
- conditions that require resolved runtime context

Avoid duplicating the same rule in multiple layers unless the runtime version is
clearly defensive.

## Typed Models

Prefer:

- `StrEnum` for closed sets
- Pydantic models or dataclasses for structured data
- named aggregate objects over positional tuples
- typed exceptions over message-only `ValueError` flows

Avoid:

- stringly typed identifiers when the set is closed
- ad hoc dict schemas for structured output
- tuple unpacking where field names matter

## Metadata

Metadata is allowed when it is deliberate.

Rules:

- Keep machine-facing metadata stable when possible.
- Use stable identifiers instead of internal class names.
- Do not hide contract changes in free-form metadata maps.
- Document compatibility-relevant metadata keys.

## Execution Logic

For estimator and scenario execution:

- keep functions small and focused
- keep route-item dispatch table-driven
- keep math helpers pure where practical
- make unsupported and infeasible outcomes explicit
- return structured failures rather than raw dependency exceptions
- preserve determinism unless a future mode explicitly introduces randomness

When extending mission actions:

- update `MissionAction`
- update route-item requirements
- update executor coverage
- add behavior tests
- update golden fixtures if output contracts change

When extending scenario behavior:

- update scenario schema enums and validation
- add runner tests for event and assertion outcomes
- keep unsupported behavior explicit
- update scenario envelope or fixtures only when the public contract changes intentionally

## Adapter Style

Adapters should translate between external surfaces and domain models.

Rules:

- `adapters/io.py` loads and classifies input errors.
- `adapters/envelope.py` builds stable estimator output structures.
- `adapters/scenario_envelope.py` builds stable scenario output structures.
- `adapters/cli.py` wires command surfaces and exit-code policy.
- Markdown renderers should format existing results, not reimplement domain rules.

Prefer adapter-local typed errors for I/O and rendering failures.

## Testing

Prefer tests that verify behavior and contracts.

Write tests for:

- observable estimator behavior
- scenario event and assertion outcomes
- invariant enforcement
- envelope semantics
- CLI exit-code behavior
- deterministic output
- golden fixtures for supported public outputs

Avoid:

- tests that only restate Pydantic internals
- brittle snapshots of implementation details
- hard-coded counts unless the count itself is behavior

Before considering work complete, run:

```bash
uv run ruff check .
uv run pytest
```

## Documentation

Update documentation when changing:

- package boundaries
- public contract semantics
- output formats
- supported fields
- supported actions
- known limitations
- CLI behavior
- ticket status

Do not leave stale comments, docstrings, examples, or roadmap statements after
behavior changes.

## Refactoring

A refactor should do at least one of the following:

- reduce duplication
- remove an unsafe pattern
- replace implicit behavior with typed structure
- simplify an extension point
- improve contract stability

Avoid refactors that mainly rename symbols, add indirection, or broaden scope
without reducing real complexity.
