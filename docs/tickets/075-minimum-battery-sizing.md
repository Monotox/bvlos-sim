# Ticket 075: Minimum Battery Sizing Calculator

## Goal

Add a `bvlos-sim size-battery` command (or `estimate --find-min-battery`) that
computes the **minimum battery capacity needed for a mission to be feasible**.
Given a mission and vehicle, search the mass-valid capacity range until the
energy reserve just meets the configured threshold, and report the verified
feasible interval with safety-margin recommendations.

## Motivation

Operators frequently work backwards from a route:

> "I want to fly this pipeline survey. My vehicle supports 900 Wh or 1200 Wh
> packs. Which one do I need?"

Today the workflow is:
1. Run `estimate` with the current vehicle profile.
2. If infeasible, manually edit `battery_capacity_wh` in the YAML, re-run.
3. Repeat until the reserve is positive.
4. Add a safety margin above the minimum.

This is tedious and error-prone. A single `size-battery` command closes the
loop in one call, answering "you need at least 843 Wh (20% safety margin: 1012 Wh)".

## Output Specification

```
## Battery Sizing: pipeline_survey_001

Mission energy required:   328.4 Wh
Reserve threshold (25 %):  225.0 Wh (of battery capacity)

Minimum feasible capacity: 843.2 Wh
Maximum feasible capacity: 1200.0 Wh
With 10 % safety margin:   927.5 Wh
With 20 % safety margin:  1011.8 Wh
With 30 % safety margin:  1096.2 Wh

Recommendation: target 927.5 Wh (10 % margin); do not exceed the verified 1200.0 Wh upper bound.

Status: SIZED
```

If the current battery is already sufficient:

```
## Battery Sizing: pipeline_demo_001

Current capacity:   900.0 Wh
Reserve at landing: 585.0 Wh (65.0% of capacity)
Minimum feasible:   550.3 Wh
Maximum feasible:   900.0 Wh
Margin over minimum: 349.7 Wh (63.5% above minimum)

Status: FEASIBLE (current battery exceeds minimum by 63.5%)
```

## Implementation

### 1 — `adapters/battery_sizer.py` (new)

```python
@dataclass(frozen=True)
class BatterySizingResult:
    mission_energy_wh: float
    reserve_threshold_wh: float
    minimum_capacity_wh: float
    maximum_feasible_capacity_wh: float
    maximum_capacity_at_mtow_wh: float
    search_tolerance_wh: float
    current_capacity_wh: float
    current_reserve_wh: float
    current_reserve_pct: float
    is_current_feasible: bool

def compute_minimum_battery_capacity(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    wind_provider=None,
    terrain_provider=None,
    geofences=None,
    landing_zones=None,
    tolerance_wh: float = 1.0,
    max_iterations: int = 40,
) -> BatterySizingResult:
    """Find the first feasible interval under battery-mass feedback."""

def render_battery_sizing_markdown(
    result: BatterySizingResult,
    *,
    mission_id: str,
    safety_margins: list[int] | None = None,
) -> str:
    """Render the sizing result as Markdown."""
```

Search bounds and resolution:
- Lower bound: the smallest positive capacity consistent with the mass model.
- Upper bound: capacity at `mass.max_takeoff_kg`.
- Discovery: scan from low to high at `tolerance_wh` resolution so a bounded
  feasible window cannot be skipped by exponential probes.
- Refinement: refine both transitions of the first contiguous feasible interval.
- A feasible island narrower than `tolerance_wh` is below the selected search
  resolution; reduce the tolerance through the Python API.

Each candidate updates battery capacity and operating mass using pack specific
energy. Requested percentage margins above the verified interval are
unavailable rather than silently emitted as unsafe recommendations.

### 2 — New `size-battery` CLI command

```bash
bvlos-sim size-battery mission.yaml vehicle.yaml
bvlos-sim size-battery mission.yaml vehicle.yaml --margin 20
bvlos-sim size-battery mission.yaml vehicle.yaml --format json
```

Or as `estimate --find-min-battery` if that is preferred.

Adding a dedicated `size-battery` command is cleaner — it has a different
exit code contract (always exits 0 unless there's an error, regardless of
whether the current battery is feasible).

### 3 — Exit codes

| Status | Exit code |
|--------|-----------|
| Sizing succeeded | 0 |
| Invalid input | 11 |
| Internal error | 13 |

### 4 — Tests

`tests/test_battery_sizer.py`:
- `test_binary_search_finds_minimum_capacity`: known mission + vehicle, check
  minimum capacity is close to expected value
- `test_minimum_capacity_is_at_feasibility_boundary`: estimate with
  `minimum_capacity_wh` → reserve ≥ threshold; with `minimum_capacity_wh - 1`
  → reserve < threshold
- `test_oversized_battery_reports_current_feasible`: current vehicle has
  excess capacity
- `test_markdown_contains_recommendation_line`
- `test_markdown_shows_safety_margin_recommendations`
- CLI integration: `size-battery mission.yaml vehicle.yaml` exits 0

### 5 — Documentation

Update `docs/USAGE.md` with a `size-battery` section.

## Integration

Reads only from existing `MissionPlan`, `VehicleProfile`, and mission asset
bundle. Uses `try_estimate_mission_distance_time` — no new execution paths.
No schema changes required.

## Acceptance Criteria

- `size-battery` exits 0 on the success fixture and outputs `Status: FEASIBLE`.
- `size-battery` exits 0 on the infeasible fixture and outputs the minimum
  battery capacity needed.
- The minimum capacity, when applied to the vehicle profile and re-estimated,
  produces a reserve at or above the reserve threshold.
- All existing tests continue to pass.
