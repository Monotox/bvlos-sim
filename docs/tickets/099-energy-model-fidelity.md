# Ticket 099: Energy-Model Fidelity — Mass, Air Density, and State of Charge

## Status

Planned.

## Goal

Replace the constant-power-per-phase energy model with one that accounts for the
factors that actually move power draw on a real flight: payload/all-up mass, air
density (altitude and temperature), and — at minimum as a reserve derating —
battery state of charge. Keep the model deterministic and keep the existing
power fields as the calibration anchor.

## Why This Is High Impact

Energy reserve is the headline output, and today it is the least defensible
number. `estimator/execution/energy.py` multiplies a single
`vehicle.energy.cruise_power_w` (and hover/climb) by leg time, with no
dependence on:

- **Mass** — `vehicle.mass.max_payload_kg` is in the schema but never used; a
  2 kg payload draws the same modeled power as none.
- **Air density** — power is altitude- and temperature-invariant; over a
  1000–1500 m climb in cold air, real draw is materially higher.
- **State of charge** — usable energy is treated as flat to empty.

The result can overestimate range/endurance in exactly the demanding cases
(cold, high, heavy) where the margin matters most. Calibration (Tickets
080–084) is the long-term fix, but a physically-aware closed-form model removes
the worst optimism now, and composes with calibration later.

## Current gap

`estimator/execution/energy.py` uses `EnergyPowerSource` scalars directly.
There is no atmosphere model, no mass term, and no state-of-charge curve. The
RTH and landing-zone energy paths inherit the same flat power.

## Scope

### New vehicle schema fields (all optional, backward-compatible)

```yaml
energy:
  cruise_power_w: 450.0          # existing: treated as reference at reference mass/density
  reference_mass_kg: 10.0        # new: mass at which the reference power was measured
  reference_density_kgm3: 1.225  # new: air density at which it was measured
  induced_power_mass_exponent: 1.5  # new: how induced/hover power scales with mass
  usable_capacity_curve: [...]   # new (optional): SoC -> usable fraction, else flat
mass:
  operating_mass_kg: 11.0        # new (optional): all-up mass for this mission/vehicle
```

### Model

- A small, pure atmosphere helper (`estimator/math/atmosphere.py`) mapping
  geometric altitude + optional temperature offset to air density (ISA).
- Hover/climb (induced) power scales with mass via the configured exponent and
  with density; cruise (parasitic-dominated) power scales with density and a
  milder mass term. All multipliers default to 1.0 when the new fields are
  absent, so existing profiles and fixtures are unchanged.
- Optional SoC derating applied to usable energy, not to the reserve threshold.

### Surfacing

- Per-leg `EnergyLegEstimate` gains the applied multipliers (mass/density) for
  transparency in the JSON and Markdown report.
- A warning when a mission relies on the new factors but the profile omits the
  reference mass/density (so results are not silently mis-scaled).

### Files to create or modify

| File | Change |
|---|---|
| `estimator/math/atmosphere.py` | New — ISA density from altitude/temperature |
| `schemas/vehicle_energy.py`, `schemas/vehicle_mass.py` | New optional fields with constraints |
| `estimator/execution/energy.py` | Apply mass/density/SoC factors to phase power |
| `estimator/core/results.py` | Optional per-leg multiplier fields (exclude_if default) |
| `adapters/markdown.py` | Show applied factors in the energy section |
| `docs/ESTIMATOR_V1_FIELD_SEMANTICS.md`, `docs/USAGE.md` | Document the model and fields |
| `tests/test_estimator_energy.py` | Mass/density/SoC behaviour + back-compat (defaults = old numbers) |

### Acceptance criteria

1. A profile with none of the new fields produces byte-identical output to today
   (golden fixtures unchanged).
2. Increasing `operating_mass_kg` increases hover/climb energy per the configured
   exponent; increasing altitude (lower density) increases power.
3. The atmosphere helper is pure and unit-tested against ISA reference values.
4. RTH and landing-zone energy paths use the same density/mass-aware power.
5. Field semantics and usage docs state clearly that these are physically-motivated
   closed-form scalings, not a substitute for log calibration (Tickets 080–084).
