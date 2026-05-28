# Ticket 085: QGC Convert Vehicle Profile Selection

## Goal

Make `bvlos-sim convert` produce mission.v5 YAML with an explicit,
operator-supplied `vehicle_profile` instead of the current
`FIXME-vehicle-profile` placeholder.

## Motivation

The QGC `.plan` importer is meant to help real users turn a flight plan into a
usable bvlos-sim mission. Today the converted mission always contains:

```yaml
vehicle_profile: FIXME-vehicle-profile
```

The metadata note asks users to replace it manually, but that is easy to miss
and makes the generated file feel unfinished. It can also confuse batch and
scenario workflows that preserve mission metadata for provenance. Conversion
should require the operator to name the intended vehicle profile before the file
is written.

## Inputs

```
bvlos-sim convert <plan>
    --vehicle-profile PROFILE_ID
    [--output FILE]
```

`PROFILE_ID` is the mission-level `vehicle_profile` string to write into the
converted mission. It is not a vehicle YAML path; the existing `estimate` and
`scenario` commands continue to receive vehicle YAML files separately.

## Behavior

- `--vehicle-profile` is required for `convert`.
- Missing or blank `--vehicle-profile` exits with `INVALID_INPUT` (11) and a
  clear error message.
- `adapters.qgc_plan` takes the vehicle profile as an explicit parameter and
  never writes `FIXME-vehicle-profile`.
- The converted mission metadata note no longer mentions a placeholder; it only
  tells users to review converted values before operational use.
- Existing conversion diagnostics for unsupported or normalized MAVLink commands
  remain unchanged.

## Implementation Approach

Thread a `vehicle_profile: str` parameter through the QGC conversion boundary:

```python
def parse_qgc_plan(
    raw: dict[str, object],
    *,
    vehicle_profile: str,
) -> tuple[dict[str, object], list[ConvertDiagnostic]]:
    ...

def load_and_convert_plan(
    path: Path,
    *,
    vehicle_profile: str,
) -> tuple[dict[str, object], list[ConvertDiagnostic]]:
    ...
```

`adapters/commands/convert.py` validates the option before calling the adapter.
The core parser should not know about Typer or exit codes.

## Files to Create or Modify

| File | Change |
|------|--------|
| `adapters/qgc_plan.py` | Replace hardcoded placeholder with explicit parameter |
| `adapters/commands/convert.py` | Add and validate `--vehicle-profile` option |
| `tests/test_qgc_convert.py` | Add CLI and parser acceptance coverage |
| `docs/USAGE.md` | Document the required convert option |
| `docs/tickets/README.md` | Mark implemented when done |

## Acceptance Criteria

1. `bvlos-sim convert plan.plan --vehicle-profile quadplane_v1` emits
   `vehicle_profile: quadplane_v1`.
2. Converted output contains no `FIXME-vehicle-profile` text in either mission
   fields or metadata notes.
3. Missing or blank `--vehicle-profile` exits with code 11 and a clear message.
4. Existing QGC conversion diagnostics are still emitted to stderr.
5. Parser-level tests verify `load_and_convert_plan(..., vehicle_profile=...)`
   threads the profile into the assembled mission.
6. `docs/USAGE.md` shows the new option in the convert section.
