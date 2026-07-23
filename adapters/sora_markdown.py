"""Markdown renderer for the SORA pre-assessment report."""

from adapters.sora_envelope import SoraResultEnvelope
from schemas.sora import (
    GrcMitigationCredit,
    OsoPartyDependency,
    Sail,
    SoraAssessment,
)

_NOT_COMPUTED = "not computed"


def _grc_line(label: str, grc: int | None, suffix: str = "") -> str:
    value = str(grc) if grc is not None else _NOT_COMPUTED
    return f"{label} {value}{suffix}".rstrip()


def _arc_label(assessment: SoraAssessment) -> str:
    if assessment.air_risk_class is None:
        return _NOT_COMPUTED
    label = f"ARC-{assessment.air_risk_class.value}"
    if assessment.strategic_mitigation_applied:
        assert assessment.initial_air_risk_class is not None
        label += (
            f" (reduced from ARC-{assessment.initial_air_risk_class.value} "
            "by evidence-backed strategic mitigation)"
        )
    return label


def _sail_label(sail: Sail | None) -> str:
    if sail is None:
        return "not applicable (certified category outcome)"
    return sail.value


def _signed_credit(credit: int) -> str:
    return f"+{credit}" if credit >= 0 else str(credit)


def _rejected_mitigation_lines(assessment: SoraAssessment) -> list[str]:
    rejected = [
        credit
        for credit in assessment.ground_risk_mitigations
        if credit.credit_status is not None
    ]
    if not rejected:
        return []
    lines = [
        "",
        "## Declared Ground Risk Mitigations: NO CREDIT APPLIED",
        "",
        (
            "The mission declares applied ground-risk mitigations, but "
            "mitigation credit is REJECTED pending an Annex B "
            "integrity/assurance evaluation. The GRC and SAIL in this report "
            "assume NO mitigation credit: the final GRC equals the intrinsic "
            "GRC."
        ),
        "",
    ]
    for credit in rejected:
        lines.append(
            f"- {credit.mitigation_id} {credit.title} "
            f"(declared robustness: {credit.robustness.value}; evidence: "
            f"{credit.evidence}): {credit.credit_status.value}"
        )
    return lines


def _mitigation_lines(assessment: SoraAssessment) -> list[str]:
    credits: list[GrcMitigationCredit] = [
        credit
        for credit in assessment.ground_risk_mitigations
        if credit.credit_status is None
    ]
    if not credits:
        return []
    lines = [
        "",
        f"## Ground Risk Mitigation Ladder (SORA {assessment.sora_version})",
        "",
        f"Intrinsic GRC: {assessment.intrinsic_grc}",
    ]
    for credit in credits:
        floor_note = ""
        if credit.grc_credit != credit.nominal_grc_credit:
            floor_note = (
                f" (nominal {_signed_credit(credit.nominal_grc_credit)}; "
                "limited by controlled-ground floor)"
            )
        lines.append(
            f"- {credit.mitigation_id} {credit.title} "
            f"({credit.robustness.value}): {_signed_credit(credit.grc_credit)}"
            f"{floor_note}"
        )
    lines.append(f"Final GRC: {assessment.final_grc}")
    return lines


def _sail_lines(assessment: SoraAssessment) -> list[str]:
    if (
        assessment.intrinsic_sail is None
        or assessment.intrinsic_sail == assessment.sail
    ):
        return [f"SAIL:                               {_sail_label(assessment.sail)}"]
    return [
        f"Intrinsic SAIL:                     {_sail_label(assessment.intrinsic_sail)}",
        f"Mitigated SAIL:                     {_sail_label(assessment.sail)}",
    ]


def _party_dependency_label(dependency: OsoPartyDependency) -> str:
    if not dependency.applicable:
        return "-"
    if not dependency.criterion_refs:
        return "X"
    return "criteria " + ", ".join(str(value) for value in dependency.criterion_refs)


def _oso_lines(assessment: SoraAssessment) -> list[str]:
    if assessment.sail is None:
        return []
    lines = [
        "",
        f"## Table 14 OSOs at SAIL {assessment.sail.value}",
        "",
        "| OSO | Title | Robustness | Required | Operator | Training organisation | Designer | Notes |",
        "|-----|-------|------------|----------|----------|-----------------------|----------|-------|",
    ]
    for oso in assessment.applicable_osos:
        dependencies = oso.party_dependencies
        lines.append(
            f"| {oso.oso_id} | {oso.title} | {oso.robustness.value} | "
            f"{'yes' if oso.required else 'no'} | "
            f"{_party_dependency_label(dependencies.operator)} | "
            f"{_party_dependency_label(dependencies.training_organisation)} | "
            f"{_party_dependency_label(dependencies.designer)} | "
            f"{', '.join(oso.note_refs) or '-'} |"
        )
    return lines


def _containment_lines(assessment: SoraAssessment) -> list[str]:
    requirement = assessment.containment_requirement
    lines = [
        "",
        "## Step 8 Containment Requirements",
        "",
        (
            "Adjacent-area outer limit:           "
            f"{requirement.adjacent_area_outer_limit_m:.1f} m from the "
            "operational volume"
        ),
        (
            "Adjacent-area assessment required:   "
            f"{'yes' if requirement.adjacent_area_assessment_required else 'no'}"
        ),
    ]
    if requirement.selected_table is not None:
        lines.append(
            f"SORA 2.5 containment table:         {requirement.selected_table}"
        )
    if requirement.assessment_reference is not None:
        lines.append(
            f"Adjacent-area evidence:              {requirement.assessment_reference}"
        )
    if requirement.average_population_density_ppl_km2 is not None:
        lines.append(
            "Assessed average population density: "
            f"{requirement.average_population_density_ppl_km2:.1f} ppl/km²"
        )
    if requirement.largest_outdoor_assembly is not None:
        lines.append(
            "Largest outdoor assembly category:  "
            f"{requirement.largest_outdoor_assembly.value}"
        )
    lines.extend(
        [
            (
                "Population operational limit:     "
                f"{requirement.population_density_operational_limit.value}"
            ),
            (
                "Outdoor-assembly operational limit: "
                f"{requirement.outdoor_assembly_operational_limit.value}"
            ),
            (
                "Required containment robustness:  "
                f"{requirement.required_robustness.value}"
            ),
        ]
    )
    if requirement.ground_risk_buffer_revalidation_reference is not None:
        lines.append(
            "Containment-informed GRC recheck:     "
            f"{requirement.ground_risk_buffer_revalidation_reference}"
        )
    lines.append("Annex E containment compliance:     NOT ASSESSED")
    return lines


def render_sora_markdown_for_assessment(assessment: SoraAssessment) -> str:
    has_credited_mitigations = any(
        credit.credit_status is None
        for credit in assessment.ground_risk_mitigations
    )
    has_rejected_mitigations = any(
        credit.credit_status is not None
        for credit in assessment.ground_risk_mitigations
    )
    if assessment.final_grc is None or has_credited_mitigations:
        final_suffix = ""
    elif has_rejected_mitigations:
        final_suffix = "   (declared mitigation credit rejected)"
    else:
        final_suffix = "   (no mitigations applied)"
    lines = [
        f"# SORA Pre-Assessment: {assessment.mission_id}",
        "",
        (
            "**INCOMPLETE SORA — this report identifies risk and assurance "
            "requirements only. Annex E containment and OSO compliance are NOT "
            "ASSESSED.**"
        ),
        "",
        (
            "Specific-category table outcome:      "
            + (
                "within tables"
                if assessment.within_specific_category_method_scope
                else "outside tables"
            )
            + " (not a compliance determination)"
        ),
        (
            "Operator-declared ground footprint:   "
            f"{assessment.ground_risk_footprint.total_buffer_m:.1f} m corridor "
            "from nominal route "
            f"({assessment.ground_risk_footprint.operational_volume_margin_m:.1f} m "
            "operational/contingency margin + "
            f"{assessment.ground_risk_footprint.ground_risk_buffer_m:.1f} m GRB)"
        ),
        (
            "Footprint derivation:                  "
            f"{assessment.ground_risk_footprint.derivation}"
        ),
        (
            "Operator-declared maximum height:      "
            f"{assessment.ground_risk_footprint.maximum_height_agl_m:.1f} m AGL"
        ),
        (
            "Whole-volume airspace assessment:      "
            f"{assessment.operational_and_contingency_volume_assessment_reference}"
        ),
        "Worst-case ARC declaration:             recorded (operator evidence)",
        _grc_line("Intrinsic Ground Risk Class (iGRC):", assessment.intrinsic_grc),
        _grc_line(
            "Final Ground Risk Class (GRC):     ", assessment.final_grc, final_suffix
        ),
        f"Air Risk Class (ARC):               {_arc_label(assessment)}",
    ]
    if assessment.air_risk_rationale is not None:
        lines.append(
            f"ARC rationale:                       {assessment.air_risk_rationale}"
        )
    if assessment.tactical_mitigation_requirement is not None:
        lines.append(
            "TMPR required robustness:            "
            f"{assessment.tactical_mitigation_requirement.required_robustness.value}"
        )
    lines.extend(_sail_lines(assessment))
    lines.extend(_rejected_mitigation_lines(assessment))
    lines.extend(_mitigation_lines(assessment))
    lines.extend(_containment_lines(assessment))
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
