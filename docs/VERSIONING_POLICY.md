# Versioning Policy

This policy defines the public contracts that bvlos-sim treats as stable within
a published version.

## Public Contracts

Current public contracts:

- package-root `estimator` imports
- mission input schema: `mission.v6`
- vehicle input schema: `vehicle.v4`
- scenario input schema: `scenario.v1`
- uncertainty input schema: `uncertainty.v1`
- stochastic propagation input schema: `stochastic.v1`
- batch manifest input schema: `batch.v1`
- geofence input schema: `geofence-geojson.v1`
- landing-zone input schema: `landing-zone-geojson.v1`
- population-density input schema: `population-grid.v1`
- estimator JSON envelope: `estimator-envelope.v7`
- scenario JSON envelope: `scenario-report.v2`
- uncertainty JSON envelope: `uncertainty-report.v1`
- stochastic propagation envelope: `stochastic-envelope.v1`
- SITL evidence bundle: `sitl-evidence.v1`
- SITL comparison report: `sitl-comparison.v1`
- CLI exit-code semantics (enumerated per command in
  [`CLI_EXIT_CODES.md`](CLI_EXIT_CODES.md)), including the `14` (`CANCELLED`)
  signal-abort code and the atomic-output-write guarantee
- supported Markdown report shape covered by golden fixtures

Internal module layout is not a public contract. Refactors are allowed when the
public contracts remain compatible.

## Compatibility Rules

Within a published schema or envelope version, do not accidentally:

- remove public fields
- rename public fields
- change enum values
- change status meanings
- change CLI exit-code meanings
- change partial-result semantics
- change canonical JSON rendering behavior
- expose raw dependency exception text in machine-facing outputs

Intentional contract changes must update all of the following in the same
change:

1. the relevant schema or envelope version
2. this policy, if the contract list or rules change
3. golden fixtures
4. regression tests
5. user-facing documentation

## Unknown Fields

Structured models use strict validation and reject unknown fields:

- mission schema objects
- vehicle schema objects
- scenario schema objects
- estimator result-envelope objects
- scenario result-envelope objects
- SITL evidence-bundle objects
- SITL comparison-report objects

Free-form maps are explicit exceptions:

- mission `metadata`
- route item `metadata`
- vehicle `metadata`
- vehicle resource-system `metadata`
- mission link-system `metadata`
- scenario link-system `metadata`
- scenario `metadata`
- estimator failure `context`
- estimator result `metadata`

Consumers should ignore unknown keys inside documented free-form maps unless
they rely on a separately documented key.

## Golden Fixtures

Golden fixtures pin representative public outputs:

- successful estimator result
- infeasible estimator result
- partial estimator result
- passed scenario result
- failed scenario result
- stochastic propagation result

Fixtures cover:

- canonical estimator JSON
- estimator Markdown
- canonical scenario JSON
- scenario Markdown
- canonical stochastic propagation JSON

Golden fixture updates should be reviewed as contract changes, not incidental
snapshot churn.

## Package-Root API

Callers should prefer package-root imports:

```python
from estimator import estimate_mission_distance_time
from estimator import try_estimate_mission_distance_time
from estimator import run_scenario
```

Symbols exported from `estimator.__all__` are treated as the stable public
Python surface for the current release line.
