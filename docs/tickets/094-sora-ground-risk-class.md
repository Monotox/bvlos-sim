# Ticket 094: SORA Ground Risk Class (iGRC)

## Status

Implemented.

## Goal

Compute the intrinsic Ground Risk Class (iGRC) for a mission by overlaying the
route against a population-density grid and the aircraft's characteristic
dimension, following the EASA SORA methodology. Output a per-leg and
whole-mission iGRC so operators can see, before flight, which ground-risk class
their operation falls into.

## Why This Is High Impact

SORA (Specific Operations Risk Assessment) is the regulatory framework that
governs BVLOS approvals in the EU, UK, and a growing number of other
jurisdictions. The first number every SORA submission needs is the **intrinsic
Ground Risk Class** — a table lookup derived from the aircraft's characteristic
dimension and the population density beneath the flight path.

bvlos-sim already models the route, terrain, wind, energy, and geofences. The
one thing it cannot answer is the question a regulator asks first: *"what is the
ground risk if this aircraft comes down here?"* Adding iGRC computation moves
bvlos-sim from an engineering feasibility tool into a regulatory
pre-assessment tool — by far the most compelling reason a professional BVLOS
operator would adopt it.

## Background: the SORA iGRC table

The intrinsic GRC is a lookup on two axes:

- **Aircraft characteristic dimension**: ≤1 m, ≤3 m, ≤8 m, >8 m. This bands the
  maximum kinetic energy at impact.
- **Population density** beneath the operational volume: controlled ground area,
  <5 ppl/km², <50, <500, <5 000, <50 000, >50 000 (gatherings).

The cell value is the iGRC. Higher dimension and higher population both raise
the class. Values above 7 are reported but annotated as outside the standard
specific-category envelope.

## Scope

### New population-density grid asset

A new asset type, parallel to the terrain grid, supplying population density per
grid cell in people per km²:

```yaml
# population_grid.v1
origin_lat: 47.04
origin_lon: 8.29
step_lat_deg: 0.001
step_lon_deg: 0.001
density_ppl_km2:
  - [12.0, 12.0, 340.0, ...]   # one row per latitude step, south to north
  - ...
```

Referenced from the mission:

```yaml
assets:
  population_grid_file: assets/population.yaml
```

### New vehicle field

```yaml
# schemas/vehicle.py — VehicleProfile
characteristic_dimension_m: float | None   # max span/diameter; required for iGRC
```

When omitted, iGRC is not computed and a `POPULATION_DENSITY_DIMENSION_MISSING`
advisory warning is emitted (consistent with other provider-dependent features).

### Computation

- For each route leg, sample the population-density grid at the leg's sampled
  midpoints (reusing the sub-segment sampling already used for wind).
- Take the maximum density encountered along the operational volume of each leg
  (a buffer around the route is configurable; default uses the leg path only).
- Map (characteristic_dimension_m, max_density) → iGRC via the SORA table.
- The mission iGRC is the maximum iGRC across all legs.

### Output integration

- New `--format ground-risk` for `estimate`: a Markdown table of per-leg iGRC,
  population density, and the governing waypoint, plus the mission-level iGRC.
- `--format checklist` gains a **Ground risk class** row showing the mission iGRC.
- `--format json` result envelope gains a `ground_risk` block:
  ```json
  "ground_risk": {
    "characteristic_dimension_m": 1.5,
    "mission_igrc": 4,
    "legs": [{"leg_index": 1, "max_density_ppl_km2": 340.0, "igrc": 4}]
  }
  ```
- `--format geojson` route legs gain an `igrc` property so the route can be
  colour-coded by ground risk in QGIS / Google Earth.

### Fetch script

A new `scripts/fetch_population.py` that pulls population density from an open
gridded source (e.g. GHSL / WorldPop / GPW) for a bounding box and writes a
`population_grid.v1` YAML. Consistent with the existing fetch-script pattern;
not part of core CI.

### New schema and enum additions

| File | Change |
|---|---|
| `schemas/vehicle.py` | Add `characteristic_dimension_m` |
| `schemas/mission.py` | Add `assets.population_grid_file` |
| `estimator/core/enums.py` | Add `POPULATION_DENSITY_DIMENSION_MISSING` warning |
| `estimator/core/results.py` | Add `GroundRiskEstimate` + `GroundRiskLegEstimate` |
| `estimator/environment/population.py` | New population grid provider |
| `estimator/execution/ground_risk.py` | New iGRC computation |
| `adapters/assets/population_grid.py` | New loader |
| `adapters/ground_risk_markdown.py` | New `--format ground-risk` renderer |
| `scripts/fetch_population.py` | New fetch script |
| `tests/test_ground_risk.py` | New unit + integration tests |
| `docs/USAGE.md` | New `## Ground Risk (SORA iGRC)` section |

## Non-goals

- This ticket computes the **intrinsic** GRC only. Mitigations (M1/M2/M3) that
  lower the final GRC are out of scope and belong in a later ticket.
- Air Risk Class and SAIL determination are Ticket 095.
- The population grid is offline; live population data fetch is best-effort in
  the fetch script only, never in core estimation.

## Composition

- The population grid loads exactly like the terrain grid (Ticket 032 pattern),
  through `assets.population_grid_file`, resolved relative to the mission file.
- iGRC computation reuses the sub-segment sampling already implemented for wind.
- Output flows through the existing envelope/markdown/geojson surfaces.

## Acceptance criteria

1. A mission over a 12 ppl/km² area with a 1 m aircraft returns the correct
   low iGRC; the same route over a 5 000 ppl/km² cell returns a higher iGRC,
   matching the implemented SORA-style table.
2. A vehicle with no `characteristic_dimension_m` emits
   `POPULATION_DENSITY_DIMENSION_MISSING` and omits the `ground_risk` block.
3. `estimate --format ground-risk` produces a per-leg iGRC table and a
   mission-level iGRC.
4. `estimate --format geojson` includes an `igrc` property on each route leg.
5. The SORA lookup table is unit-tested at every cell boundary.
6. A mission with no `population_grid_file` is unaffected (backward compatible).
