"""Markdown renderer for the SORA pre-assessment report."""

from adapters.sora_envelope import SoraResultEnvelope
from schemas.sora import Sail, SoraAssessment

_NOT_COMPUTED = "not computed"


def _grc_line(label: str, grc: int | None, suffix: str = "") -> str:
    value = str(grc) if grc is not None else _NOT_COMPUTED
    return f"{label} {value}{suffix}".rstrip()


def _arc_label(assessment: SoraAssessment) -> str:
    if assessment.air_risk_class is None:
        return _NOT_COMPUTED
    label = f"ARC-{assessment.air_risk_class.value}"
    if assessment.strategic_mitigation_applied and assessment.initial_air_risk_class:
        label += (
            f" (reduced from ARC-{assessment.initial_air_risk_class.value} "
            "by strategic mitigation)"
        )
    return label


def _sail_label(sail: Sail | None) -> str:
    if sail is None:
        return _NOT_COMPUTED
    if sail == Sail.CERTIFIED:
        return "outside specific category (certified category required)"
    return sail.value


def _oso_lines(assessment: SoraAssessment) -> list[str]:
    if assessment.sail is None or assessment.sail == Sail.CERTIFIED:
        return []
    lines = [
        "",
        f"## Applicable OSOs at SAIL {assessment.sail.value}",
        "",
        "| OSO | Title | Robustness |",
        "|-----|-------|------------|",
    ]
    for oso in assessment.applicable_osos:
        lines.append(f"| {oso.oso_id} | {oso.title} | {oso.robustness.value} |")
    return lines


def render_sora_markdown_for_assessment(assessment: SoraAssessment) -> str:
    final_suffix = "   (no mitigations applied)" if assessment.final_grc is not None else ""
    lines = [
        f"# SORA Pre-Assessment: {assessment.mission_id}",
        "",
        _grc_line("Intrinsic Ground Risk Class (iGRC):", assessment.intrinsic_grc),
        _grc_line("Final Ground Risk Class (GRC):     ", assessment.final_grc, final_suffix),
        f"Air Risk Class (ARC):               {_arc_label(assessment)}",
        f"SAIL:                               {_sail_label(assessment.sail)}",
    ]
    lines.extend(_oso_lines(assessment))
    if assessment.advisories:
        lines.extend(["", "## Advisories", ""])
        lines.extend(
            f"- {advisory.code.value}: {advisory.message}"
            for advisory in assessment.advisories
        )
    lines.extend(["", "---", assessment.disclaimer, ""])
    return "\n".join(lines)


def render_sora_markdown(envelope: SoraResultEnvelope) -> str:
    return render_sora_markdown_for_assessment(envelope.result)


__all__ = [
    "render_sora_markdown",
    "render_sora_markdown_for_assessment",
]
