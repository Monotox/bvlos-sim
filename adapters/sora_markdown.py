"""Markdown renderer for the SORA pre-assessment report."""

from adapters.sora_envelope import SoraResultEnvelope
from schemas.sora import GrcMitigationCredit, Sail, SoraAssessment

_NOT_COMPUTED = "not computed"


def _grc_line(label: str, grc: int | None, suffix: str = "") -> str:
    value = str(grc) if grc is not None else _NOT_COMPUTED
    return f"{label} {value}{suffix}".rstrip()


def _arc_label(assessment: SoraAssessment) -> str:
    if assessment.air_risk_class is None:
        return _NOT_COMPUTED
    label = f"ARC-{assessment.air_risk_class.value}"
    reductions = []
    if assessment.strategic_mitigation_applied:
        reductions.append("strategic")
    if assessment.tactical_air_risk_mitigation is not None:
        reductions.append(
            f"tactical ({assessment.tactical_air_risk_mitigation.robustness.value})"
        )
    if reductions and assessment.initial_air_risk_class:
        label += (
            f" (reduced from ARC-{assessment.initial_air_risk_class.value} "
            f"by {' + '.join(reductions)} mitigation)"
        )
    return label


def _sail_label(sail: Sail | None) -> str:
    if sail is None:
        return _NOT_COMPUTED
    if sail == Sail.CERTIFIED:
        return "outside specific category (certified category required)"
    return sail.value


def _signed_credit(credit: int) -> str:
    return f"+{credit}" if credit >= 0 else str(credit)


def _mitigation_lines(assessment: SoraAssessment) -> list[str]:
    credits: list[GrcMitigationCredit] = assessment.ground_risk_mitigations
    if not credits:
        return []
    lines = [
        "",
        f"## Ground Risk Mitigation Ladder (SORA {assessment.sora_version})",
        "",
        f"Intrinsic GRC: {assessment.intrinsic_grc}",
    ]
    for credit in credits:
        lines.append(
            f"- {credit.mitigation_id} {credit.title} "
            f"({credit.robustness.value}): {_signed_credit(credit.grc_credit)}"
        )
    lines.append(f"Final GRC: {assessment.final_grc}")
    return lines


def _sail_lines(assessment: SoraAssessment) -> list[str]:
    if assessment.intrinsic_sail is None or assessment.intrinsic_sail == assessment.sail:
        return [f"SAIL:                               {_sail_label(assessment.sail)}"]
    return [
        f"Intrinsic SAIL:                     {_sail_label(assessment.intrinsic_sail)}",
        f"Mitigated SAIL:                     {_sail_label(assessment.sail)}",
    ]


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
    has_mitigations = bool(assessment.ground_risk_mitigations)
    final_suffix = (
        "" if assessment.final_grc is None or has_mitigations else "   (no mitigations applied)"
    )
    lines = [
        f"# SORA Pre-Assessment: {assessment.mission_id}",
        "",
        _grc_line("Intrinsic Ground Risk Class (iGRC):", assessment.intrinsic_grc),
        _grc_line("Final Ground Risk Class (GRC):     ", assessment.final_grc, final_suffix),
        f"Air Risk Class (ARC):               {_arc_label(assessment)}",
    ]
    lines.extend(_sail_lines(assessment))
    lines.extend(_mitigation_lines(assessment))
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
