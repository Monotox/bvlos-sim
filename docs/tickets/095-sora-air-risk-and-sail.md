# Ticket 095: SORA Air Risk Class and SAIL Determination

## Status

Implemented and hardened for the SORA 2.5-only `mission.v7` contract. The
command rejects incomplete footprint/airspace evidence, unsupported ARC-a and
above-FL600 shortcuts, and every applied ground-risk mitigation until the
necessary evidence evaluators exist.

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
  max_altitude_agl_m: 120.0        # worst-case whole-volume ceiling above ground
  operational_and_contingency_volume_assessment_reference: "AS-014 rev 2"
  worst_case_arc_declared: true
  aerodrome_environment: false     # explicit SORA Annex I whole-volume assessment
  atypical_or_segregated: false    # true unsupported pending authority evidence
  over_urban_area: false           # required for low uncontrolled airspace
  transponder_mandatory_zone: false # Mode-C veil or TMZ
  entirely_above_flight_level_600: false # true unsupported pending pressure-altitude evidence
```

The initial ARC is assigned by a deterministic rule set based on worst-case
conditions across the whole operational and contingency volume. A non-blank
assessment reference and explicit worst-case declaration are mandatory.
ARC-a from an atypical/segregated boolean and the above-FL600 shortcut are
rejected until authority and pressure-altitude evidence workflows exist.

### Strategic and tactical mitigation boundary

Residual ARC currently equals initial ARC. A boolean `strategic_mitigation`
claim is rejected because a reduction requires local encounter-rate evidence.
Tactical mitigations satisfy the TMPR derived from residual ARC and do not
lower that ARC; a bare tactical-credit declaration is likewise rejected.

### SAIL determination

- Read the final GRC from the ground-risk computation (Ticket 094).
- Read the residual ARC from the airspace rule set.
- Look up SAIL via the SORA GRC × ARC matrix.
- Emit all 17 Table 14 OSO rows for the selected SAIL, including `NR` rows, an
  explicit required flag, note references, and operator/training-organisation/
  designer dependencies with criterion references.

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

Table 14 OSOs at SAIL III: OSO#01 (M, required), OSO#04 (NR), ...
```

### New schema, enum, and module additions

| File | Change |
|---|---|
| `schemas/mission.py` | Add optional `airspace` descriptor block |
| `schemas/sora.py` | SORA requirements output schema (now `sora-assessment.v3`) |
| `estimator/execution/air_risk.py` | ARC rule set |
| `estimator/execution/sail.py` | GRC × ARC → SAIL + OSO table |
| `adapters/commands/sora.py` | New `sora` command |
| `adapters/sora_markdown.py` | SORA report renderer |
| `adapters/sora_envelope.py` | `sora-assessment.v3` in `sora-envelope.v3` JSON |
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

1. `bvlos-sim sora mission.yaml vehicle.yaml` with complete population
   coverage, characteristic dimension, maximum speed, airspace descriptor, and
   explicit SORA 2.5 ground-risk footprint produces a SAIL value.
2. A class-G, low-altitude, no-aerodrome operation yields a low ARC; a
   near-aerodrome operation yields a higher ARC, matching the SORA airspace
   categorisation.
3. The GRC × ARC → SAIL lookup is unit-tested at every matrix cell.
4. A mission missing the airspace descriptor or assessed ground-risk footprint
   is rejected as invalid rather than producing a partial operational SAIL.
5. The `--format markdown` report lists the applicable OSOs for the determined
   SAIL.
6. The report carries the non-certification disclaimer.
