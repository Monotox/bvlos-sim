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

## Integration Requirements

- Calibration profiles must layer on top of existing vehicle YAML rather than
  replacing vehicle profiles.
- Calibration artifacts should be selectable by `estimate`, `scenario`, API, and
  validation workflows through explicit configuration.
- Add examples that pair base vehicle YAML, calibration artifacts, mission YAML,
  terrain, wind, and validation data.
- Keep fitted values traceable to source logs, normalized traces, validation
  reports, and tool versions.
- Preserve deterministic behavior for a fixed calibration artifact.

## Acceptance Criteria

- A calibration dataset can produce a versioned calibration artifact without changing core estimator logic.
- Fitted parameters are separated from raw manufacturer/default profile values.
- Calibrated runs compose with existing mission, vehicle, terrain, wind,
  geofence, landing-zone, energy, and scenario behavior.

## Out of Scope

- Online auto-tuning.
- Black-box model replacement.
