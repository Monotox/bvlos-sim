# Example Missions

Mission YAML files for the pipeline inspection demo route (Lat 52°N, Lon 4°E area).

| File | Description |
|---|---|
| `pipeline_demo_001.yaml` | Baseline VTOL mission: takeoff, waypoint, loiter, RTL. References `quadplane_v1`. |
| `pipeline_demo_001.plan` | QGroundControl `.plan` source for the same route — convert with `bvlos-sim convert`. |
| `pipeline_demo_001_integrated.yaml` | Same route with terrain and spatiotemporal wind assets enabled. |
| `pipeline_demo_001_ekf.yaml` | Variant with GPS/battery sensor profile for EKF twin-state propagation. References `quadplane_v1_ekf`. |
| `pipeline_demo_001_resource_link.yaml` | Variant with explicit resource and link systems. References `quadplane_resource_link`. |
| `pipeline_demo_001_ground_risk.yaml` | Variant with a population-density grid for `estimate --format ground-risk`. References `quadplane_v1_ground_risk`. |

## Quick start

```bash
# Deterministic estimate
uv run bvlos-sim estimate examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml --format summary --engineering-only

# Pre-flight checklist
uv run bvlos-sim estimate examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml --format checklist

# SORA iGRC pre-assessment
uv run bvlos-sim estimate examples/missions/pipeline_demo_001_ground_risk.yaml \
  examples/vehicles/quadplane_v1_ground_risk.yaml --format ground-risk \
  --engineering-only
```

These examples declare `schema_version: mission.v7`. The baseline inputs omit
several operational evidence categories, so computational demos use
`--engineering-only`; the checklist intentionally shows the default fail-closed
`NO-GO` instead.

See `examples/vehicles/` for matching vehicle profiles.
