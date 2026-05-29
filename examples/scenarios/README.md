# Example Scenarios

Scenario YAML files that inject events and assert outcomes against the pipeline demo mission.

| File | What it tests |
|---|---|
| `pipeline_demo_001_scenario.yaml` | Basic lost-link RTL policy; time and feasibility assertions. |
| `pipeline_demo_001_v2_scenario.yaml` | Same scenario with fidelity v2 (turn arcs). |
| `pipeline_demo_001_divert_routing_scenario.yaml` | Lost-link divert policy; asserts divert feasibility. |
| `pipeline_demo_001_waypoint_policy_scenario.yaml` | Multiple lost-link events with distinct per-event contingency policies. |
| `pipeline_demo_001_integrated_scenario.yaml` | Full stack: terrain, wind, geofence, LZ, divert assertion. |
| `pipeline_demo_001_lz_availability_scenario.yaml` | `landing_zone_unavailable` event removes a zone mid-flight. |
| `pipeline_demo_001_resource_link_scenario.yaml` | Explicit resource and link systems with policy assertions. |

## Quick start

```bash
# Run a scenario and see the one-line result
uv run bvlos-sim scenario examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format summary

# Full JSON report
uv run bvlos-sim scenario examples/scenarios/pipeline_demo_001_scenario.yaml \
  --format json
```

Each scenario YAML references its mission and vehicle files by relative path — run
commands from the repository root.
