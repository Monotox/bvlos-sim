"""SORA 2.5 ground credits and fail-closed mitigation-credit rejection."""

import math

import pytest
from pydantic import ValidationError

from estimator.execution.ground_risk import (
    apply_grc_mitigations,
    supported_sora_versions,
)
from schemas.sora import (
    AirRiskMitigations,
    GrcMitigationCredit,
    GrcMitigationCreditStatus,
    GroundRiskMitigation,
    GroundRiskMitigations,
    GroundRiskFootprint,
    MitigationRobustness,
    SoraAdvisoryCode,
    SoraMitigations,
)

_R = MitigationRobustness


def _applied(robustness: MitigationRobustness) -> GroundRiskMitigation:
    return GroundRiskMitigation(
        applied=True,
        robustness=robustness,
        evidence="Test assurance dossier",
        footprint_revalidated=True,
    )


def test_no_mitigations_leaves_intrinsic_grc_unchanged() -> None:
    result = apply_grc_mitigations(5, None, sora_version="2.5")
    assert result.final_grc == 5
    assert result.credits == []
    explicit_none = apply_grc_mitigations(
        5,
        GroundRiskMitigations(),
        sora_version="2.5",
        controlled_ground_floor=1,
    )
    assert explicit_none.final_grc == 5
    assert explicit_none.credits == []


@pytest.mark.parametrize(
    ("field", "robustness"),
    [
        ("m1a_sheltering", _R.LOW),
        ("m1b_operational_restrictions", _R.MEDIUM),
        ("m1c_ground_observation", _R.LOW),
        ("m2_impact_reduction", _R.HIGH),
    ],
)
def test_every_applied_ground_mitigation_is_rejected_until_criteria_evaluation(
    field: str,
    robustness: MitigationRobustness,
) -> None:
    mitigations = GroundRiskMitigations(**{field: _applied(robustness)})

    result = apply_grc_mitigations(
        6,
        mitigations,
        sora_version="2.5",
        controlled_ground_floor=1,
    )

    assert result.final_grc == 6
    assert len(result.credits) == 1
    credit = result.credits[0]
    assert (
        credit.credit_status
        is GrcMitigationCreditStatus.CREDIT_REJECTED_PENDING_ANNEX_B
    )
    assert credit.robustness is robustness
    assert credit.evidence == "Test assurance dossier"
    assert credit.nominal_grc_credit == 0
    assert credit.grc_credit == 0
    assert [advisory.code for advisory in result.advisories] == [
        SoraAdvisoryCode.GROUND_MITIGATION_CREDIT_REJECTED
    ]
    message = result.advisories[0].message
    assert "Annex B integrity-and-assurance criteria evaluator" in message
    assert "free-text evidence reference cannot earn GRC credit" in message


def test_multiple_applied_ground_mitigations_earn_no_credit() -> None:
    mitigations = GroundRiskMitigations(
        m1a_sheltering=_applied(_R.LOW),
        m1b_operational_restrictions=_applied(_R.MEDIUM),
    )

    result = apply_grc_mitigations(
        6,
        mitigations,
        sora_version="2.5",
        controlled_ground_floor=1,
    )

    assert result.final_grc == 6
    assert [credit.mitigation_id for credit in result.credits] == ["M1(A)", "M1(B)"]
    assert all(
        credit.credit_status
        is GrcMitigationCreditStatus.CREDIT_REJECTED_PENDING_ANNEX_B
        for credit in result.credits
    )
    message = result.advisories[0].message
    assert "M1(A), M1(B)" in message


def test_rejected_credit_status_cannot_carry_grc_credit() -> None:
    with pytest.raises(ValidationError, match="cannot carry GRC credit"):
        GrcMitigationCredit(
            mitigation_id="M1(A)",
            title="Strategic mitigation by sheltering",
            robustness=_R.LOW,
            evidence="Test assurance dossier",
            nominal_grc_credit=-1,
            grc_credit=-1,
            credit_status=GrcMitigationCreditStatus.CREDIT_REJECTED_PENDING_ANNEX_B,
        )


def test_unset_credit_status_is_omitted_from_serialized_credit() -> None:
    credit = GrcMitigationCredit(
        mitigation_id="M1(A)",
        title="Strategic mitigation by sheltering",
        robustness=_R.LOW,
        evidence="Test assurance dossier",
        nominal_grc_credit=-1,
        grc_credit=-1,
    )
    assert "credit_status" not in credit.model_dump(mode="json")


def test_unsupported_version_is_rejected_instead_of_ignored() -> None:
    with pytest.raises(ValueError, match="unsupported SORA version"):
        apply_grc_mitigations(5, None, sora_version="2.0")
    with pytest.raises(ValidationError):
        SoraMitigations.model_validate({"version": "9.9"})


def test_only_sora_25_is_supported() -> None:
    assert supported_sora_versions() == ("2.5",)


def test_ground_risk_footprint_requires_auditable_derivation() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        GroundRiskFootprint(
            operational_volume_margin_m=10.0,
            ground_risk_buffer_m=120.0,
            vertical_contingency_margin_m=10.0,
            maximum_height_agl_m=130.0,
            derivation="   ",
        )


@pytest.mark.parametrize("margin_m", [0.0, -1.0, math.inf, math.nan])
def test_ground_risk_footprint_requires_finite_positive_operational_margin(
    margin_m: float,
) -> None:
    with pytest.raises(ValidationError, match="operational_volume_margin_m"):
        GroundRiskFootprint(
            operational_volume_margin_m=margin_m,
            ground_risk_buffer_m=120.0,
            vertical_contingency_margin_m=10.0,
            maximum_height_agl_m=130.0,
            derivation="Operator footprint assessment",
        )


def test_ground_risk_footprint_height_includes_vertical_margin() -> None:
    with pytest.raises(ValidationError, match="must include the vertical"):
        GroundRiskFootprint(
            operational_volume_margin_m=10.0,
            ground_risk_buffer_m=120.0,
            vertical_contingency_margin_m=50.0,
            maximum_height_agl_m=40.0,
            derivation="Operator footprint assessment",
        )


def test_sora_20_m1_and_m3_field_names_are_rejected() -> None:
    with pytest.raises(ValidationError):
        GroundRiskMitigations.model_validate(
            {"m1_strategic": {"applied": True, "robustness": "high"}}
        )
    with pytest.raises(ValidationError):
        GroundRiskMitigations.model_validate(
            {"m3_erp": {"applied": True, "robustness": "high"}}
        )


def test_inconsistent_applied_and_robustness_declaration_is_rejected() -> None:
    with pytest.raises(ValidationError, match="requires a robustness"):
        GroundRiskMitigation(applied=True, robustness=_R.NONE)
    with pytest.raises(ValidationError, match="must be 'none'"):
        GroundRiskMitigation(applied=False, robustness=_R.LOW)


def test_applied_ground_mitigation_requires_evidence() -> None:
    with pytest.raises(ValidationError, match="evidence"):
        GroundRiskMitigation(applied=True, robustness=_R.LOW)


def test_m2_free_text_evidence_cannot_bypass_criteria_evaluator() -> None:
    mitigations = GroundRiskMitigations(
        m2_impact_reduction=GroundRiskMitigation(
            applied=True,
            robustness=_R.MEDIUM,
            evidence="M2 test dossier",
            footprint_revalidated=True,
        )
    )

    result = apply_grc_mitigations(
        5,
        mitigations,
        sora_version="2.5",
        controlled_ground_floor=1,
    )

    assert result.final_grc == 5
    credit = result.credits[0]
    assert credit.mitigation_id == "M2"
    assert credit.grc_credit == 0
    assert (
        credit.credit_status
        is GrcMitigationCreditStatus.CREDIT_REJECTED_PENDING_ANNEX_B
    )


def test_tactical_air_mitigation_claim_is_rejected_not_credited() -> None:
    with pytest.raises(ValidationError, match="cannot reduce ARC"):
        AirRiskMitigations.model_validate(
            {
                "tactical_mitigation": {
                    "applied": True,
                    "robustness": "high",
                    "evidence": "Test DAA evidence",
                }
            }
        )
