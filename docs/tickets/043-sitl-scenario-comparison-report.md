# Ticket 043: SITL Scenario Comparison Report

## Status

Implemented.

## Goal

Compare deterministic bvlos-sim scenario expectations against ArduPilot SITL
evidence and emit a versioned report that explains agreement, drift, and
unsupported comparisons.

## Implementation Status

Implemented. The project now turns `sitl-evidence.v1` bundles into
`sitl-comparison.v1` reports through `estimate --sitl-evidence` and
adapter-level Python APIs.

## Scope

- Build comparison reports from evidence bundles emitted by Ticket 042.
- Compare deterministic scenario assertions, uploaded mission item count,
  telemetry record count, heartbeat presence, adapter lifecycle events,
  simulator lifecycle events, and position proximity for observed
  `GLOBAL_POSITION_INT` telemetry.
- Report matched, drifted, missing, unsupported, and skipped comparison
  outcomes.
- Add deterministic position tolerance handling with a default tolerance of
  500 m.
- Emit canonical JSON and Markdown comparison reports.
- Add synthetic unit tests and a live ArduPilot SITL integration smoke test.
- Document the distinction between SITL consistency checks and real-world
  validation.

## Implemented API

Schema models live in `schemas/sitl_comparison.py` and are exported through
`schemas/__init__.py`:

- `SITL_COMPARISON_SCHEMA_VERSION`
- `SitlComparisonOutcome`
- `SitlComparisonSummary`
- `SitlComparisonItem`
- `SitlComparisonReport`

Adapter-level report construction and rendering live in `adapters/`:

- `build_sitl_comparison_report(...)`
- `render_sitl_comparison_json(...)`
- `render_sitl_comparison_markdown(...)`
- `compare_sitl_evidence_bundle(...)`

The implementation keeps helper builders private to the adapter layer. It does
not import SITL comparison logic into schemas or estimator core modules.

CLI rendering is available through the existing `estimate` command:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml \
  --sitl-evidence /tmp/sitl-evidence.json \
  --comparison-id pipeline-demo-sitl-comparison \
  --position-tolerance-m 500 \
  --output /tmp/sitl-comparison.json
```

The `estimate` path supports JSON and Markdown via `--format` and writes to
stdout or `--output`, matching the normal estimator report workflow.

## Report Dimensions

`sitl-comparison.v1` reports include items in this order:

1. `bundle_completeness`
2. `assertion:<assertion_id>` for each deterministic scenario assertion
3. `mission_item_count`
4. `telemetry_record_count`
5. `heartbeat_observed`
6. `adapter_lifecycle`
7. `simulator_lifecycle`
8. `position:timeline_index_<index>` or one `position_proximity` unsupported
   item when position telemetry is unavailable

Contract-only evidence bundles skip telemetry-dependent dimensions while still
reporting deterministic scenario assertions.

## Summary Rules

The report summary is:

- `unsupported` when no matched, drifted, or missing comparisons ran
- `failed` when any supported comparison is missing
- `drifted` when at least one supported comparison drifted and none are missing
- `passed` otherwise

## Integration Requirements

- Use deterministic `scenario` outputs as the expected behavior source.
- Reuse report/envelope conventions established by estimator, scenario, and
  uncertainty outputs.
- Keep comparison reports adapter-level; do not change core estimator result
  semantics solely for SITL.
- Ensure unsupported comparisons are explicit instead of silently omitted.
- Keep the path open for validation-track tickets 080-084 to reuse telemetry
  normalization concepts.

## Acceptance Criteria

- A deterministic scenario can be compared against a SITL evidence bundle.
  Implemented.
- Comparison output identifies matched, missing, drifted, skipped, and
  unsupported observations. Implemented.
- Reports are reproducible for a given evidence bundle and tolerance
  configuration. Implemented.
- SITL comparison does not claim real-world calibration or operational
  approval. Implemented.

## Out of Scope

- Real-world flight-log validation.
- Calibration profile fitting.
- Regulatory compliance scoring.
- Live UTM, Remote ID, or traffic integrations.
