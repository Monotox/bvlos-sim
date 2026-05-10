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

## Acceptance Criteria

- Calibration and validation results are reported separately.
- Holdout validation quality can be reviewed without inspecting raw logs manually.

## Out of Scope

- Complex statistical modeling.
- Cross-validation framework beyond what is needed for a first honest validation report.
