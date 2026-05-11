# Scenario Report

- Scenario: `pipeline-failed-v1`
- Status: `failed`
- Envelope schema: `scenario-report.v2`
- Tool version: `0.2.0`

## Assertion Results

- `estimate-succeeds` `passed`: Estimate status is 'success' (success).
- `time-too-short` `failed`: 'estimate.total_time_s' field_lt 10.0 not satisfied (actual: 169.820275172818).
- `unsupported-field` `unsupported`: Assertion is not supported: Field path 'estimate.unknown_field' is not supported in scenario.v1. See docs for supported field paths.
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
- scenario: `yaml` sha256 `1ec836db62b982e3d8f3be3dbd3367ea18f76026b8f82c21f6cd156fa26fcdf0`
- mission: `yaml` sha256 `7bab3b2b9b996564f04f80c9cbb92051e2e187f2d4198b355e0939e9eec4473c`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Estimate Summary

- Horizontal distance m: `707.0645448969212`
- Vertical distance m: `240.0`
- Path distance m: `707.0645448969212`
- Time s: `169.820275172818`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `41.50531217438002`
- Battery capacity Wh: `900.0`
- Usable energy Wh: `675.0`
- Reserve threshold percent: `25.0`
- Reserve threshold Wh: `225.0`
- Reserve at landing Wh: `858.49468782562`
- Reserve at landing percent: `95.38829864729111`
- Energy legs: `5`
