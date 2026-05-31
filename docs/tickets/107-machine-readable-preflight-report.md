# Ticket 107: Machine-Readable Preflight Validation Report

## Status

Planned.

## Goal

Give every run type a cheap, machine-readable pre-flight check so a caller can
validate inputs — including referenced GeoJSON assets — before queuing a long
job, and parse the result without scraping stdout.

## Why This Matters

A per-command `--validate-only` flag already exists on `estimate`, `scenario`,
`sample`, `propagate`, `batch`, `sora`, `convert`, and `export`: each loads and
schema-validates its inputs and exits `0` or `11`
(`adapters/commands/estimate.py:354-357` and the equivalent paths in the other
commands), so schema-validity preflight is already possible. Two gaps remain.
First, `--validate-only` prints only plain-text "OK" lines, so a backend must
scrape text to learn what failed. Second, in validate-only mode the mission's
GeoJSON/terrain/population assets are not checked, because asset loading runs
after the early exit — an invalid geofence passes preflight and fails only at run
time. The standalone `validate` command is unrelated: it is a predicted-vs-
observed accuracy report requiring a flight trace, not a preflight tool.

## Scope

- Add a `--format json` preflight envelope — for example `preflight-validation.v1`
  — emitted by the existing `--validate-only` path on each command: per-file
  ok/error, error stage and detail, and an overall pass flag.
- Move mission asset loading (`_populate_mission_assets`) ahead of the
  validate-only early exit, or add an explicit asset-check pass, so geofence,
  landing-zone, terrain, and population assets are validated in preflight.
- Add `--validate-only` to `calibrate`, `compare`, and `size-battery` for parity.
- Coordinate with Ticket 089: its combined `preflight` command should emit the
  same machine-readable report rather than text only.

## Acceptance Criteria

- `<command> --validate-only --format json` emits a `preflight-validation.v1`
  envelope and exits `0` (valid) or `11` (invalid) for estimate, scenario, sample,
  propagate, batch, sora, convert, and export.
- Referenced GeoJSON/terrain/population assets are validated in validate-only mode
  and reported per file.
- `calibrate`, `compare`, and `size-battery` accept `--validate-only`.
- The existing plain-text validate-only output stays the default; JSON is opt-in.

## Out of Scope

- Overloading the existing `validate` command, which is reserved for predicted-vs-
  observed validation reports.
- Running any estimator or scenario computation in validate-only mode; it stays a
  pure load-and-schema-check.
