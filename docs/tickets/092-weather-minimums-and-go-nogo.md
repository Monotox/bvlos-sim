# Ticket 092: Weather Minimums and Automatic GO/NO-GO

## Status

Planned.

## Goal

Add weather-limit fields to the mission schema and enforce them deterministically
against the forecast wind grid, emitting structured warnings and a GO/NO-GO
verdict based on operator-defined operational limits. This is the single most
common reason a BVLOS flight is cancelled: wind speed, gusts, or crosswind
exceed the aircraft's approved operational envelope.

## Why This Is High Impact

Every BVLOS operational approval document lists weather minimums:
maximum sustained wind, maximum gust factor, minimum visibility, maximum
crosswind component. bvlos-sim currently models wind physics (energy, ground
speed) but does not enforce these limits against the forecast as a
feasibility check. The result: a mission can show `FEASIBLE` even when the
forecast would prevent legal operation under the operator's approval.

Adding weather minimums turns bvlos-sim's output from "energy OK" into
"energy OK AND weather within approved limits" — the statement an operator
actually needs to file a flight authorisation.

## Current gap

`constraints.max_wind_mps` exists in the schema but is documented as
"reserved for future feasibility layers; the estimator does not currently
enforce this field." This ticket implements that enforcement and extends it to
cover gusts and crosswind.

`vehicle.performance.max_wind_mps` triggers an advisory warning today, but
only as a WARNING, not a feasibility failure, and only per-leg rather than
as a pre-departure decision gate.

## Scope

### New schema fields (`MissionConstraints`)

```yaml
constraints:
  # existing
  min_landing_reserve_percent: 25.0
  max_wind_mps: 12.0          # now enforced: any forecast leg exceeding this → INFEASIBLE

  # new
  max_gust_mps: 15.0          # maximum 3-second gust; requires gust field in wind grid
  max_crosswind_mps: 8.0      # maximum wind component perpendicular to route leg heading
  min_visibility_m: 5000.0    # minimum horizontal visibility (requires external data source)
  max_precipitation_mm_h: 0.0 # maximum precipitation rate (0 = no rain)
```

### Enforcement logic

When a `SpatiotemporalWindProvider` is configured and `constraints.max_wind_mps`
is set:

- For each transit leg at each sub-segment midpoint, compute the wind speed
  (magnitude of east + north components).
- If any midpoint exceeds `max_wind_mps` → emit `WIND_LIMIT_EXCEEDED` failure,
  infeasible result.
- If `max_crosswind_mps` is set → compute the crosswind component for each leg
  heading and fail if exceeded.
- If `max_gust_mps` is set and the wind grid includes a gust field → check per
  midpoint.

When only a `LayeredWindProvider` or `ConstantWindProvider` is available:
- Check the wind magnitude at the route altitude; emit `WIND_LIMIT_EXCEEDED`
  if exceeded.

### New FailureCodes

```python
WIND_LIMIT_EXCEEDED = "WIND_LIMIT_EXCEEDED"      # sustained wind > max_wind_mps
GUST_LIMIT_EXCEEDED = "GUST_LIMIT_EXCEEDED"      # gust > max_gust_mps
CROSSWIND_LIMIT_EXCEEDED = "CROSSWIND_LIMIT_EXCEEDED"  # crosswind > max_crosswind_mps
```

### Output integration

- `--format checklist` gains a **Weather limits** row: `✓ / ✗ PASS/FAIL` with
  the worst-case wind speed and the leg/waypoint where it occurs.
- `--format summary` includes a `weather FAIL` field when any limit is exceeded.
- `--format json` captures per-leg wind assessment in the result envelope.

### Wind grid extension (optional, non-blocking)

If `max_gust_mps` is set but the wind grid has no gust field, emit a
`GUST_DATA_UNAVAILABLE` advisory warning (not a failure) and skip the gust
check. This allows the schema field to exist without requiring all operators to
have gust data.

### Fetch script extension

`scripts/fetch_wind.py` extended to optionally fetch `wind_gusts_10m` from
Open-Meteo when `--include-gusts` flag is set, adding a `gusts_10m` field to
each grid cell.

### Files to create or modify

| File | Change |
|---|---|
| `schemas/mission.py` | Add `max_gust_mps`, `max_crosswind_mps`, `min_visibility_m`, `max_precipitation_mm_h` to `MissionConstraints`; enforce `max_wind_mps` |
| `estimator/core/enums.py` | Add `WIND_LIMIT_EXCEEDED`, `GUST_LIMIT_EXCEEDED`, `CROSSWIND_LIMIT_EXCEEDED` failure codes |
| `estimator/execution/rules.py` | Add per-leg weather limit checks |
| `estimator/execution/engine.py` | Wire weather checks into estimation pipeline |
| `adapters/checklist_markdown.py` | Add Weather limits row |
| `adapters/assets/wind_grid.py` | Add optional `gusts_10m` field parsing |
| `scripts/fetch_wind.py` | Add `--include-gusts` flag |
| `tests/test_weather_limits.py` | New — unit and integration tests |
| `docs/USAGE.md` | Document `constraints.max_wind_mps` enforcement and new fields |

### Acceptance criteria

1. A mission with `constraints.max_wind_mps: 5.0` and a wind grid showing
   10 m/s sustained wind on a transit leg returns `INFEASIBLE` with
   `WIND_LIMIT_EXCEEDED` in the diagnostics.
2. The `--format checklist` output shows a **Weather limits** row with `✗ FAIL`
   when limits are exceeded.
3. When no wind provider is configured, weather limit fields are accepted but
   not enforced (consistent with other provider-dependent checks).
4. `max_crosswind_mps` is evaluated correctly for a route leg with a known
   heading and a known wind vector.
5. All new failure codes appear in `estimator.FailureCode` public exports.
