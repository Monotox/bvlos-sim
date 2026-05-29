# BVLOS Simulator

> Preflight energy, geofence, weather, and contingency feasibility checker for
> beyond-visual-line-of-sight (BVLOS) drone operations.

bvlos-sim turns two YAML files — a **mission** and a **vehicle profile** — into a
deterministic preflight answer to the questions no spreadsheet handles cleanly:

- Does this aircraft have enough reserve given tomorrow's wind over this terrain?
- Does the route cross any restricted airspace, and can it always return home or
  reach a landing zone with reserve intact?
- Is the forecast within the operator's approved weather minimums?
- What is the p5 reserve margin if the wind is a few m/s stronger than forecast?

```text
$ bvlos-sim estimate alpine_mission.yaml quadplane_v1.yaml --format checklist

## Pre-Flight Checklist: alpine_demo_001

✓ Energy feasibility        PASS   reserve 605.78 Wh above threshold
✓ Geofence clearance        PASS   0 conflicts across 0 zone(s)
✓ Landing-zone coverage     PASS   reachable zone found at all 4 checked state(s)
✓ Weather limits            PASS   worst wind 6.00 m/s at leg 1 (wp1)
  RTH reserve (advisory)    INFO   reserve intact for RTH from all 6 leg(s)

Status: GO
```

## Where to start

- **[Usage](USAGE.md)** — every command, flag, output format, and worked example.
- **[Project Brief](BVLOS_MISSION_SIMULATOR_BRIEF.md)** — what the tool is for and
  the design principles behind it.
- **[Field Semantics](ESTIMATOR_V1_FIELD_SEMANTICS.md)** — the meaning, units, and
  conventions of every result field.
- **[Roadmap](ROADMAP.md)** and **[Ticket Backlog](tickets/README.md)** — what is
  built and what is planned.

The documentation site is built from this directory by GitHub Actions.

## Contributing

The tool is open source and contributions are welcome. Read the
**[Contribution Style Guide](CODE_STYLE.md)** and the relevant ticket before
opening a pull request. Core execution is deterministic, all public outputs are
versioned, and unsupported inputs are rejected explicitly rather than
approximated.

The source lives at [github.com/Monotox/bvlos-sim](https://github.com/Monotox/bvlos-sim).
