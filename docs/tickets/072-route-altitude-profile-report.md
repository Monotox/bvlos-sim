# Ticket 072: Route Altitude Profile Report

## Goal

Add a `--format profile` output mode to the `estimate` and `scenario`
commands that renders a markdown-formatted altitude vs. distance chart
showing the planned route altitude alongside the terrain floor (when a
terrain provider is available) and the minimum clearance margin at each leg.
Drone operators doing pre-flight terrain clearance review can run a single
command and immediately see the vertical safety profile without loading a GIS
tool.

## Motivation

Terrain clearance is the most critical safety check for BVLOS operations in
hilly or mountainous terrain. Today the tool computes terrain-corrected
altitudes but only exposes them as numeric fields inside the JSON envelope.
A `--format profile` mode turns those numbers into a visual cross-section
report that is:

- Readable in a terminal without any dependencies
- Embeddable in a CI/CD pre-flight report as a Markdown artifact
- Immediately interpretable by a non-engineer operations reviewer

A typical flight over Alpine terrain might have six legs. The profile report
shows whether leg 3 passes within 50 m of a hilltop, which the numeric
envelope buries in a 200-line JSON object.

## Output Format

A Markdown document (`profile.md`) with two sections.

### 1 — Altitude Table

A table with one row per leg:

```markdown
## Route Altitude Profile

| Leg | ID        | Phase   | Dist m  | Start AMSL m | End AMSL m | Terrain m | Clearance m |
|-----|-----------|---------|--------:|-------------:|-----------:|----------:|------------:|
|   0 | takeoff   | TAKEOFF |    80.0 |         12.0 |       92.0 |      12.0 |        80.0 |
|   1 | wp1       | TRANSIT |   340.0 |         92.0 |      212.0 |      85.0 |       127.0 |
|   2 | loiter    | LOITER  |   251.2 |        212.0 |      212.0 |      91.0 |       121.0 |
|   3 | rtl       | RTL     |   620.0 |        212.0 |       12.0 |      12.0 |       200.0 |
```

When no terrain provider is available, the `Terrain m` and `Clearance m`
columns show `—`.

### 2 — ASCII Cross-Section

A 40×10 character ASCII art elevation profile showing altitude (Y axis)
vs cumulative distance (X axis), with terrain floor drawn as `▄` blocks
and route drawn as `─` dashes and `╮`/`╰` angle markers at climb/descent.

```
AMSL m
 212 ┤          ╭──loiter──╮
     │     wp1 ╯            ╰ rtl
  92 ┤   ╭╯
  12 ┤ ╭─╯takeoff          ▄▄▄▄     ╰─╮ 12
     └─────────────────────────────────┘
       0                 1.0 km      1.6 km
```

(Exact rendering TBD; the goal is quick visual triage, not publication quality.)

## Implementation

### 1 — `adapters/profile_markdown.py` (new)

```python
def render_profile_markdown(envelope: EstimatorResultEnvelope) -> str:
    """Render a terrain clearance profile report as Markdown."""
```

Inputs needed (all available on `EstimatorResultEnvelope.result`):
- `result.legs`: `LegEstimate` list — start/end AMSL altitudes, phase, distance
- `result.metadata.terrain_provider_id`: detect whether terrain is active

The terrain elevation at each leg endpoint is not stored on `LegEstimate`
today (it is computed transiently inside the estimator). Two implementation
options:

**Option A — Read from metadata**: Add `terrain_elevation_start_m` and
`terrain_elevation_end_m` optional fields to `LegEstimate` in
`estimator/core/results.py`. Populate them in `fidelity_v1.py` and
`fidelity_v2.py` when a terrain provider is set. This is the preferred
approach as it makes the data available for JSON consumers too.

**Option B — Re-query terrain at render time**: Pass `terrain_provider` to
the profile renderer. The renderer calls `provider.elevation_at(lat, lon)`
for each leg endpoint. This avoids schema changes at the cost of requiring
the terrain provider in the adapter layer.

Start with Option B for simplicity; plan a follow-up to promote terrain
elevations to `LegEstimate` fields in a later ticket.

### 2 — Extend `OutputFormat` and `DocumentOutputFormat`

Add `PROFILE = "profile"` to the output format enum in `adapters/cli.py` (or
wherever the format enum lives). Wire it into the `estimate` and `scenario`
render paths.

### 3 — `adapters/cli.py` changes

In `_render_estimate_command_output`, handle `OutputFormat.PROFILE`:

```python
elif format == OutputFormat.PROFILE:
    terrain_provider = mission_assets.terrain_provider
    return render_profile_markdown(envelope, terrain_provider=terrain_provider)
```

### 4 — Tests

- `tests/test_profile_markdown.py`:
  - `test_profile_table_has_one_row_per_leg`: verify row count
  - `test_profile_table_shows_clearance_when_terrain_present`: verify
    Clearance m column is populated
  - `test_profile_table_shows_dashes_when_no_terrain`: verify `—` in
    Terrain/Clearance columns
  - `test_profile_report_contains_altitude_table_header`: verify heading text
  - `test_profile_report_ends_with_newline`
  - CLI integration test: `estimate --format profile` exits 0 and output
    starts with `## Route Altitude Profile`

### 5 — Documentation

Update `docs/USAGE.md` with a `--format profile` section showing example
output. Add a note that terrain data must be referenced in `assets.terrain_file`
for the Clearance column to be populated.

## Integration

Reads only from `EstimatorResultEnvelope.result.legs` and the optional terrain
provider, both already in scope at the CLI `estimate` render callsite. Does not
touch the core estimator or any schema versions. Can land without golden
fixture changes.

## Acceptance Criteria

- `estimate --format profile` exits 0 and produces a Markdown table with one
  row per route leg.
- `Terrain m` and `Clearance m` columns are populated when a terrain file is
  referenced and dashes (`—`) when not.
- `scenario --format profile` works identically using the scenario result's
  embedded estimate.
- All existing estimate and scenario tests continue to pass.
