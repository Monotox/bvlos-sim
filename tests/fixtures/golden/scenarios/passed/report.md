# Scenario Report

- Scenario: `pipeline-passed-v1`
- Status: `passed`
- Envelope schema: `scenario-report.v2`
- Tool version: `0.22.0`

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
- mission: `yaml` sha256 `7bab3b2b9b996564f04f80c9cbb92051e2e187f2d4198b355e0939e9eec4473c`
- vehicle: `yaml` sha256 `4067f6697bba308915271afc95bf273ae7dc7637f3d921c71ac30b15a26453e5`

## Estimate Summary

- Horizontal distance m: `707.0645449`
- Vertical distance m: `240.0`
- Path distance m: `787.0645449`
- Time s: `169.82027517`
- Legs: `5`

## Energy Feasibility

- Feasible: `true`
- Total energy Wh: `41.50531217`
- Battery capacity Wh: `900.0`
- Usable energy Wh: `675.0`
- Reserve threshold percent: `25.0`
- Reserve threshold Wh: `225.0`
- Reserve at landing Wh: `858.49468783`
- Reserve at landing percent: `95.38829865`
- Energy legs: `5`
