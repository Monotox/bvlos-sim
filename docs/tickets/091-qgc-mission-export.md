# Ticket 091: QGC Mission Export

## Status

Implemented.

## Goal

Add a `bvlos-sim export` command that converts a `mission.v5` YAML file into a
QGroundControl `.plan` JSON file. This closes the round-trip started by
Ticket 085 (`convert` imports FROM QGC) and means operators can author missions
in bvlos-sim's richer YAML format and then upload them to a real aircraft via
QGroundControl or MAVLink without manual reformatting.

## Why This Is High Impact

The current workflow forces a choice: either author in QGC and import (losing
bvlos-sim-specific fields like constraints and assets), or author in bvlos-sim
YAML and copy waypoints by hand into QGC for upload. Neither is acceptable for
a real flight operation. Export closes the loop:

```
QGC .plan  →  bvlos-sim convert  →  mission.v5 YAML  (validate, simulate)
mission.v5 YAML  →  bvlos-sim export  →  QGC .plan   (upload to aircraft)
```

Any BVLOS tool that cannot produce an uploadable mission file will be treated as
a planning aid, not an operational tool. Export is the feature that moves
bvlos-sim from "analysis" to "mission authoring".

## Scope

### CLI

```bash
bvlos-sim export mission.yaml --output mission.plan
bvlos-sim export mission.yaml           # writes to stdout (JSON)
bvlos-sim export mission.yaml --validate-only  # validate exportability without writing
```

### Supported route item mappings

| bvlos-sim action | QGC command | Notes |
|---|---|---|
| `vtol_takeoff` | `MAV_CMD_NAV_VTOL_TAKEOFF` (84) | `altitude_m` → param 7 |
| `waypoint` | `MAV_CMD_NAV_WAYPOINT` (16) | lat/lon/alt; `acceptance_radius_m` → param 2 |
| `loiter_time` | `MAV_CMD_NAV_LOITER_TIME` (19) | `loiter_time_s` → param 1; `loiter_radius_m` → param 3 |
| `land` | `MAV_CMD_NAV_LAND` (21) | lat/lon |
| `rtl` | `MAV_CMD_NAV_RETURN_TO_LAUNCH` (20) | no params |

### Output format

The exported `.plan` must be loadable by QGroundControl 4.x. Required fields:

```json
{
  "fileType": "Plan",
  "groundStation": "bvlos-sim",
  "version": 1,
  "mission": {
    "cruiseSpeed": <mission.defaults.cruise_speed_mps>,
    "hoverSpeed": <mission.defaults.hover_speed_mps>,
    "plannedHomePosition": [lat, lon, alt_amsl_m],
    "items": [ ... ]
  }
}
```

Each mission item follows QGC `SimpleItem` format with `type`, `command`,
`frame`, `coordinate`, and `params` fields.

### Altitude frame

- `altitude_reference: relative_home` → `frame: 3` (MAV_FRAME_GLOBAL_RELATIVE_ALT)
- `altitude_reference: amsl` → `frame: 0` (MAV_FRAME_GLOBAL)
- `altitude_reference: terrain` → emit a warning diagnostic and use frame 3

### Diagnostics

Emit a warning for any route item that cannot be faithfully round-tripped:
- `loiter_radius_m: 0` (QGC encodes CW/CCW with sign — use positive by default)
- `altitude_reference: terrain` (QGC uses a different terrain-frame mechanism)
- Any bvlos-sim-specific fields that have no QGC equivalent (`acceptance_radius_m`
  is actually supported in QGC param 2, so this one is fine)

### Constraints and assets

bvlos-sim constraint and asset fields (`min_landing_reserve_percent`,
`geofences_file`, etc.) have no QGC `.plan` equivalent. These are silently
omitted from the export — they remain in the source YAML only. A header comment
in the exported file (if written to a file) notes this.

### Files to create or modify

| File | Change |
|---|---|
| `adapters/qgc_export.py` | New — mission.v5 → QGC .plan dict |
| `adapters/commands/export.py` | New — `export` CLI command |
| `adapters/cli.py` | Register `export` command |
| `tests/test_qgc_export.py` | New — unit and CLI tests |
| `docs/USAGE.md` | Add `## QGC Mission Export` section |
| `docs/tickets/README.md` | Mark implemented |

### Acceptance criteria

1. `bvlos-sim export examples/missions/pipeline_demo_001.yaml` emits valid JSON
   loadable by `json.loads`.
2. The exported `.plan` file can be re-imported with `bvlos-sim convert` and
   produces a mission with the same route item count and waypoint coordinates
   (round-trip fidelity).
3. `bvlos-sim export mission.yaml --validate-only` validates the mission YAML
   and exits 0 without writing output.
4. A mission with `altitude_reference: terrain` emits a warning diagnostic to
   stderr and still produces a valid `.plan`.
5. All route item types (vtol_takeoff, waypoint, loiter_time, rtl, land) are
   exercised in tests.
