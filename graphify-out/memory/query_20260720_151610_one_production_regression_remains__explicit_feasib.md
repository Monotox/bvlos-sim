---
type: "query"
date: "2026-07-20T15:16:10.293260+00:00"
question: "One production regression remains: explicit feasible external power may replace base battery/RTH feasibility, while onboard/hybrid resources must still account for RTH reserve."
contributor: "graphify"
outcome: "useful"
source_nodes: ["run_estimation()", "evaluate_energy_feasibility()", "evaluate_resource_feasibility()"]
---

# Q: One production regression remains: explicit feasible external power may replace base battery/RTH feasibility, while onboard/hybrid resources must still account for RTH reserve.

## Answer

Expanded from original query via graph vocab: [resource, external, power, energy, reserve, rth, hybrid, battery, feasibility, evaluate]. run_estimation calls evaluate_energy_feasibility before evaluate_resource_feasibility. The fix defers only base-battery RTH reserve-margin gating when explicit resources exist, then makes resource evaluation enforce RTH reserve for onboard/hybrid systems and RTH peak power for external systems.

## Outcome

- Signal: useful

## Source Nodes

- run_estimation()
- evaluate_energy_feasibility()
- evaluate_resource_feasibility()