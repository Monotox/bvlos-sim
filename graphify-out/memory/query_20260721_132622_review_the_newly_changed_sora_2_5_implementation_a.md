---
type: "query"
date: "2026-07-21T13:26:22.966119+00:00"
question: "Review the newly changed SORA 2.5 implementation and migration changes for correctness, fail-open behavior, contract inconsistencies, wrong Table 14/TMPR/SAIL values, and tests that assert implementation rather than official semantics."
contributor: "graphify"
outcome: "useful"
source_nodes: ["sora.py", "ground_risk.py", "air_risk.py", "sail.py", "mission.py"]
---

# Q: Review the newly changed SORA 2.5 implementation and migration changes for correctness, fail-open behavior, contract inconsistencies, wrong Table 14/TMPR/SAIL values, and tests that assert implementation rather than official semantics.

## Answer

Expanded from original query via graph vocab: [sora, risk, ground, air, mitigation, sail, tmpr, robustness, containment, evidence, schema, migration]. Table 7, Table 14 and TMPR numeric transcriptions match JARUS 2.5. Material gaps remain: Step 8 containment is represented only by a boolean; aerodrome scope is documented too narrowly; zero operational-volume margin and unverified references can yield success; population inputs omit transient assemblies/freshness and can alias source rasters; Category C is incorrectly serialized as a SAIL sentinel; controlled-ground-area row is unreachable through the CLI; v2.0 is silently relabelled v2.5 during migration.

## Outcome

- Signal: useful

## Source Nodes

- sora.py
- ground_risk.py
- air_risk.py
- sail.py
- mission.py