# Ticket 083: Calibration Profiles and Parameter Fitting

## Goal

Tune model parameters from observed flights without rewriting core formulas.

## Current Gap

There is no calibration data format and no fitter for turning observed flights into updated profile parameters.

## Scope

- Add calibration profile data format separate from base vehicle profile.
- Fit a narrow first parameter set:
  - cruise speed
  - climb rate
  - descent rate
  - station-keep wind authority
  - phase energy coefficients later when energy model exists
- Record for each fitted parameter:
  - fitted value
  - confidence range or spread
  - sample count
  - calibration dataset version
  - applicable conditions
- Keep calibration artifacts versioned and reproducible.

## Acceptance Criteria

- A calibration dataset can produce a versioned calibration artifact without changing core estimator logic.
- Fitted parameters are separated from raw manufacturer/default profile values.

## Out of Scope

- Online auto-tuning.
- Black-box model replacement.
