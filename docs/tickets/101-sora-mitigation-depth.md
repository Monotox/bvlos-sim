# Ticket 101: SORA Mitigation Depth — M1–M3 and Tactical Air-Risk Reduction

## Status

Planned.

## Goal

Extend the SORA pre-assessment from "intrinsic GRC + ARC → SAIL" to apply the
declared mitigations that actually determine the final SAIL: ground-risk
mitigations M1 (strategic/sheltering), M2 (effects of impact reduction), and M3
(ERP), plus tactical air-risk reduction. Keep it an explicit, auditable
pre-assessment — never a certified determination.

## Why This Is High Impact

SORA is a headline capability (Tickets 094/095), but today it stops at the
*intrinsic* figures: `estimator/execution/ground_risk.py` computes iGRC and
`air_risk.py`/`sail.py` map GRC×ARC→SAIL with no mitigation logic. Real SORA
outcomes hinge on mitigations — an operator lowers the final GRC with M1/M2 and
reduces ARC tactically. Without them the tool reports a SAIL that is almost
always more conservative than the operator's actual case, so users must do the
real work by hand and the number is only a rough gate. Adding mitigation logic
turns it from "intrinsic risk class" into "the SAIL you would actually argue,"
which is what a ConOps author needs.

## Current gap

- No mitigation inputs in the SORA schema; `compute_ground_risk` and the SAIL
  matrix consume only intrinsic inputs.
- The `sora` command and docs explicitly state mitigations are not applied
  (`docs/USAGE.md` SORA section).

## Scope

### Mitigation inputs (SORA-version-aware, robustness-rated)

```yaml
sora:
  ground_risk_mitigations:
    m1_strategic: { applied: true, robustness: medium }   # e.g. controlled ground area / sheltering
    m2_impact_reduction: { applied: false, robustness: none }
    m3_erp: { applied: true, robustness: low }
  air_risk:
    tactical_mitigation: { applied: true, robustness: medium }
```

### Logic

- Apply the SORA credit table for M1/M2/M3 by robustness to step the final GRC
  down from iGRC (clamped, never below the floor), with each applied credit
  recorded.
- Apply tactical air-risk reduction to the residual ARC.
- Recompute SAIL from the *mitigated* GRC × residual ARC, alongside the
  intrinsic SAIL, so both are visible.
- Encode the mitigation/credit tables as data keyed by SORA version, so a future
  SORA revision is a table change, not a logic rewrite.

### Surfacing

- The SORA result block reports intrinsic GRC/ARC/SAIL, each applied mitigation
  with its robustness and credit, the final GRC/ARC, and the resulting SAIL.
- The `sora` Markdown/JSON output shows the mitigation ladder
  (iGRC → credits → final GRC) so the assessment is auditable.
- Every surface restates that this is an operator-input-driven pre-assessment,
  not an authority determination.

### Files to create or modify

| File | Change |
|---|---|
| `schemas/sora.py` | Mitigation inputs with robustness enums + constraints |
| `estimator/execution/ground_risk.py` | Apply M1–M3 credits to derive final GRC |
| `estimator/execution/air_risk.py` | Apply tactical air-risk reduction to residual ARC |
| `estimator/execution/sail.py` | SAIL from mitigated GRC × residual ARC; keep intrinsic |
| `estimator/core/` (SORA result models) | Mitigation ladder + final-vs-intrinsic fields |
| `adapters/sora_markdown.py`, `adapters/sora_envelope.py` | Render the mitigation ladder |
| `docs/USAGE.md` | Document mitigation inputs and the pre-assessment boundary |
| `tests/test_sora_*.py` | Credit application per robustness, clamping, intrinsic-vs-final |

### Acceptance criteria

1. Declaring M1 at a given robustness lowers the final GRC by the SORA-table
   credit (clamped), and the SAIL is recomputed from the mitigated GRC.
2. A scenario with no mitigations reproduces today's intrinsic SAIL exactly
   (existing SORA fixtures unchanged).
3. Both intrinsic and mitigated SAIL appear in the output, with the full credit
   ladder.
4. Mitigation/credit tables are versioned data; switching SORA version selects
   the matching table.
5. Output continues to state explicitly that it is a pre-assessment aid, not a
   certified SORA determination.
