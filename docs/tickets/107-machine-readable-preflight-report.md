# Ticket 107: Machine-Readable Preflight Validation Report

## Status

Implemented.

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

## Implementation

### Envelope

`schemas/preflight_validation.py` defines `preflight-validation.v1`
(`PREFLIGHT_VALIDATION_SCHEMA_VERSION`): `PreflightValidationReport` (schema
version, `command`, overall `ok`, `files`, and a deterministic
`generated_at: null`), `FileCheck` (`path`, `role`, `ok`, `stage`, `error`), and
`PreflightError` (`code`, `message`, `detail`). All models are Pydantic v2 with
`ConfigDict(extra="forbid")`. `adapters/preflight_envelope.py` renders it through
the shared `render_canonical_json`, so the output matches every other envelope
and is byte-for-byte deterministic.

### Engine

`adapters/preflight.py` runs the real loaders and turns each into a `FileCheck`,
collecting every failure rather than aborting on the first. `_translate` maps
loader exceptions onto a stable `(stage, code)`: `schema` for schema/root-type
failures, `asset-load` for read/parse/format failures, with codes such as
`SCHEMA_VALIDATION_FAILED`, `ASSET_FILE_MISSING`, and `GEOJSON_PARSE_FAILED` (a
missing asset and a malformed one are distinct). `mission_asset_checks` validates
every referenced mission asset (geofence, landing-zone, terrain, population,
obstacle, wind-grid) by running its loader against the path resolved relative to
the mission file; `comms_coverage_file` is reserved and not checked.
`emit_preflight` prints the legacy plain-text lines when every file is valid, or
the JSON envelope under `--validate-format json`, and exits `0`/`11`.

### CLI flag choice — `--validate-format`, not `--format`

A separate `--validate-format` (enum `text`|`json`, default `text`) is added to
every command rather than overloading `--format`. On `estimate`, `scenario`,
`sample`, and `propagate` the existing `--format` controls *run* output and
already defaults to (or includes) `json`, so reusing it would either collide with
run output or make JSON the implicit preflight default — violating "plain text
stays the default". `--validate-format` is uniform across all commands and only
active in `--validate-only` mode.

### Commands

The eight commands that already had `--validate-only` (`estimate`, `scenario`,
`sample`, `propagate`, `batch`, `sora`, `convert`, `export`) now route their
validate-only path through the engine, and asset-consuming commands validate
referenced assets — closing the gap where a broken geofence path passed preflight
and failed only at run time. `calibrate`, `compare`, and `size-battery` gained
`--validate-only` plus the same JSON opt-in. The plain-text default output for
the all-valid case is unchanged, so existing validate-only tests pass unmodified.

### Coordination with Ticket 089

Ticket 089 (combined `preflight` command) is still planned; a note in its file
points its future `--validate-only --validate-format json` at this envelope so
there is exactly one machine-readable preflight path.

### Tests

`tests/test_preflight_validation.py` covers the schema (round-trip, extra-field
rejection, pinned version literal), per-command JSON envelopes for `estimate`,
`scenario`, `batch`, and `export` (valid, bad schema, missing asset, malformed
GeoJSON), text+json for `calibrate`, `compare`, and `size-battery`, the unchanged
plain-text default, and envelope determinism.
