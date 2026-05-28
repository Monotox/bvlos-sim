from adapters.envelope import EstimatorResultEnvelope
from adapters.scenario_envelope import ScenarioResultEnvelope
from estimator.core.results import GroundRiskEstimate, MissionEstimate

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

    lines.extend(
        [
            f"- Characteristic dimension m: `{_fmt(ground_risk.characteristic_dimension_m)}`",
            f"- Mission iGRC: `{_igrc_label(ground_risk.mission_igrc)}`",
            "",
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
