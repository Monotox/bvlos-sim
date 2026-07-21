# Scenario Report

- Scenario: `pipeline-passed-v1`
- Status: `passed`
- Assertions: 3 passed, 0 failed, 0 skipped
- Envelope schema: `scenario-report.v3`
- Tool version: `0.0.0-test`

## Assertion Results

- `estimate-succeeds` `passed`: Estimate status is 'success' (success).
- `time-under-limit` `passed`: 'estimate.total_time_s' field_lt 3600.0 satisfied (actual: 169.82027517).
- `energy-feasible` `passed`: 'estimate.energy.is_feasible' == True (actual: True).

## Timeline

- [0] t=0.00s (52.00000, 4.00000) alt=12.0m
- [1] t=26.67s (52.00000, 4.00000) alt=92.0m [takeoff]
- [2] t=40.00s (52.00100, 4.00200) alt=132.0m [wp1]
- [3] t=49.82s (52.00200, 4.00400) alt=132.0m [loiter]
- [4] t=109.82s (52.00200, 4.00400) alt=132.0m [loiter]
- [5] t=169.82s (52.00000, 4.00000) alt=12.0m [rtl]

## Event Outcomes

- `start` (observe): fired at timeline[0]
- `loiter-reached` (observe): fired at timeline[3]
- `end` (observe): fired at timeline[5]

## Determinism

- Deterministic: `true`
- External network access used: `false`

## Provenance

- Scenario runner API: `scenario_runner.run_scenario`
- scenario: `yaml` sha256 `d2efe19af1b7572fca38796460f74333c561b6283f73d94e0bb32845e372ef46`
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
