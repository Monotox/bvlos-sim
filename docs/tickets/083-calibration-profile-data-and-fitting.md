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

## Implementation

**Status:** implemented

### New files

| File | Purpose |
|---|---|
| `schemas/calibration.py` | `CalibratedParameter`, `CalibratedParameterName`, `CalibrationProvenance`, `CalibrationProfile` (schema version `calibration-profile.v1`) |
| `adapters/calibration/fitter.py` | `fit_calibration_profile`, `CalibrationInput` — deterministic parameter-fitting engine |
| `adapters/calibration/apply.py` | `apply_calibration`, `CalibrationMismatchError` — the opt-in apply seam |
| `adapters/calibration/io.py` | `write_calibration_profile`, `load_calibration_profile`, `load_and_apply_calibration` |
| `adapters/calibration/__init__.py` | Public package |
| `adapters/calibration_markdown.py` | `render_calibration_markdown` — Markdown report renderer |
| `adapters/commands/calibrate.py` | `calibrate` CLI command |
| `examples/calibration/quadplane_v1_calibration.json` | Deterministically generated example artifact |
| `examples/calibration/README.md` | Example pairing base vehicle + trace + artifact |
| `tests/test_calibration.py` | 22 tests |

`schemas/__init__.py` exports the calibration models; `adapters/cli.py` registers
the `calibrate` command. `estimate`, `scenario`, and `validate` gain an opt-in
`--calibration PATH` flag.

### Calibration artifact

A `calibration-profile.v1` artifact *layers on* a base vehicle: it carries
`base_vehicle_id` (never a full vehicle profile) and a list of fitted parameter
records. Each record holds the fitted value, the observed sample range
(`confidence_low`/`confidence_high`), the population `spread`, `sample_count`,
the deterministic `calibration_dataset_version`, the `applicable_conditions`
envelope, and a human-readable `derivation`. Provenance carries `tool_version`,
the sorted `source_trace_ids`, and any linked `validation_report_ids`. All models
use `extra="forbid"`.

### The fitting approach

`fit_calibration_profile` is pure and deterministic — the same base vehicle and
the same ordered trace/segmentation pairs always produce byte-identical canonical
JSON. It reuses Ticket 081 segmentation as the phase bridge and touches no core
estimator formula:

- **cruise_speed_mps** — mean groundspeed over `transit`-phase trace records.
- **climb_rate_mps** / **descent_rate_mps** — mean vertical rate over records
  whose finite-difference rate clears the segmenter's climb/descent threshold;
  descent stored as a positive magnitude.
- **max_station_keep_wind_mps** — maximum wind speed observed while holding
  position during `loiter_dwell` segments (the demonstrated authority).

Parameters with no supporting samples are reported in `notes`, never fabricated.
Energy coefficients are deferred (the energy model has no fitting surface yet).

### The apply seam

`apply_calibration(vehicle, calibration)` returns a copy of the vehicle with only
the calibrated `PerformanceProfile` fields overridden, re-validated through
`VehicleProfile` (so an override that breaks an invariant — e.g. cruise above
`max_speed_mps` — is rejected). It is opt-in: with no parameters it returns the
base vehicle unchanged, and a `base_vehicle_id` that does not match the vehicle's
`vehicle_id` is rejected (`CalibrationMismatchError`). `load_and_apply_calibration`
maps both failure modes onto `InputLoadError` so the wired commands report them as
invalid input.

### CLI usage

```bash
# Fit a calibration profile from a base vehicle + one or more traces
bvlos-sim calibrate VEHICLE.yaml TRACE.json [TRACE2.json ...]          # Markdown
bvlos-sim calibrate VEHICLE.yaml TRACE.json --format json -o cal.json  # envelope

# Run any of these calibrated (opt-in; behaviour is unchanged when omitted)
bvlos-sim estimate MISSION.yaml VEHICLE.yaml --calibration cal.json
bvlos-sim scenario SCENARIO.yaml --calibration cal.json
bvlos-sim validate MISSION.yaml VEHICLE.yaml TRACE.json --calibration cal.json
```

Error handling mirrors `validate`: `InputLoadError` → exit 11, output-write
failure → exit 13.

### Out of scope (kept for later)

Online auto-tuning, black-box model replacement, and energy-coefficient fitting
are not part of this ticket. Held-out validation reporting is Ticket 084.
