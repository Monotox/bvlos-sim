# Getting started

By the end you'll have run a real preflight check on a bundled Alpine mission,
read its go/no-go verdict, and produced a one-line summary you could wire into
CI. Takes about five minutes; everything runs offline.

## Before you begin

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)

```bash
git clone https://github.com/Monotox/bvlos-sim
cd bvlos-sim
uv sync
uv run bvlos-sim --help   # verify the CLI answers
```

## 1. Run the preflight checklist

The repository ships a pre-fetched mission over the Lucerne/Zug Alps — real
SRTM terrain, a real Open-Meteo wind grid, real OpenStreetMap landing zones —
so no network is needed:

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml \
  --format checklist
```

You should see every evaluated check pass, and still:

```text
✓ Energy feasibility        PASS   reserve 603.56 Wh above threshold (828.56 Wh at landing, 225.00 Wh threshold)
◌ Geofence clearance        N/A    not evaluated
✓ Landing-zone coverage     PASS   reachable zone found at all 166 checked state(s)
◌ Resource availability     N/A    not evaluated
...
  Warnings                  1      ENERGY_MODEL_UNCALIBRATED

Status: NO-GO
Blocked by: missing evidence (geofence, resource, link, obstacle, ground_risk); blocking warnings (ENERGY_MODEL_UNCALIBRATED) — the checklist is fail-closed
```

The exit code is `10`. This is deliberate: the checklist is **fail-closed** —
evidence that was never evaluated (`◌ N/A`) can never contribute to a `GO`.
The demo mission omits geofence, resource, link, obstacle, and ground-risk
inputs, so it cannot pass an *operational* preflight, and the `Blocked by:`
line names exactly what's missing.

`ENERGY_MODEL_UNCALIBRATED` is the same principle applied to the numbers
themselves. This vehicle profile ships placeholder power values, so every energy
figure above is arithmetic on invented coefficients. Step 4 shows the profile
that has been calibrated against a flight log.

## 2. Get the engineering verdict

When you only want the physics — is the route flyable with this battery in
this wind — opt out of the operational gate:

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml \
  --format summary --engineering-only
```

```text
FEASIBLE   reserve 268.2 %   flight 7m 58s   warnings 1
```

Exit code `0`. `reserve 268.2 %` means the predicted energy at landing is
268.2% *above the reserve threshold* (25% of battery for this mission) — it is
a margin over the reserve, not battery state of charge.

## 3. See a failure

The same route with a battery that cannot make it:

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_infeasible.yaml \
  examples/real_world/quadplane_small_battery.yaml \
  --format summary
```

```text
INFEASIBLE   reserve −36.2 %   flight 7m 58s   RTH infeasible   warnings 1   [RESERVE_BELOW_THRESHOLD]
```

Exit code `10` again — but now for a physical reason, named by the failure
code. `bvlos-sim size-battery` on the same pair would tell you the smallest
battery that fixes it.

## 4. See a GO

Everything so far was blocked. This is what clearing the gate looks like:

```bash
uv run bvlos-sim estimate \
  examples/missions/pipeline_demo_001_go.yaml \
  examples/vehicles/quadplane_v1_complete.yaml \
  --calibration examples/calibration/quadplane_v1_calibration.json \
  --format checklist
```

```text
✓ Energy feasibility        PASS   reserve 650.00 Wh above threshold (875.00 Wh at landing, 225.00 Wh threshold)
✓ Geofence clearance        PASS   0 conflicts across 1 zone(s)
✓ Landing-zone coverage     PASS   reachable zone found at all 14 checked state(s)
✓ Resource availability     PASS   system 'fiber-power-primary' sufficient
✓ Link availability         PASS   link 'mesh-primary' available
✓ Obstacle clearance        PASS   0 violations across 3 leg(s) and 1 obstacle(s)
✓ Weather limits            PASS   worst wind 2.72 m/s at leg 1 (wp1)
✓ RTH feasibility           PASS   selected external resource covers RTH peak power
  Ground risk class         INFO   mission iGRC 3
  Departure time            INFO   2026-07-21T12:00:00Z
  Warnings                  NONE

Status: GO
```

Exit code `0`. Three things earn it, and dropping any one of them puts the
verdict back to NO-GO:

- **Every evidence category is supplied.** Open
  `examples/missions/pipeline_demo_001_go.yaml` and you'll find geofence,
  landing-zone, obstacle, terrain, population, and wind assets, plus
  `link_systems`, `airspace`, and `sora` blocks. The vehicle supplies
  `resource_systems` and `characteristic_dimension_m`.
- **The coefficients are calibrated.** `--calibration` layers a profile fitted
  from a real flight trace onto the vehicle, which clears
  `ENERGY_MODEL_UNCALIBRATED`.
- **No warning is waived.** The mission has no `accepted_warning_codes` at all.
  A `GO` that needs a waiver is worth less than one that doesn't.

Drop the `--calibration` flag and run it again: same route, same assets, back to
NO-GO.

## 5. Check inputs without running anything

```bash
uv run bvlos-sim estimate \
  examples/real_world/alpine_mission.yaml \
  examples/real_world/quadplane_v1.yaml \
  --validate-only
```

`--validate-only` schema-checks the mission, vehicle, and every referenced
asset file, then exits — `0` when everything loads, `11` with a pointed error
when it doesn't. Use it in CI before long runs, and while authoring your own
files.

## What you built

You ran the full preflight pipeline: a fail-closed operational checklist, an
engineering feasibility verdict, an infeasible counter-example, a complete-evidence
`GO`, and input validation — all deterministic, all reproducible.

Next:

- Author your own mission and vehicle — [Missions and vehicles](missions.md).
- Fetch real terrain/wind/landing-zone data for your own area —
  [`examples/real_world/README.md`](https://github.com/Monotox/bvlos-sim/blob/main/examples/real_world/README.md).
- Every command, flag, and exit code — [CLI reference](cli.md).
- Why the tool refuses to guess — [Design](design.md).
