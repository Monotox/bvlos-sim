# Ticket 095: SORA Air Risk Class and SAIL Determination

## Status

Planned.

## Goal

Complete the SORA pre-assessment by computing the Air Risk Class (ARC) for the
operational volume and combining it with the Ground Risk Class (Ticket 094) to
determine the **SAIL** (Specific Assurance and Integrity Level) — the single
output that tells a BVLOS operator how much rigour their operation must
demonstrate. Produce a SORA summary report aligned with the EASA submission
structure.

## Why This Is High Impact

The SAIL is the keystone of a SORA submission. It determines which Operational
Safety Objectives (OSOs) apply and at what robustness level. An operator
preparing a BVLOS authorisation needs to know their SAIL before they write a
single line of their operations manual.

Ticket 094 gives the Ground Risk Class. This ticket adds the Air Risk Class and
the GRC × ARC → SAIL determination, turning bvlos-sim into a tool that produces
the headline number of a SORA application. Together, 094 and 095 are the
features most likely to make a professional operator choose this tool.

## Background: ARC and SAIL

- **Air Risk Class (ARC-a … ARC-d)**: the likelihood of encountering manned
  aircraft in the operational volume, driven by airspace class, altitude band,
  proximity to aerodromes, and whether the volume is atypical/segregated.
- **SAIL (I … VI)**: a lookup combining the final GRC (rows) and the residual
  ARC (columns). Higher GRC or ARC raises the SAIL.

## Scope

### Air Risk Class inputs

ARC is derived from airspace context. The mission gains an optional operational
airspace descriptor:

```yaml
airspace:
  class: "G"                       # ICAO airspace class at operational altitude
  max_altitude_agl_m: 120.0        # operational ceiling above ground
  near_aerodrome: false            # within an aerodrome traffic zone
  atypical_or_segregated: false    # e.g. active danger area, segregated volume
```

The initial ARC is assigned by a deterministic rule set based on these inputs,
following the SORA airspace encounter categorisation. If the descriptor is
absent, ARC is not computed and a `AIRSPACE_DESCRIPTOR_MISSING` advisory is
emitted.

### Strategic mitigation (optional)

A `strategic_mitigation` flag may lower the ARC by one band where the SORA
methodology permits (e.g. operating in an atypical/segregated volume). Tactical
mitigation is out of scope (it is an operational, not a planning-time, property).

### SAIL determination

- Read the final GRC from the ground-risk computation (Ticket 094).
- Read the residual ARC from the airspace rule set.
- Look up SAIL via the SORA GRC × ARC matrix.
- Emit the SAIL and the list of applicable OSOs at their required robustness for
  that SAIL (a static table from the SORA annex).

### New `sora` command

Rather than overloading `estimate`, add a dedicated command that runs the full
SORA pre-assessment and renders the report:

```bash
bvlos-sim sora mission.yaml vehicle.yaml --format markdown
bvlos-sim sora mission.yaml vehicle.yaml --format json
```

The command reuses the estimator (for the route + ground risk) and adds the
air-risk and SAIL layers. `--format markdown` renders a SORA-style summary:

```
# SORA Pre-Assessment: alpine_demo_001

Intrinsic Ground Risk Class (iGRC): 4
Final Ground Risk Class (GRC):      4   (no mitigations applied)
Air Risk Class (ARC):               b
SAIL:                               III

Applicable OSOs at SAIL III: OSO#01 (M), OSO#03 (M), ...
```

### New schema, enum, and module additions

| File | Change |
|---|---|
| `schemas/mission.py` | Add optional `airspace` descriptor block |
| `schemas/sora.py` | New `sora-assessment.v1` output schema |
| `estimator/execution/air_risk.py` | ARC rule set |
| `estimator/execution/sail.py` | GRC × ARC → SAIL + OSO table |
| `adapters/commands/sora.py` | New `sora` command |
| `adapters/sora_markdown.py` | SORA report renderer |
| `adapters/sora_envelope.py` | `sora-assessment.v1` JSON envelope |
| `adapters/cli.py` | Register `sora` command |
| `tests/test_air_risk.py` | ARC rule-set tests |
| `tests/test_sail.py` | SAIL matrix tests |
| `tests/test_sora_cli.py` | End-to-end command tests |
| `docs/USAGE.md` | New `## SORA Pre-Assessment` section |

## Dependencies

- **Requires Ticket 094** (Ground Risk Class) — the SAIL needs the GRC.
- Composes with Ticket 093 (time-varying geofences) and Ticket 058 (NOTAM) for
  a richer airspace picture, but does not require them.

## Non-goals

- This is a **pre-assessment aid**, not a certified SORA determination. The
  output must carry a prominent disclaimer (consistent with the existing
  README disclaimer) that it does not replace a competent authority review.
- Mitigation robustness evidence (the actual OSO compliance) is out of scope;
  the report lists *which* OSOs apply, not whether they are met.
- Quantitative/PRA SORA (the numerical path) is out of scope; this ticket
  implements the standard qualitative table-driven SORA.

## Acceptance criteria

1. `bvlos-sim sora mission.yaml vehicle.yaml` with a populated population grid,
   characteristic dimension, and airspace descriptor produces a SAIL value.
2. A class-G, low-altitude, no-aerodrome operation yields a low ARC; a
   near-aerodrome operation yields a higher ARC, matching the SORA airspace
   categorisation.
3. The GRC × ARC → SAIL lookup is unit-tested at every matrix cell.
4. A mission missing the airspace descriptor emits `AIRSPACE_DESCRIPTOR_MISSING`
   and reports GRC only, without a SAIL.
5. The `--format markdown` report lists the applicable OSOs for the determined
   SAIL.
6. The report carries the non-certification disclaimer.
