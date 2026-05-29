"""SORA pre-assessment orchestration.

Combines the Ground Risk Class (computed by the estimator from the population
grid) with the Air Risk Class and SAIL determination to produce a whole-mission
:class:`SoraAssessment`. Mitigations that would lower the final GRC are out of
scope, so the final GRC equals the intrinsic GRC.
"""

from estimator.core.results import MissionEstimate
from estimator.execution.air_risk import compute_air_risk
from estimator.execution.sail import applicable_osos, determine_sail
from schemas.mission import MissionPlan
from schemas.sora import (
    AirRiskClass,
    Sail,
    SoraAdvisory,
    SoraAdvisoryCode,
    SoraAssessment,
)
from schemas.vehicle import VehicleProfile


def build_sora_assessment(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    estimate: MissionEstimate,
) -> SoraAssessment:
    """Assemble the SORA pre-assessment from estimator outputs and airspace."""
    advisories: list[SoraAdvisory] = []

    ground_risk = estimate.ground_risk
    if ground_risk is None:
        intrinsic_grc: int | None = None
        final_grc: int | None = None
        advisories.append(
            SoraAdvisory(
                code=SoraAdvisoryCode.GROUND_RISK_NOT_COMPUTED,
                message=(
                    "Ground Risk Class was not computed; provide a mission "
                    "population grid and vehicle characteristic_dimension_m."
                ),
            )
        )
    else:
        intrinsic_grc = ground_risk.mission_igrc
        final_grc = intrinsic_grc

    initial_arc: AirRiskClass | None = None
    residual_arc: AirRiskClass | None = None
    strategic_mitigation_applied = False
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
    else:
        air_risk = compute_air_risk(mission.airspace)
        initial_arc = air_risk.initial_arc
        residual_arc = air_risk.residual_arc
        strategic_mitigation_applied = air_risk.strategic_mitigation_applied

    sail: Sail | None = None
    osos = []
    if final_grc is not None and residual_arc is not None:
        sail = determine_sail(final_grc, residual_arc)
        if sail == Sail.CERTIFIED:
            advisories.append(
                SoraAdvisory(
                    code=SoraAdvisoryCode.OPERATION_OUTSIDE_SPECIFIC_CATEGORY,
                    message=(
                        "Final GRC exceeds 7; the operation falls outside the "
                        "specific category and requires the certified category."
                    ),
                )
            )
        else:
            osos = applicable_osos(sail)

    return SoraAssessment(
        mission_id=mission.mission_id,
        characteristic_dimension_m=vehicle.characteristic_dimension_m,
        intrinsic_grc=intrinsic_grc,
        final_grc=final_grc,
        initial_air_risk_class=initial_arc,
        air_risk_class=residual_arc,
        strategic_mitigation_applied=strategic_mitigation_applied,
        sail=sail,
        applicable_osos=osos,
        advisories=advisories,
    )


__all__ = [
    "build_sora_assessment",
]
