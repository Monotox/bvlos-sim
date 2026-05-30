"""SORA pre-assessment orchestration.

Combines the Ground Risk Class (computed by the estimator from the population
grid) with the Air Risk Class and SAIL determination to produce a whole-mission
:class:`SoraAssessment`. Operator-declared mitigations (M1/M2/M3 and tactical
air-risk reduction) step the intrinsic figures down to the final GRC, residual
ARC, and mitigated SAIL; the intrinsic SAIL is retained alongside so both are
auditable. The result is an explicit pre-assessment aid, never a certified
determination.
"""

from estimator.core.results import MissionEstimate
from estimator.execution.air_risk import AirRiskAssessment, compute_air_risk
from estimator.execution.ground_risk import apply_grc_mitigations
from estimator.execution.sail import applicable_osos, determine_sail
from schemas.mission import MissionPlan
from schemas.sora import (
    DEFAULT_SORA_VERSION,
    AirRiskClass,
    GrcMitigationCredit,
    Sail,
    SoraAdvisory,
    SoraAdvisoryCode,
    SoraAssessment,
    TacticalAirRiskMitigation,
)
from schemas.vehicle import VehicleProfile


def build_sora_assessment(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    estimate: MissionEstimate,
) -> SoraAssessment:
    """Assemble the SORA pre-assessment from estimator outputs and airspace."""
    advisories: list[SoraAdvisory] = []
    mitigations = mission.sora
    sora_version = mitigations.version if mitigations is not None else DEFAULT_SORA_VERSION

    intrinsic_grc, final_grc, grc_credits = _ground_risk(
        estimate, mitigations, sora_version, advisories
    )

    air_risk = _air_risk(mission, mitigations, sora_version, advisories)
    initial_arc = air_risk.initial_arc if air_risk is not None else None
    residual_arc = air_risk.residual_arc if air_risk is not None else None

    intrinsic_sail = _sail_or_none(intrinsic_grc, initial_arc)
    sail = _sail_or_none(final_grc, residual_arc)
    osos = []
    if sail is not None and sail == Sail.CERTIFIED:
        advisories.append(
            SoraAdvisory(
                code=SoraAdvisoryCode.OPERATION_OUTSIDE_SPECIFIC_CATEGORY,
                message=(
                    "Final GRC exceeds 7; the operation falls outside the "
                    "specific category and requires the certified category."
                ),
            )
        )
    elif sail is not None:
        osos = applicable_osos(sail)

    return SoraAssessment(
        mission_id=mission.mission_id,
        sora_version=sora_version,
        characteristic_dimension_m=vehicle.characteristic_dimension_m,
        intrinsic_grc=intrinsic_grc,
        final_grc=final_grc,
        ground_risk_mitigations=grc_credits,
        initial_air_risk_class=initial_arc,
        air_risk_class=residual_arc,
        strategic_mitigation_applied=(
            air_risk.strategic_mitigation_applied if air_risk is not None else False
        ),
        tactical_air_risk_mitigation=_tactical_mitigation(air_risk),
        intrinsic_sail=intrinsic_sail,
        sail=sail,
        applicable_osos=osos,
        advisories=advisories,
    )


def _ground_risk(
    estimate: MissionEstimate,
    mitigations,
    sora_version: str,
    advisories: list[SoraAdvisory],
) -> tuple[int | None, int | None, list[GrcMitigationCredit]]:
    ground_risk = estimate.ground_risk
    if ground_risk is None:
        advisories.append(
            SoraAdvisory(
                code=SoraAdvisoryCode.GROUND_RISK_NOT_COMPUTED,
                message=(
                    "Ground Risk Class was not computed; provide a mission "
                    "population grid and vehicle characteristic_dimension_m."
                ),
            )
        )
        return None, None, []

    intrinsic_grc = ground_risk.mission_igrc
    declared = mitigations.ground_risk_mitigations if mitigations is not None else None
    result = apply_grc_mitigations(
        intrinsic_grc, declared, sora_version=sora_version
    )
    advisories.extend(result.advisories)
    return intrinsic_grc, result.final_grc, result.credits


def _air_risk(
    mission: MissionPlan,
    mitigations,
    sora_version: str,
    advisories: list[SoraAdvisory],
) -> AirRiskAssessment | None:
    if mission.airspace is None:
        advisories.append(
            SoraAdvisory(
                code=SoraAdvisoryCode.AIRSPACE_DESCRIPTOR_MISSING,
                message=(
                    "Airspace descriptor is missing; Air Risk Class and SAIL "
                    "were not determined."
                ),
            )
        )
        return None
    tactical = mitigations.air_risk.tactical_mitigation if mitigations is not None else None
    return compute_air_risk(
        mission.airspace, tactical=tactical, sora_version=sora_version
    )


def _tactical_mitigation(
    air_risk: AirRiskAssessment | None,
) -> TacticalAirRiskMitigation | None:
    if air_risk is None or air_risk.tactical_bands_reduced <= 0:
        return None
    return TacticalAirRiskMitigation(
        robustness=air_risk.tactical_robustness,
        arc_bands_reduced=air_risk.tactical_bands_reduced,
    )


def _sail_or_none(grc: int | None, arc: AirRiskClass | None) -> Sail | None:
    if grc is None or arc is None:
        return None
    return determine_sail(grc, arc)


__all__ = [
    "build_sora_assessment",
]
