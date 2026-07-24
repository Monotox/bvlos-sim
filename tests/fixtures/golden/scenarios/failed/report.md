# Scenario Report

- Scenario: `pipeline-failed-v1`
- Status: `failed`
- Assertions: 2 passed, 1 failed, 0 skipped, 1 unsupported
- Envelope schema: `scenario-report.v3`
- Tool version: `0.0.0-test`

## Assertion Results

- `estimate-succeeds` `passed`: Estimate status is 'success' (success).
- `time-too-short` `failed`: 'estimate.total_time_s' field_lt 10.0 not satisfied (actual: 169.82027517).
- `unsupported-comparison` `unsupported`: Assertion is not supported: Field 'estimate.energy.is_feasible' has a non-numeric value; cannot apply 'field_lt' comparison.
- `policy-action` `passed`: Policy action for event 'link-lost' is 'rtl' as expected.

## Timeline

- [0] t=0.00s (52.00000, 4.00000) alt=12.0m
- [1] t=26.67s (52.00000, 4.00000) alt=92.0m [takeoff]
- [2] t=40.00s (52.00100, 4.00200) alt=132.0m [wp1]
- [3] t=49.82s (52.00200, 4.00400) alt=132.0m [loiter]
- [4] t=109.82s (52.00200, 4.00400) alt=132.0m [loiter]
- [5] t=169.82s (52.00000, 4.00000) alt=12.0m [rtl]

## Event Outcomes

- `start` (observe): fired at timeline[0]
- `link-lost` (lost_link): fired at timeline[2]
  - Policy: `rtl` after `30.0s` loiter at t=`70.00s` (52.00200, 4.00400) alt=`132.0m`

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Provenance

- Scenario runner API: `scenario_runner.run_scenario`
- scenario: `yaml` sha256 `ad795e8222b72a5146777901cddeb35582a8dfcaf34e5aa187347abcfb858222`
- mission: `yaml` sha256 `f51ebfee7ac0a53d5f1f010d15fbc838d171388865d762f3732fdb113963b445`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Estimate Summary

- Horizontal distance m: `707.06`
- Vertical distance m: `240.00`
- Path distance m: `787.06`
- Time: `2m 49s (169.82 s)`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `45.39`
- Battery capacity Wh: `900.00`
- Usable energy Wh: `675.00`
- Reserve threshold percent: `25.00`
- Reserve threshold Wh: `225.00`
- Reserve at landing Wh: `854.61`
- Reserve at landing percent: `94.96`
- Energy legs: `5`

## Warnings

- `LOITER_ASSUMED_ZERO_GROUND_DISTANCE`: Loiter dwell modeled as station-keep hold with zero ground-path distance in estimator v1.
- `ENERGY_MODEL_UNCALIBRATED`: vehicle.calibration_status is not declared, so every energy figure below rests on unvalidated coefficients. Fit a calibration profile from a real flight trace (bvlos-sim calibrate) and pass it with --calibration, or set calibration_status to manufacturer_derived once the values come from published data.
