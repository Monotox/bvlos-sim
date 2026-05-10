# Ticket 032: Terrain-Referenced Altitude Execution

## Goal

Support mission legs whose altitude reference is terrain-relative while keeping
estimator outputs deterministic and auditable.

## Current Gap

Terrain-referenced altitude inputs are rejected as unsupported. The estimator
does not load terrain data, resolve ground elevation along a route, or report
terrain-derived altitude assumptions.

## Scope

- Add a deterministic terrain provider interface.
- Add at least one offline terrain-data adapter.
- Resolve terrain-relative route-item altitudes into AMSL altitudes.
- Add diagnostics when required terrain coverage is missing.
- Record terrain provider metadata in estimator outputs.
- Add focused schema, estimator, CLI, and golden-fixture coverage.

## Acceptance Criteria

- Missions using terrain-referenced altitude can run when terrain coverage is
  available.
- Missing or unsupported terrain data fails with structured diagnostics.
- Existing AMSL and relative-home behavior remains stable.

## Out of Scope

- Online terrain service calls during core estimation.
- Obstacle clearance modeling.
- Regulatory terrain/obstacle compliance claims.
