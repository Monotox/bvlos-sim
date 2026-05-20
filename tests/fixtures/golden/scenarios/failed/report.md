# Scenario Report

- Scenario: `pipeline-failed-v1`
- Status: `failed`
- Envelope schema: `scenario-report.v2`
- Tool version: `0.22.0`

## Assertion Results

- `estimate-succeeds` `passed`: Estimate status is 'success' (success).
- `time-too-short` `failed`: 'estimate.total_time_s' field_lt 10.0 not satisfied (actual: 169.82027517).
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
- scenario: `yaml` sha256 `f38dbbadbcf404c969d8cee3cb8a32e378f52a57360b06092cef7c17a45913a0`
- mission: `yaml` sha256 `5a4e27cdb6453b5679faf29ace529db26cdabd0d8a1fb9ba18cbd111e17ac9c5`
- vehicle: `yaml` sha256 `8d6aa9d57a7125b48b16264741c45c3335f026acb19ecba8fe0e2b36fa3c7046`

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
