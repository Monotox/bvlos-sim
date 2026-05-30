"""SORA mitigation depth: GRC credits, tactical ARC reduction, and SAIL."""

import pytest

from estimator.execution.air_risk import compute_air_risk
from estimator.execution.ground_risk import (
    apply_grc_mitigations,
    supported_sora_versions,
)
from schemas.mission import Airspace, IcaoAirspaceClass
from schemas.sora import (
    AirRiskClass,
    GroundRiskMitigation,
    GroundRiskMitigations,
    MitigationRobustness,
)

_R = MitigationRobustness


def _mitigations(**kwargs: GroundRiskMitigation) -> GroundRiskMitigations:
    return GroundRiskMitigations(**kwargs)


def test_no_mitigations_leaves_intrinsic_grc_unchanged() -> None:
    result = apply_grc_mitigations(5, None, sora_version="2.0")
    assert result.final_grc == 5
    assert result.credits == []
    assert result.advisories == []


def test_empty_mitigations_block_is_a_no_op() -> None:
    result = apply_grc_mitigations(5, GroundRiskMitigations(), sora_version="2.0")
    assert result.final_grc == 5
    assert result.credits == []


def test_m1_medium_lowers_final_grc_by_one() -> None:
    result = apply_grc_mitigations(
        5,
        _mitigations(m1_strategic=GroundRiskMitigation(applied=True, robustness=_R.MEDIUM)),
        sora_version="2.0",
    )
    assert result.final_grc == 4
    assert [(c.mitigation_id, c.grc_credit) for c in result.credits] == [("M1", -1)]


def test_m1_high_lowers_final_grc_by_two() -> None:
    result = apply_grc_mitigations(
        5,
        _mitigations(m1_strategic=GroundRiskMitigation(applied=True, robustness=_R.HIGH)),
        sora_version="2.0",
    )
    assert result.final_grc == 3


def test_m3_low_robustness_raises_final_grc() -> None:
    result = apply_grc_mitigations(
        4,
        _mitigations(m3_erp=GroundRiskMitigation(applied=True, robustness=_R.LOW)),
        sora_version="2.0",
    )
    assert result.final_grc == 5
    assert result.credits[0].grc_credit == 1


def test_combined_mitigations_sum_credits() -> None:
    result = apply_grc_mitigations(
        6,
        _mitigations(
            m1_strategic=GroundRiskMitigation(applied=True, robustness=_R.HIGH),
            m2_impact_reduction=GroundRiskMitigation(applied=True, robustness=_R.MEDIUM),
            m3_erp=GroundRiskMitigation(applied=True, robustness=_R.HIGH),
        ),
        sora_version="2.0",
    )
    # -2 (M1 high) + -1 (M2 medium) + -1 (M3 high) = -4
    assert result.final_grc == 2
    assert len(result.credits) == 3


def test_final_grc_is_floored_at_one() -> None:
    result = apply_grc_mitigations(
        2,
        _mitigations(
            m1_strategic=GroundRiskMitigation(applied=True, robustness=_R.HIGH),
            m2_impact_reduction=GroundRiskMitigation(applied=True, robustness=_R.HIGH),
        ),
        sora_version="2.0",
    )
    assert result.final_grc == 1


def test_unsupported_version_skips_credits_with_advisory() -> None:
    result = apply_grc_mitigations(
        5,
        _mitigations(m1_strategic=GroundRiskMitigation(applied=True, robustness=_R.HIGH)),
        sora_version="9.9",
    )
    assert result.final_grc == 5
    assert result.credits == []
    assert result.advisories
    assert result.advisories[0].code.value == "MITIGATION_VERSION_UNSUPPORTED"


def test_supported_versions_includes_baseline() -> None:
    assert "2.0" in supported_sora_versions()


def _airspace(**kwargs) -> Airspace:
    base = {"class": IcaoAirspaceClass.C, "max_altitude_agl_m": 300.0}
    base.update(kwargs)
    return Airspace(**base)


def test_tactical_medium_lowers_residual_arc_one_band() -> None:
    airspace = _airspace()  # above 500 ft controlled -> ARC-d
    assessment = compute_air_risk(
        airspace,
        tactical=GroundRiskMitigation(applied=True, robustness=_R.MEDIUM),
        sora_version="2.0",
    )
    assert assessment.initial_arc == AirRiskClass.D
    assert assessment.residual_arc == AirRiskClass.C
    assert assessment.tactical_bands_reduced == 1


def test_tactical_high_lowers_residual_arc_two_bands() -> None:
    assessment = compute_air_risk(
        _airspace(),
        tactical=GroundRiskMitigation(applied=True, robustness=_R.HIGH),
        sora_version="2.0",
    )
    assert assessment.residual_arc == AirRiskClass.B
    assert assessment.tactical_bands_reduced == 2


def test_tactical_stacks_after_strategic_floored_at_a() -> None:
    assessment = compute_air_risk(
        _airspace(strategic_mitigation=True),
        tactical=GroundRiskMitigation(applied=True, robustness=_R.HIGH),
        sora_version="2.0",
    )
    # ARC-d -> strategic -1 -> ARC-c -> tactical -2 -> ARC-a (floored)
    assert assessment.strategic_mitigation_applied is True
    assert assessment.residual_arc == AirRiskClass.A


def test_no_tactical_leaves_residual_unchanged() -> None:
    assessment = compute_air_risk(_airspace(), sora_version="2.0")
    assert assessment.residual_arc == AirRiskClass.D
    assert assessment.tactical_bands_reduced == 0
    assert assessment.tactical_robustness == _R.NONE


@pytest.mark.parametrize("robustness", [_R.NONE, _R.LOW])
def test_low_or_none_tactical_has_no_effect(robustness: MitigationRobustness) -> None:
    assessment = compute_air_risk(
        _airspace(),
        tactical=GroundRiskMitigation(applied=True, robustness=robustness),
        sora_version="2.0",
    )
    assert assessment.residual_arc == AirRiskClass.D
