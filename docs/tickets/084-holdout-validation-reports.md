# Ticket 084: Holdout Validation Reports

## Goal

Prevent false confidence by separating calibration performance from validation performance.

## Current Gap

There is no holdout validation workflow or report that distinguishes calibration fit quality from generalization quality.

## Scope

- Add train/validation split handling for calibration datasets.
- Generate validation reports that include:
  - number of flights used for calibration
  - number of holdout flights
  - mission-level error metrics
  - phase-level error metrics
  - worst-case error
  - known invalid conditions
- Version and store validation reports as artifacts.

## Integration Requirements

- Holdout reports must reference the same mission, vehicle, terrain, wind,
  scenario, calibration, and trace artifacts used to generate them.
- Reports should compare baseline deterministic runs and calibrated runs through
  the existing estimator/scenario output contracts.
- Add examples showing a complete holdout workflow from YAML inputs through
  validation report output.
- Keep report generation deterministic for a fixed dataset split.

## Acceptance Criteria

- Calibration and validation results are reported separately.
- Holdout validation quality can be reviewed without inspecting raw logs manually.
- Holdout reporting composes with existing YAML-configured missions, assets,
  calibration artifacts, and scenario behavior.

## Out of Scope

- Complex statistical modeling.
- Cross-validation framework beyond what is needed for a first honest validation report.
