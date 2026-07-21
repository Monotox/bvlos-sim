# Ticket 094: SORA Ground Risk Class (iGRC)

## Status

Implemented.

## Goal

Compute the intrinsic Ground Risk Class (iGRC) for a mission by evaluating the
declared operational footprint against conservative population evidence and
the aircraft's maximum characteristic dimension and speed, following JARUS
SORA 2.5. Output per-leg and whole-mission iGRC pre-assessment evidence.

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

- **Aircraft column**: the first Table 2 column whose maximum characteristic
  dimension **and** maximum speed both cover the aircraft. The 250 g / 25 m/s
  exception is handled separately.
- **Population density** across the assessed operational footprint: controlled ground area,
  <5 ppl/km², <50, <500, <5 000, <50 000, >50 000 (gatherings).

The cell value is the iGRC. Higher dimension and higher population both raise
the class. Values above 7 are reported but annotated as outside the standard
specific-category envelope.

## Scope

### New population-density grid asset

A new evidence asset, parallel to the terrain grid, supplying conservative
population density per grid cell in people per km²:

```yaml
# population_grid.v2
schema_version: population-grid.v2
origin_lat: 47.04
origin_lon: 8.29
step_lat_deg: 0.001
step_lon_deg: 0.001
density_ppl_km2:
  - [12.0, 12.0, 340.0, ...]   # one row per latitude step, south to north
  - ...
metadata:
  source: Authority-approved conservative population map
  population_year: 2026
  native_resolution_m: 100.0
  effective_resolution_m: 100.0
  value_semantics: conservative_cell_maximum
  authority_assessment_reference: POP-001 rev 1
  valid_from: 2026-01-01T00:00:00Z
  valid_until: 2026-12-31T23:59:59Z
  transient_population_assessment_reference: EVT-001 rev 1
  operational_footprint_assemblies_present: false
```

Referenced from the mission:

```yaml
assets:
  population_grid_file: assets/population.yaml
```

### New vehicle field

```yaml
# schemas/vehicle.py — VehicleProfile
characteristic_dimension_m: float | None   # maximum aircraft dimension
```

When omitted, iGRC is not computed and a `POPULATION_DENSITY_DIMENSION_MISSING`
advisory warning is emitted (consistent with other provider-dependent features).

### Computation

- For each route leg, conservatively cover the declared footprint using route
  samples and the population grid's effective resolution.
- Take the maximum conservative cell value that can overlap that footprint.
- Select the aircraft column using maximum characteristic dimension and maximum
  speed, then map the maximum density to iGRC via the SORA 2.5 table.
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

`scripts/fetch_population.py` pulls WorldPop point samples for diagnostics. Its
output is deliberately marked ineligible for operational SORA use; it does not
provide conservative cell maxima, authority approval, transient-population
assessment, or bounded evidence validity.

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

- This ticket computes the **intrinsic** GRC only. Mitigations were out of its
  original scope and belong to Ticket 101. The current SORA 2.5 contract uses
  M1(A/B/C) and M2; the former M3 ERP treatment is not a ground-credit input.
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
5. The SORA lookup table is unit-tested at every dimension, speed, and density
   boundary.
6. A mission with no `population_grid_file` is unaffected (backward compatible).
