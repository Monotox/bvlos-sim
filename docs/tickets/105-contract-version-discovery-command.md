# Ticket 105: Contract-Version Discovery Command

## Status

Planned.

## Goal

Let a consumer read the supported input and output contract versions without
running a job, so a backend can pin and check compatibility at startup instead of
inferring versions from a full run's envelope.

## Why This Matters

Every envelope already carries an envelope `schema_version` and a `tool_version`,
and `tool_version` is sourced reliably from `pyproject.toml`
(`adapters/version.py:26-36`), so a captured simulator version is trustworthy.
But `--version` prints only the tool version (`adapters/cli.py:83-86`), and the
schema-version constants are emitted exclusively from job-output builders. A
backend that wants to pin `estimator-envelope.v7` / `mission.v6` / `vehicle.v4`
has to run a real estimate to discover them, which is wasteful and couples
version discovery to a successful run.

## Scope

- Add a read-only `schema-versions` command (alias `contracts`), or a
  `--schema-version` eager flag, that prints canonical JSON: `tool_version` plus
  every output envelope version and every input schema version, then exits `0`
  without loading a mission.
- Source the map from the existing module constants so it cannot drift from the
  real envelopes:
  - outputs: `adapters/envelope.py:16` (`estimator-envelope.v7`),
    `adapters/scenario_envelope.py:18` (`scenario-report.v2`),
    `adapters/uncertainty_envelope.py:11` (`uncertainty-report.v1`),
    `adapters/stochastic_envelope.py:11` (`stochastic-envelope.v1`),
    `adapters/sora_envelope.py:11` (`sora-envelope.v1`),
    `adapters/battery_sizing_envelope.py:12` (`battery-sizing-report.v1`),
    `adapters/sitl/evidence.py:37` (`sitl-evidence.v1`), and the
    `sitl-comparison.v1` constant.
  - inputs: `adapters/envelope.py:17-23` plus `scenario.v1`, `uncertainty.v1`,
    `stochastic.v1`, and `batch.v1`.

## Acceptance Criteria

- `bvlos-sim schema-versions` prints canonical JSON with `tool_version` and all
  input/output contract versions and exits `0`, without loading any mission file.
- The printed versions are sourced from the same constants the envelopes use; a
  test asserts the printed map matches the constants so the two cannot drift.
- `--version` continues to print the plain `bvlos-sim <version>` line unchanged.

## Out of Scope

- A migration tool for upgrading files between versions — Ticket 090 covers that.

## Notes

- Two data-completeness nits surfaced while scoping this and are deliberately left
  out of the discovery command because each changes a published envelope and so
  needs its own golden-fixture and version review: `_input_schema_versions()`
  omits `obstacles` (`adapters/envelope.py:504`), and the battery-sizing envelope
  carries no input schema-version field. Track them separately if pursued.
