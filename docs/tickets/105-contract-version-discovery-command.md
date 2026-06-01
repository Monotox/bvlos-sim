# Ticket 105: Contract-Version Discovery Command

## Status

Implemented.

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

## Implementation

### New files

| File | Purpose |
|------|---------|
| `adapters/commands/schema_versions.py` | The `schema_versions` command: builds the `tool_version` / `output_envelopes` / `input_schemas` map from imported constants and prints it as canonical JSON. |
| `tests/test_schema_versions.py` | Exit-code, JSON-shape, drift-guard, alias-equivalence, no-file-argument, determinism, and `--version`-unchanged tests. |

### Command and alias

`schema-versions` is registered in `adapters/cli.py:_register_commands()` with
both its canonical name and the `contracts` alias, mirroring how `size-battery`
is registered with an explicit name:

```python
app.command("schema-versions")(schema_versions)
app.command("contracts")(schema_versions)
```

The command takes no arguments or options. It loads nothing, calls
`tool_version()`, renders the version map with `render_canonical_json` (sorted
keys, stable float precision, trailing newline), and exits `0`. `--version` is
untouched and still prints the plain `bvlos-sim <version>` line.

### Constants sourced (no string is restated)

Every printed version is imported from the module that owns it, so the map cannot
drift from what a real run emits; `tests/test_schema_versions.py` asserts the
printed value equals each imported constant.

- Output envelopes: `RESULT_ENVELOPE_SCHEMA_VERSION`,
  `SCENARIO_REPORT_SCHEMA_VERSION`, `UNCERTAINTY_REPORT_SCHEMA_VERSION`,
  `STOCHASTIC_ENVELOPE_SCHEMA_VERSION`, `SORA_ENVELOPE_SCHEMA_VERSION`,
  `BATTERY_SIZING_REPORT_SCHEMA_VERSION`, `SITL_EVIDENCE_SCHEMA_VERSION`,
  `SITL_COMPARISON_SCHEMA_VERSION`.
- Input schemas: `MISSION_SCHEMA_VERSION`, `VEHICLE_SCHEMA_VERSION`,
  `GEOFENCE_SCHEMA_VERSION`, `LANDING_ZONE_SCHEMA_VERSION`,
  `TERRAIN_SCHEMA_VERSION`, `POPULATION_SCHEMA_VERSION`, `WIND_GRID_SCHEMA_VERSION`,
  `SCENARIO_INPUT_SCHEMA_VERSION`, `UNCERTAINTY_INPUT_SCHEMA_VERSION`,
  `STOCHASTIC_INPUT_SCHEMA_VERSION`, and `batch.v1`.
- `batch.v1` has no named module constant — it is a `Literal` field on
  `schemas.batch.BatchManifest`. Rather than restate the string, the command (and
  the test) extract it from the field annotation with
  `typing.get_args(BatchManifest.model_fields["format_version"].annotation)[0]`,
  so the discovery map stays bound to what the loader actually accepts.

### Beyond the spec's eight output contracts

The spec listed eight core output/envelope contracts. Five more report/artifact
contracts have been added to the repo since this ticket was written; they are
included for completeness, each sourced from its own constant:
`VALIDATION_REPORT_SCHEMA_VERSION` (`validation-report.v1`),
`CALIBRATION_PROFILE_SCHEMA_VERSION` (`calibration-profile.v1`),
`FLIGHT_TRACE_SCHEMA_VERSION` (`flight-trace.v1`),
`PHASE_SEGMENT_SCHEMA_VERSION` (`phase-segments.v1`), and
`SORA_ASSESSMENT_SCHEMA_VERSION` (`sora-assessment.v1`). Including them does not
complicate the drift test (each is just another `imported == printed` assertion),
and it makes the discovery output a complete picture of the published contracts.

### Deliberately left out

The two data-completeness nits in the Notes above — the `obstacles` input-schema
version omitted from the live envelope's `_input_schema_versions()`, and the
missing battery-sizing input schema-version field — are out of scope here. Each
would change a published envelope and needs its own golden-fixture and version
review; the discovery command reports only what the envelopes emit today.
