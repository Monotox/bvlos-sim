# Ticket 074: Energy Reserve Sensitivity Table

## Goal

Add a `--format sensitivity` output mode to the `estimate` command that
runs a deterministic parameter sweep and shows how the energy reserve changes
under variations in cruise power, wind speed, and battery capacity. Operators
use this to answer "how robust is my reserve margin?" without running a full
Monte Carlo analysis.

## Motivation

A single-point estimate gives one number: "reserve at landing = 585 Wh". That
number is meaningful only if the operator knows how sensitive it is to real-
world deviations from the model. A mission with 585 Wh reserve that drops to
−20 Wh when cruise power is 10% higher is far less safe than one that drops
to 350 Wh under the same variation.

Today operators must either:
1. Run multiple manual estimates with edited YAML files, or
2. Run `sample` with a full uncertainty YAML for a Monte Carlo sweep.

Option 1 is tedious. Option 2 requires writing an `uncertainty.v1` YAML and
understanding Monte Carlo output. Neither gives a clean table of "what happens
at ±10%/±20%/±30% variation?"

`--format sensitivity` fills this gap with a single command:

```
## Energy Reserve Sensitivity: pipeline_demo_001

Baseline reserve at landing: 585.0 Wh (65.0% of capacity)

### Cruise Power Variation

| Variation | Reserve (Wh) | Reserve (%) | Status   |
|-----------|-------------:|------------:|----------|
| −30 %     |       701.4  |       77.9  | FEASIBLE |
| −20 %     |       656.2  |       72.9  | FEASIBLE |
| −10 %     |       619.1  |       68.8  | FEASIBLE |
|  baseline |       585.0  |       65.0  | FEASIBLE |
| +10 %     |       548.6  |       61.0  | FEASIBLE |
| +20 %     |       510.1  |       56.7  | FEASIBLE |
| +30 %     |       473.5  |       52.6  | FEASIBLE |

### Headwind Variation (applied to all legs)

| Variation | Reserve (Wh) | Reserve (%) | Status     |
|-----------|-------------:|------------:|------------|
| −3 m/s    |       621.3  |       69.0  | FEASIBLE   |
| −2 m/s    |       608.1  |       67.6  | FEASIBLE   |
| −1 m/s    |       596.8  |       66.3  | FEASIBLE   |
|  baseline |       585.0  |       65.0  | FEASIBLE   |
| +1 m/s    |       571.1  |       63.5  | FEASIBLE   |
| +2 m/s    |       554.9  |       61.7  | FEASIBLE   |
| +3 m/s    |       535.2  |       59.5  | FEASIBLE   |

### Battery Capacity Variation

| Variation | Capacity (Wh) | Reserve (Wh) | Reserve (%) | Status   |
|-----------|-------------:|-------------:|------------:|----------|
| −30 %     |         630  |       225.0  |       35.7  | FEASIBLE |
| −20 %     |         720  |       315.0  |       43.8  | FEASIBLE |
| −10 %     |         810  |       405.0  |       50.0  | FEASIBLE |
|  baseline |         900  |       495.0  |       55.0  | FEASIBLE |
| +10 %     |         990  |       585.0  |       59.1  | FEASIBLE |
| +20 %     |        1080  |       675.0  |       62.5  | FEASIBLE |
| +30 %     |        1170  |       765.0  |       65.4  | FEASIBLE |

Sensitivity scan: 3 parameters × 7 levels = 21 runs
```

The table immediately shows operators:
- Whether the mission remains feasible under worst-case deviations
- At what variation level the status changes from FEASIBLE to INFEASIBLE
- Which parameter the mission is most sensitive to

## Output Specification

### Header

```
## Energy Reserve Sensitivity: <mission_id>
```

### Baseline line

```
Baseline reserve at landing: <reserve_wh> Wh (<reserve_pct>% of capacity)
```

### Sensitivity sections

One table per parameter. Default parameters:
- Cruise power: ±10%, ±20%, ±30%
- Headwind: ±1, ±2, ±3 m/s (applied as uniform east-component wind overlay)
- Battery capacity: ±10%, ±20%, ±30%

Optional CLI flags to control sweep:
- `--sensitivity-power-steps` (default: `10,20,30`)
- `--sensitivity-wind-steps` (default: `1,2,3`)
- `--sensitivity-battery-steps` (default: `10,20,30`)

### Footer

```
Sensitivity scan: N parameters × M levels = K runs
```

### Status line at end

If any variation causes INFEASIBLE or a reserve below the threshold:

```
Status: MARGINAL — some variations produce INFEASIBLE or sub-threshold reserve
```

Otherwise:

```
Status: ROBUST — all variations remain FEASIBLE with positive reserve
```

## Implementation

### 1 — `adapters/sensitivity.py` (new)

```python
@dataclass(frozen=True)
class SensitivityLevel:
    parameter: str
    variation_label: str
    variation_value: float
    reserve_wh: float
    reserve_pct: float
    status: str  # "FEASIBLE" / "INFEASIBLE" / "ERROR"

def run_sensitivity_sweep(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    *,
    power_steps: list[int],
    wind_steps: list[float],
    battery_steps: list[int],
    wind_provider: SpatiotemporalWindProvider | None = None,
    terrain_provider: GridTerrainProvider | None = None,
    geofences: list[GeofenceZone] | None = None,
    landing_zones: list[LandingZone] | None = None,
) -> list[SensitivityLevel]:
    """Run parameter variations and return one SensitivityLevel per run."""

def render_sensitivity_markdown(
    baseline: MissionEstimate,
    levels: list[SensitivityLevel],
    *,
    mission_id: str,
) -> str:
    """Render the sensitivity table as Markdown."""
```

Each variation creates a patched copy of the vehicle or mission using
`model_copy(update={...})`. The sweep runs 3 × (2 × len(power_steps))
estimates synchronously on a single thread (no concurrency needed — each
run is fast).

### 2 — Extend `OutputFormat`

Add `SENSITIVITY = "sensitivity"` to `OutputFormat` in `adapters/envelope.py`.

### 3 — Wire into `estimate` CLI

In `adapters/cli.py`:

```python
elif format == OutputFormat.SENSITIVITY:
    levels = run_sensitivity_sweep(
        mission_model, vehicle_model,
        power_steps=[10, 20, 30],
        wind_steps=[1.0, 2.0, 3.0],
        battery_steps=[10, 20, 30],
        wind_provider=mission_assets.wind_provider,
        terrain_provider=mission_assets.terrain_provider,
        geofences=mission_assets.geofences,
        landing_zones=mission_assets.landing_zones,
    )
    output_str = render_sensitivity_markdown(result, levels, mission_id=mission.stem)
```

### 4 — Tests

`tests/test_sensitivity.py`:
- `test_sensitivity_baseline_run_matches_plain_estimate`: sweep at 0% variation equals baseline
- `test_sensitivity_positive_power_reduces_reserve`: reserve decreases when power increases
- `test_sensitivity_headwind_reduces_reserve`: reserve decreases with headwind
- `test_sensitivity_battery_reduction_reduces_reserve`: reserve decreases with smaller battery
- `test_sensitivity_all_levels_completed`: 21 levels in result for default steps
- `test_sensitivity_markdown_contains_all_sections`: checks `### Cruise Power`, `### Headwind`, `### Battery Capacity` headers
- `test_sensitivity_markdown_status_robust_when_all_feasible`
- `test_sensitivity_markdown_status_marginal_when_any_infeasible`
- CLI integration: `estimate --format sensitivity` exits 0 and output contains `Status:`

### 5 — Documentation

Update `docs/USAGE.md` with a `--format sensitivity` section showing the
table output and the optional step flags.

## Integration

Reads only from `EstimatorResultEnvelope.result` and the already-loaded
mission/vehicle models. No changes to core schemas or golden fixtures. The
`OutputFormat` enum extension is backward-compatible.

The sweep reuses `try_estimate_mission_distance_time` — no new execution
paths. Mission and vehicle `model_copy` is the only new operation.

## Acceptance Criteria

- `estimate --format sensitivity` exits 0 on the success fixture.
- Output contains `Status: ROBUST` for the success fixture.
- Each of the three parameter sections is present.
- Reserve values decrease monotonically as headwind increases.
- All existing estimate tests continue to pass.
