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
✓ Energy feasibility        PASS   reserve 573.05 Wh above threshold (798.05 Wh at landing, 225.00 Wh threshold)
✓ Geofence clearance        PASS   0 conflicts across 0 zone(s)
✓ Landing-zone coverage     PASS   reachable zone found at all 166 checked state(s)
◌ Resource availability     N/A    not evaluated
...
Status: NO-GO
Blocked by: missing evidence (resource, link, obstacle, ground_risk) — the checklist is fail-closed
```

The exit code is `10`. This is deliberate: the checklist is **fail-closed** —
evidence that was never evaluated (`◌ N/A`) can never contribute to a `GO`.
The demo mission omits resource, link, obstacle, and ground-risk inputs, so it
cannot pass an *operational* preflight, and the `Blocked by:` line names
exactly what's missing.

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
FEASIBLE   reserve 254.7 %   flight 7m 55s
```

Exit code `0`. `reserve 254.7 %` means the predicted energy at landing is
254.7% *above the reserve threshold* (25% of battery for this mission) — it is
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
INFEASIBLE   reserve −179.7 %   flight 7m 55s   RTH infeasible   [INSUFFICIENT_ENERGY]
```

Exit code `10` again — but now for a physical reason, named by the failure
code. `bvlos-sim size-battery` on the same pair would tell you the smallest
battery that fixes it.

## 4. Check inputs without running anything

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
engineering feasibility verdict, an infeasible counter-example, and input
validation — all deterministic, all reproducible.

Next:

- Author your own mission and vehicle — [Missions and vehicles](missions.md).
- Fetch real terrain/wind/landing-zone data for your own area —
  [`examples/real_world/README.md`](https://github.com/Monotox/bvlos-sim/blob/main/examples/real_world/README.md).
- Every command, flag, and exit code — [CLI reference](cli.md).
- Why the tool refuses to guess — [Design](design.md).
