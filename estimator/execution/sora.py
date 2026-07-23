"""SORA pre-assessment orchestration.

Combines the SORA 2.5 Ground Risk Class with the initial/residual Air Risk Class
and SAIL determination. Ground mitigation declarations fail closed until Annex B
criteria can be evaluated: they earn no GRC credit and are recorded in the
assessment as ``credit_rejected_pending_annex_b``. Tactical air-risk mitigations
are represented as TMPR requirements and never lower residual ARC.
"""

import math

from pyproj import Geod

from estimator.core.results import MissionEstimate
from estimator.environment.population import PopulationEvidence
from estimator.environment.terrain import TerrainProvider
from estimator.execution.air_risk import AirRiskAssessment, compute_air_risk
from estimator.execution.containment import derive_containment_requirement
from estimator.execution.ground_risk import apply_grc_mitigations
from estimator.execution.sail import applicable_osos, determine_sail
from schemas.mission import MissionPlan
from schemas.sora import (
    DEFAULT_SORA_VERSION,
    AirRiskClass,
    GrcMitigationCredit,
    GroundRiskFootprint,
    Sail,
    PopulationEvidenceSummary,
    SoraAdvisory,
    SoraAdvisoryCode,
    SoraAssessment,
    TacticalMitigationRequirement,
)
from schemas.vehicle import VehicleProfile


def build_sora_assessment(
    mission: MissionPlan,
    vehicle: VehicleProfile,
    estimate: MissionEstimate,
    *,
    population_evidence: PopulationEvidence | None,
    terrain_provider: TerrainProvider | None,
) -> SoraAssessment:
    """Assemble the SORA pre-assessment from estimator outputs and airspace."""
    advisories: list[SoraAdvisory] = []
    mitigations = mission.sora
    sora_version = (
        mitigations.version if mitigations is not None else DEFAULT_SORA_VERSION
    )
    footprint = _validated_ground_risk_footprint(
        mission,
        estimate,
        terrain_provider=terrain_provider,
    )
    population_summary = _validated_population_evidence(mission, population_evidence)

    intrinsic_grc, final_grc, grc_credits = _ground_risk(
        estimate, mitigations, sora_version, advisories
    )

    air_risk = _air_risk(mission, mitigations, sora_version, advisories)
    initial_arc = air_risk.initial_arc if air_risk is not None else None
    residual_arc = air_risk.residual_arc if air_risk is not None else None

    intrinsic_sail = _sail_or_none(intrinsic_grc, initial_arc)
    sail = _sail_or_none(final_grc, residual_arc)
    osos = []
    if sail is None and final_grc is not None and final_grc > 7:
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

    if mission.airspace is None:
        raise AssertionError("validated SORA assessment unexpectedly lacks airspace")

    aircraft_mass_kg = (
        vehicle.mass.operating_mass_kg
        if vehicle.mass.operating_mass_kg is not None
        else vehicle.mass.max_takeoff_kg
    )
    containment = derive_containment_requirement(
        aircraft_mass_kg=aircraft_mass_kg,
        characteristic_dimension_m=vehicle.characteristic_dimension_m,
        max_speed_mps=vehicle.performance.max_speed_mps,
        sail=sail,
        footprint=footprint,
        evidence=(
            mitigations.containment_evidence if mitigations is not None else None
        ),
    )
    advisories.append(
        SoraAdvisory(
            code=SoraAdvisoryCode.CONTAINMENT_COMPLIANCE_NOT_ASSESSED,
            message=(
                "Step 8 operational limits and required robustness were derived, "
                "but Annex E containment compliance was not assessed."
            ),
        )
    )
    if not containment.within_specific_category_method_scope:
        advisories.append(
            SoraAdvisory(
                code=SoraAdvisoryCode.CONTAINMENT_OUT_OF_SCOPE,
                message=(
                    "The Step 8 result is outside the SORA 2.5 specific-category "
                    "containment tables for the declared operation."
                ),
            )
        )
    if osos:
        advisories.append(
            SoraAdvisory(
                code=SoraAdvisoryCode.OSO_COMPLIANCE_NOT_ASSESSED,
                message=(
                    "Table 14 identifies applicable OSO robustness only; OSO "
                    "compliance and supporting evidence were not assessed."
                ),
            )
        )

    within_specific_category_method_scope = (
        sail is not None and containment.within_specific_category_method_scope
    )

    if sail is None:
        category_outcome = "certified"
    elif containment.within_specific_category_method_scope:
        category_outcome = "specific"
    else:
        category_outcome = "specific_method_out_of_scope"

    return SoraAssessment(
        mission_id=mission.mission_id,
        sora_version=sora_version,
        characteristic_dimension_m=vehicle.characteristic_dimension_m,
        max_speed_mps=vehicle.performance.max_speed_mps,
        aircraft_mass_kg=aircraft_mass_kg,
        ground_risk_footprint=footprint,
        population_evidence=population_summary,
        population_numerical_dilation_m=(
            estimate.ground_risk.population_numerical_dilation_m
            if estimate.ground_risk is not None
            else 0.0
        ),
        intrinsic_grc=intrinsic_grc,
        final_grc=final_grc,
        ground_risk_mitigations=grc_credits,
        operational_and_contingency_volume_assessment_reference=(
            mission.airspace.operational_and_contingency_volume_assessment_reference
        ),
        worst_case_arc_declared=mission.airspace.worst_case_arc_declared,
        initial_air_risk_class=initial_arc,
        air_risk_class=residual_arc,
        air_risk_rationale=(air_risk.rationale if air_risk is not None else None),
        strategic_mitigation_applied=(
            air_risk.strategic_mitigation_applied if air_risk is not None else False
        ),
        tactical_mitigation_requirement=_tactical_requirement(air_risk),
        intrinsic_sail=intrinsic_sail,
        sail=sail,
        category_outcome=category_outcome,
        containment_requirement=containment,
        applicable_osos=osos,
        within_specific_category_method_scope=(within_specific_category_method_scope),
        advisories=advisories,
    )


def _validated_population_evidence(
    mission: MissionPlan,
    evidence: PopulationEvidence | None,
) -> PopulationEvidenceSummary:
    if evidence is None:
        raise ValueError(
            "the sora command requires a population-grid.v2 asset with "
            "conservative-cell values, source/resolution provenance, validity "
            "dates, and a transient-population assessment"
        )
    departure = mission.departure_time
    if departure is None:
        raise ValueError(
            "mission.departure_time is required to verify SORA population-evidence "
            "validity"
        )
    if departure.tzinfo is None or departure.utcoffset() is None:
        raise ValueError("mission.departure_time must include a UTC offset")
    if not evidence.valid_from <= departure <= evidence.valid_until:
        raise ValueError(
            "mission.departure_time falls outside the population evidence validity "
            "interval"
        )
    return PopulationEvidenceSummary(
        source=evidence.source,
        population_year=evidence.population_year,
        native_resolution_m=evidence.native_resolution_m,
        effective_resolution_m=evidence.effective_resolution_m,
        value_semantics=evidence.value_semantics,
        authority_assessment_reference=evidence.authority_assessment_reference,
        valid_from=evidence.valid_from,
        valid_until=evidence.valid_until,
        transient_population_assessment_reference=(
            evidence.transient_population_assessment_reference
        ),
        operational_footprint_assemblies_present=(
            evidence.operational_footprint_assemblies_present
        ),
    )


def _validated_ground_risk_footprint(
    mission: MissionPlan,
    estimate: MissionEstimate,
    *,
    terrain_provider: TerrainProvider | None,
) -> GroundRiskFootprint:
    if mission.sora is None or mission.sora.ground_risk_footprint is None:
        raise ValueError(
            "SORA 2.5 requires an explicit assessed ground_risk_footprint "
            "covering the operational/contingency volume plus Ground Risk Buffer; "
            "centerline-only population output is diagnostic and cannot be used."
        )
    footprint = mission.sora.ground_risk_footprint
    resolved_route_max_agl_m = _conservative_route_max_agl_m(
        estimate,
        terrain_provider=terrain_provider,
    )
    required_maximum_height_agl_m = (
        resolved_route_max_agl_m + footprint.vertical_contingency_margin_m
    )
    if footprint.maximum_height_agl_m < required_maximum_height_agl_m:
        raise ValueError(
            "ground-risk footprint maximum_height_agl_m must cover the resolved "
            "route maximum AGL plus vertical_contingency_margin_m "
            f"({required_maximum_height_agl_m:.3f} m required)"
        )
    if (
        mission.airspace is not None
        and mission.airspace.max_altitude_agl_m < footprint.maximum_height_agl_m
    ):
        raise ValueError(
            "airspace.max_altitude_agl_m must cover the terrain-checked "
            "ground-risk footprint maximum_height_agl_m"
        )
    if footprint.ground_risk_buffer_m < footprint.maximum_height_agl_m:
        raise ValueError(
            "initial_1_to_1 ground_risk_buffer_m must be at least the "
            "terrain-checked maximum_height_agl_m"
        )
    if (
        estimate.ground_risk is not None
        and estimate.ground_risk.population_assessment_buffer_m
        != footprint.total_buffer_m
    ):
        raise ValueError(
            "ground-risk estimate was not computed over the declared SORA footprint"
        )
    return footprint


def _conservative_route_max_agl_m(
    estimate: MissionEstimate,
    *,
    terrain_provider: TerrainProvider | None,
) -> float:
    if terrain_provider is None:
        raise ValueError(
            "the sora command requires terrain coverage to verify the declared "
            "maximum height AGL"
        )
    minimum_method = getattr(
        terrain_provider,
        "conservative_min_elevation_along_segment",
        None,
    )
    if not callable(minimum_method):
        raise ValueError(
            "the configured terrain provider cannot prove conservative minimum "
            "elevation along route segments"
        )
    geod = Geod(ellps="WGS84")
    maximum_agl_m = float("-inf")
    for leg in estimate.legs:
        coordinates = leg.path_coordinates or (
            (leg.start_lat, leg.start_lon),
            (leg.end_lat, leg.end_lon),
        )
        if len(coordinates) == 1:
            coordinates = (coordinates[0], coordinates[0])
        leg_max_altitude_m = max(leg.start_alt_amsl_m, leg.end_alt_amsl_m)
        for start, end in zip(coordinates, coordinates[1:]):
            start_lat, start_lon = start
            end_lat, end_lon = end
            terrain_min_m = minimum_method(
                start_lat,
                start_lon,
                end_lat,
                end_lon,
                geod=geod,
            )
            if (
                terrain_min_m is None
                or isinstance(terrain_min_m, bool)
                or not isinstance(terrain_min_m, int | float)
                or not math.isfinite(float(terrain_min_m))
            ):
                raise ValueError(
                    "terrain coverage cannot prove maximum AGL over the full route"
                )
            maximum_agl_m = max(
                maximum_agl_m,
                leg_max_altitude_m - float(terrain_min_m),
            )
    if maximum_agl_m == float("-inf"):
        raise ValueError("the sora command requires at least one resolved route leg")
    return maximum_agl_m


def _ground_risk(
    estimate: MissionEstimate,
    mitigations,
    sora_version: str,
    advisories: list[SoraAdvisory],
) -> tuple[int | None, int | None, list[GrcMitigationCredit]]:
    ground_risk = estimate.ground_risk
    if ground_risk is None:
        raise ValueError(
            "Ground Risk Class was not computed; provide complete population "
            "coverage and vehicle characteristic dimension / maximum speed."
        )
    if ground_risk.sora_version != sora_version:
        raise ValueError(
            "ground-risk estimate and requested SORA assessment use different "
            "methodology versions"
        )

    intrinsic_grc = ground_risk.mission_igrc
    declared = mitigations.ground_risk_mitigations if mitigations is not None else None
    result = apply_grc_mitigations(
        intrinsic_grc,
        declared,
        sora_version=sora_version,
        controlled_ground_floor=ground_risk.controlled_ground_area_reference_igrc,
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
        raise ValueError("Airspace descriptor is required for a SORA 2.5 assessment.")
    tactical = (
        mitigations.air_risk.tactical_mitigation if mitigations is not None else None
    )
    return compute_air_risk(
        mission.airspace, tactical=tactical, sora_version=sora_version
    )


def _tactical_requirement(
    air_risk: AirRiskAssessment | None,
) -> TacticalMitigationRequirement | None:
    if air_risk is None:
        return None
    return TacticalMitigationRequirement(
        required_robustness=air_risk.tmpr_required_robustness,
    )


def _sail_or_none(grc: int | None, arc: AirRiskClass | None) -> Sail | None:
    if grc is None or arc is None:
        return None
    return determine_sail(grc, arc)


__all__ = [
    "build_sora_assessment",
]
