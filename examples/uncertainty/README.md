# Example Uncertainty Plans

Monte Carlo uncertainty plans for the pipeline demo mission. Use with `bvlos-sim sample`.

| File | What it models |
|---|---|
| `pipeline_demo_001_wind_uncertainty.yaml` | 200 samples varying east and north wind components. |
| `pipeline_demo_001_speed_uncertainty.yaml` | 200 samples varying cruise speed. |

## Quick start

```bash
# One-line summary: feasibility rate and p5/p50/p95 reserve
uv run bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format summary

# Full statistics report
uv run bvlos-sim sample examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml \
  --format markdown
```

## Difference from stochastic propagation

`sample` (Monte Carlo) runs the full deterministic estimator once per sample —
fast, but gives only a landing-reserve distribution. `propagate` (stochastic)
steps particles through the timeline at `dt_s` intervals and outputs
per-step reserve-violation probability. Use `sample` for quick feasibility
envelopes; use `propagate` when you need mid-flight risk curves.
