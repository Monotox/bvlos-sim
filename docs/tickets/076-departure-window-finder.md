# Ticket 076: Departure Window Finder

## Goal

Add a `bvlos-sim window` command that scans a spatiotemporal wind forecast
across a range of departure times and reports which windows produce a feasible
estimate with acceptable reserve. Output: a compact go/no-go table per time
slot, plus a best-window recommendation and JSON envelope for automation.

## Motivation

A drone operator with a pre-fetched wind forecast (`wind_grid.yaml`) faces a
recurring question: "Can I fly at 10:00, or should I wait until 14:00?" Today
they must either manually re-run `estimate` with different `departure_offset_h`
values or interpret the raw wind grid themselves.

`bvlos-sim window` answers the question in one command:

```
$ bvlos-sim window \
    examples/real_world/alpine_mission.yaml \
    examples/real_world/quadplane_v1.yaml \
    --from-offset 0 --to-offset 8 --step 1

## Departure Window Analysis: alpine_demo_001

| Offset | Departure (UTC)  | Status     | Reserve %  | Notes                    |
|--------|------------------|------------|------------|--------------------------|
|  0 h   | 2025-06-15 14:00 | FEASIBLE   |  68.2 %    |                          |
|  1 h   | 2025-06-15 15:00 | FEASIBLE   |  71.4 %    | ★ Best window            |
|  2 h   | 2025-06-15 16:00 | FEASIBLE   |  65.1 %    |                          |
|  3 h   | 2025-06-15 17:00 | INFEASIBLE | −12.3 %    | Headwind +4 m/s on wp_1  |
|  4 h   | 2025-06-15 18:00 | INFEASIBLE |  −8.1 %    |                          |
|  5 h   | 2025-06-15 19:00 | FEASIBLE   |  42.2 %    | Tight reserve margin     |
|  6 h   | 2025-06-15 20:00 | FEASIBLE   |  55.0 %    |                          |
|  7 h   | 2025-06-15 21:00 | FEASIBLE   |  66.3 %    |                          |
|  8 h   | 2025-06-15 22:00 | FEASIBLE   |  70.8 %    |                          |

Best window: 1 h offset (2025-06-15 15:00 UTC) — reserve 71.4 %
```

This is a one-command answer to a question operators ask before every BVLOS
flight. The analysis takes seconds and requires no additional input beyond what
`estimate` already needs.

## Inputs

```
bvlos-sim window <mission> <vehicle>
    [--from-offset HOURS]     # earliest departure offset from wind grid base time (default: 0)
    [--to-offset HOURS]       # latest departure offset (default: max forecast horizon)
    [--step HOURS]            # step size between slots (default: 1)
    [--format summary|json|markdown]
    [--output FILE]
```

The wind grid embedded in the mission `assets.wind_grid_file` must be a
`SpatiotemporalWindProvider` (type `spatiotemporal`). If it is a layered
static wind provider, the command exits with `INVALID_INPUT` and a clear
message: "Departure window analysis requires a time-varying wind grid."

## Output Schema: `window-report.v1`

```json
{
  "schema_version": "window-report.v1",
  "tool_version": "...",
  "mission_id": "alpine_demo_001",
  "wind_grid_base_time": "2025-06-15T14:00:00Z",
  "slots": [
    {
      "offset_h": 0,
      "departure_utc": "2025-06-15T14:00:00Z",
      "status": "FEASIBLE",
      "reserve_at_landing_percent": 68.2,
      "reserve_at_landing_wh": 614.0,
      "failure_code": null,
      "warning_count": 0
    },
    ...
  ],
  "best_offset_h": 1,
  "feasible_slot_count": 7,
  "infeasible_slot_count": 2,
  "provenance": { ... }
}
```

`best_offset_h` selects the feasible slot with the highest
`reserve_at_landing_percent`. When no slot is feasible, `best_offset_h` is
`null` and the command exits with code `INFEASIBLE`.

## Implementation Approach

### Core logic

```python
def find_departure_windows(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    wind_provider: SpatiotemporalWindProvider,
    *,
    from_offset_h: float = 0.0,
    to_offset_h: float | None = None,
    step_h: float = 1.0,
    terrain_provider: TerrainProvider | None = None,
    geofences: list[GeofenceZone] | None = None,
    landing_zones: list[LandingZone] | None = None,
) -> list[WindowSlotResult]:
```

Each slot shifts the wind provider's `base_time` by `offset_h` hours before
passing it to `try_estimate_mission_distance_time`. The underlying estimator
already queries the spatiotemporal grid at `base_time + elapsed_time_s`, so
shifting `base_time` correctly moves the entire forecast window.

`SpatiotemporalWindProvider` already has a `base_time` parameter. The
implementation creates a shallow copy with a shifted `base_time` per slot.
No estimator changes are required.

### Shifting base_time

```python
from datetime import timedelta

def _shifted_provider(
    provider: SpatiotemporalWindProvider,
    offset_h: float,
) -> SpatiotemporalWindProvider:
    return provider.model_copy(
        update={"base_time": provider.base_time + timedelta(hours=offset_h)}
    )
```

This works because `SpatiotemporalWindProvider.wind_at(lat, lon, alt, t)` uses
`base_time + t` as the absolute lookup time. Shifting `base_time` advances the
entire mission's wind profile by `offset_h`.

### Auto-detect offset range

When `--to-offset` is not specified, derive it from the wind grid's time
horizon: `max_offset_h = (grid.times[-1] - grid.base_time).total_seconds() / 3600 - mission_duration_h`. This ensures every slot's wind is fully covered by the grid without extrapolation.

### Tight-reserve warning

Slots where `reserve_at_landing_percent < min_landing_reserve_percent * 1.15`
(within 15% of the threshold) are flagged with a "Tight reserve margin" note.

## Output Formats

- `json` — `window-report.v1` envelope (default)
- `markdown` — Markdown table as shown above
- `summary` — single line: `feasible 7/9   best +1h   reserve 71.4 %`

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | At least one feasible window found |
| 10   | No feasible window found |
| 11   | Invalid input (missing wind grid, incompatible provider, etc.) |
| 13   | Internal error |

## Integration

- Reuses `load_mission`, `load_vehicle`, `load_terrain_grid`, `load_wind_grid`,
  `load_geofences`, `load_landing_zones` from existing IO adapters
- Reuses `_populate_mission_assets` from `cli_support`
- Reuses `try_estimate_mission_distance_time` unchanged
- New module: `estimator/execution/window.py` — `find_departure_windows`
- New adapter: `adapters/window_envelope.py` — `WindowSlotResult`,
  `WindowReport`, `build_window_envelope`, `render_window_markdown`
- New CLI command: `window` registered on `app` in `adapters/cli.py`

## Files to Create or Modify

| File | Change |
|------|--------|
| `estimator/execution/window.py` | New — core window-scanning logic |
| `adapters/window_envelope.py` | New — `window-report.v1` schema and renderers |
| `adapters/cli.py` | Add `window` command |
| `adapters/summary.py` | Add `format_window_summary` |
| `schemas/__init__.py` | Export new window types |
| `tests/test_window_command.py` | Acceptance tests |
| `docs/USAGE.md` | Document `window` command |
| `docs/tickets/README.md` | Mark implemented when done |

## Acceptance Criteria

1. `bvlos-sim window alpine_infeasible.yaml quadplane_v1.yaml` exits non-zero
   when no slot is feasible (infeasible across all forecast hours).
2. `bvlos-sim window alpine_mission.yaml quadplane_v1.yaml --format summary`
   emits a single-line summary with feasible count and best-window reserve.
3. `bvlos-sim window alpine_mission.yaml ... --from-offset 2 --to-offset 4`
   scans only hours 2–4 and outputs 3 rows.
4. When the mission has no spatiotemporal wind provider (static or no wind),
   the command exits `INVALID_INPUT` with a clear error message.
5. `--format json` output validates against `window-report.v1` schema.
6. The best-window slot is the feasible slot with the highest reserve percent.
7. Golden fixture test for the Alpine example covering offset 0–3 h.
