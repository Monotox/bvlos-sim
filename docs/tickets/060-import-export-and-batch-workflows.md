# Ticket 060: Import/Export and Batch Workflows

## Goal

Improve engineering workflow and interoperability.

## Current Gap

There is no plan importer, no batch execution, and no report comparison tooling.

## Scope

- Add QGroundControl `.plan` importer.
- Add import diagnostics.
- Add batch-run support.
- Add report comparison/diff tools.
- Add performance profiling.
- Expand mission/action compatibility where required by imports.

## Integration Requirements

- Importers must emit existing mission YAML/JSON schema shapes rather than a
  separate internal plan format.
- Batch runs must execute the same `estimate` and `scenario` behavior used by
  single-file CLI runs.
- Batch manifests should reference existing mission, vehicle, scenario, terrain,
  wind, geofence, and landing-zone files.
- Add example batch inputs that combine previously implemented asset types.
- Report comparison must understand existing estimator and scenario envelopes,
  including terrain, wind-grid, landing-zone, geofence, energy, and policy
  sections.

## Acceptance Criteria

- Teams can import plans, run batches, and compare outputs deterministically.
- Imported and batch-run missions compose with existing YAML assets and command
  behavior.

## Out of Scope

- Live GCS synchronization.
- UTM integration.
