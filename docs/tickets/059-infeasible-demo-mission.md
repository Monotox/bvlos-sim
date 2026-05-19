# Ticket 059: Deliberately Infeasible Demo Mission

## Goal

Add one example mission that produces `INFEASIBLE` output — a route that
fails a real check — and a short README note explaining what failed and what
you would change to fix it. This requires no code changes.

## Motivation

Every current example passes. A new user who runs all provided examples sees a
tool that always says yes. The value of bvlos-sim is that it catches problems a
spreadsheet would not catch. Without a failing example, the tool looks like a
calculator that outputs green, not a validator that can output red.

Operators trust tools that demonstrate failure modes, not tools that only show
passes. An infeasible example with a clear explanation — "this mission fails
because the route crosses the restricted zone at wp2; shift the waypoint 500 m
north to clear it" — is the moment a new user understands why the tool exists.

## Scope

Two new files, no code changes:

| File | Contents |
|---|---|
| `examples/real_world/alpine_infeasible.yaml` | Mission that fails one or more checks |
| Update `examples/real_world/README.md` | Section showing the failure output and fix |

The failure should be real and meaningful — not a contrived energy budget
exhausted by a 10,000 km route. Candidate failure modes:

1. **Geofence conflict** — route leg intersects a `forbidden` zone in the
   committed `geofences.geojson` (requires Ticket 053 to have real airspace);
   fallback: use the existing synthetic `data/geofences/demo.geojson`.
2. **Insufficient reserve for terrain** — battery too small for the elevation
   gain on the alpine route, ending with `reserve_at_landing_wh < threshold`.
3. **Landing-zone unreachable** — `min_distance_to_landing_zone_m` constraint
   tighter than any available landing zone; useful if no geofences are yet
   committed.

Option 2 (energy/reserve failure) is self-contained and does not depend on
Ticket 053. Use a reduced `battery_capacity_wh` in a local vehicle override or
a second vehicle YAML (e.g. `alpine_small_battery.yaml`) to make the failure
legible without editing the real quadplane profile.

## README note format

After the passing estimate command, add:

```
## What a failing mission looks like

This mission uses a smaller battery and fails the reserve check:

  uv run bvlos-sim estimate \
    examples/real_world/alpine_infeasible.yaml \
    examples/real_world/quadplane_small_battery.yaml \
    --format summary

Output:
  INFEASIBLE [ENERGY_RESERVE]   reserve −12.4 %   flight 8m 22s

The reserve drops below the 25 % threshold because the battery (300 Wh) is
too small for the 450 m terrain climb on the wp_ridge leg at alpine cruise
power. Fix: increase battery_capacity_wh to at least 520 Wh, or reduce the
altitude gain by lowering the waypoint altitude or re-routing around the ridge.
```

## Acceptance Criteria

1. `uv run bvlos-sim estimate examples/real_world/alpine_infeasible.yaml
   examples/real_world/quadplane_small_battery.yaml --format summary` exits
   non-zero and prints `INFEASIBLE`.
2. The failure reason is real (not a nonsensical constraint) and the README
   explains both what failed and how to fix it.
3. All existing tests continue to pass.

## Out of Scope

- Geofence-based failure (deferred until Ticket 053 commits real airspace).
- Any code changes to the estimator or CLI.
