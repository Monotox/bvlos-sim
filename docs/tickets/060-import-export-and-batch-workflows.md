# Ticket 060: Import/Export and Batch Workflows

## Goal

Improve engineering workflow and interoperability.

Status: implemented for QGC plan conversion and batch estimate workflows.

## Delivered

- Added `bvlos-sim convert` for QGroundControl `.plan` to `mission.v5` YAML
  conversion.
- Added import diagnostics for unsupported QGC mission items and commands.
- Added `batch.v1` manifests and `bvlos-sim batch` for multi-run mission
  estimates.
- Added example `.plan` and batch manifest files.

## Integration Requirements

- Importers must emit existing mission YAML/JSON schema shapes rather than a
  separate internal plan format.
- Batch runs execute the same `estimate` behavior used by single-file CLI runs.
- Batch manifests reference existing mission, vehicle, terrain, wind, geofence,
  and landing-zone files.
- Add example batch inputs that combine previously implemented asset types.

## Acceptance Criteria

- Teams can import QGC plans and run estimate batches deterministically.
- Imported and batch-run missions compose with existing YAML assets and command
  behavior.

## Out of Scope

- Live GCS synchronization.
- UTM integration.
- Batch scenario runs.
- Report comparison/diff tooling.
- Performance profiling.
