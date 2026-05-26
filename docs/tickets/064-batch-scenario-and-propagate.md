# Ticket 064 — Batch Scenario and Batch Propagate Modes

## Status: Planned

## Problem

`BatchManifest` (batch.v1) only supports estimate runs. There is no way
to batch-run scenarios or stochastic propagations from a manifest file.
A CI pipeline that wants to run 20 scenarios against one vehicle change
must script individual CLI calls with no structured output. Real teams
maintaining a library of scenarios for regression testing need this.

## Acceptance Criteria

1. `BatchManifest` gains an optional `run_type` field:
   `"estimate"` (default), `"scenario"`, or `"propagate"`.
2. For `run_type: "scenario"`, each `BatchRun` references a scenario
   file instead of (or in addition to) mission + vehicle.
3. For `run_type: "propagate"`, each `BatchRun` references a stochastic
   plan file.
4. `bvlos-sim batch manifest.yaml` detects `run_type` and dispatches to
   the appropriate runner.
5. The batch table output is extended with `status` columns appropriate
   for each run type (scenario pass/fail, propagate feasibility rate).
6. The `--output` flag writes per-run envelopes to a directory (one JSON
   file per run ID).
7. Existing `batch.v1` manifests without `run_type` default to estimate
   and are fully backwards compatible.
8. At least one CLI-level test per run type.

## Scope

- `schemas/batch.py` — add `run_type` field and scenario/propagate
  run variants
- `adapters/batch_support.py` — dispatch by run type
- `adapters/batch_io.py` — schema version bump or extension
- `adapters/cli_batch_support.py` — output per-run files
- `adapters/cli.py` — batch command update
- `docs/USAGE.md` — document new run types
- `tests/` — new batch scenario and propagate tests

## Notes

- The manifest format version should remain `batch.v1` with a new
  optional field rather than bumping to `batch.v2`, as long as old
  manifests are fully compatible.
- Per-run output files follow the same envelope format as the individual
  commands (scenario-envelope.v2, stochastic-envelope.v1).
