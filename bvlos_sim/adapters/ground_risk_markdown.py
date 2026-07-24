from bvlos_sim.adapters.envelope import EstimatorResultEnvelope
from bvlos_sim.adapters.scenario_envelope import ScenarioResultEnvelope
from bvlos_sim.estimator.core.results import GroundRiskEstimate, MissionEstimate

_MISSING = "-"
_EXCEEDS_NOTE = "exceeds specific-category envelope"


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def _igrc_label(igrc: int) -> str:
    if igrc > 7:
        return f"{igrc} ({_EXCEEDS_NOTE})"
    return str(igrc)


def _ground_risk_lines(ground_risk: GroundRiskEstimate | None) -> list[str]:
    lines = ["# Ground Risk Class", ""]
    if ground_risk is None:
        lines.append(
            "Ground risk was not computed. Provide a mission population grid and "
            "vehicle characteristic_dimension_m."
        )
        lines.append("")
        return lines

    buffer_m = ground_risk.population_assessment_buffer_m
    lines.extend(
        [
            f"- Characteristic dimension m: `{_fmt(ground_risk.characteristic_dimension_m)}`",
            f"- SORA version: `{ground_risk.sora_version or _MISSING}`",
            f"- Population assessment buffer m: `{_fmt(buffer_m)}`",
            f"- Population numerical dilation m: "
            f"`{_fmt(ground_risk.population_numerical_dilation_m)}`",
            f"- Mission iGRC: `{_igrc_label(ground_risk.mission_igrc)}`",
            "",
        ]
    )
    if buffer_m <= 0.0:
        lines.extend(
            [
                "> **Centerline-only figure — not a SORA iGRC.** Population was "
                "sampled along the route centerline with no assessment buffer, so "
                "this understates the ground risk of the operational volume and "
                "any adjacent area. Re-run with a population assessment buffer "
                "covering the operational volume plus ground-risk buffer before "
                "using this number in a SORA submission.",
                "",
            ]
        )
    lines.extend(
        [
            "| Leg | Route Item ID | Max Density (ppl/km^2) | iGRC |",
            "|----:|---------------|------------------------:|------|",
        ]
    )
    for leg in ground_risk.legs:
        route_item_id = leg.route_item_id or _MISSING
        lines.append(
            f"| {leg.leg_index} | {route_item_id} "
            f"| {_fmt(leg.max_density_ppl_km2)} | {_igrc_label(leg.igrc)} |"
        )
    lines.append("")
    return lines


def render_ground_risk_markdown_for_estimate(
    estimate: MissionEstimate | None,
) -> str:
    ground_risk = estimate.ground_risk if estimate is not None else None
    return "\n".join(_ground_risk_lines(ground_risk))


def render_ground_risk_markdown(envelope: EstimatorResultEnvelope) -> str:
    return render_ground_risk_markdown_for_estimate(envelope.result)


def render_ground_risk_markdown_from_scenario(
    envelope: ScenarioResultEnvelope,
) -> str:
    return render_ground_risk_markdown_for_estimate(envelope.estimate)


__all__ = [
    "render_ground_risk_markdown",
    "render_ground_risk_markdown_for_estimate",
    "render_ground_risk_markdown_from_scenario",
]
