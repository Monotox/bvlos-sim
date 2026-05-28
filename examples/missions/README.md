# Example Missions

Mission YAML files for the pipeline inspection demo route (Lat 52°N, Lon 4°E area).

| File | Description |
|---|---|
| `pipeline_demo_001.yaml` | Baseline VTOL mission: takeoff, waypoint, loiter, RTL. References `quadplane_v1`. |
| `pipeline_demo_001.plan` | QGroundControl `.plan` source for the same route — convert with `bvlos-sim convert`. |
| `pipeline_demo_001_integrated.yaml` | Same route with terrain and spatiotemporal wind assets enabled. |
| `pipeline_demo_001_ekf.yaml` | Variant with GPS/battery sensor profile for EKF twin-state propagation. References `quadplane_v1_ekf`. |
| `pipeline_demo_001_resource_link.yaml` | Variant with explicit resource and link systems. References `quadplane_resource_link`. |

## Quick start

```bash
# Deterministic estimate
uv run bvlos-sim estimate examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml --format summary

# Pre-flight checklist
uv run bvlos-sim estimate examples/missions/pipeline_demo_001.yaml \
  examples/vehicles/quadplane_v1.yaml --format checklist
```

See `examples/vehicles/` for matching vehicle profiles.
