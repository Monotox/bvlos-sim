"""JARUS SORA 2.5 intrinsic Ground Risk Class with fail-closed mitigations."""

from dataclasses import dataclass, field
import math
from typing import NoReturn

from pyproj import Geod

from estimator.core.enums import FailureCode, FailureKind, WarningCode
from estimator.core.results import (
    EstimatorFailure,
    EstimatorWarning,
    GroundRiskEstimate,
    GroundRiskLegEstimate,
    LegEstimate,
    MissionEstimate,
)
from estimator.environment.population import GridPopulationProvider
from estimator.execution.runtime.failure_translation import error_from_failure
from estimator.execution.spatial_sampling import (
    SpatialSample,
    SpatialSamplingError,
    route_leg_samples,
)
from schemas.sora import (
    DEFAULT_SORA_VERSION,
    GrcMitigationCredit,
    GrcMitigationCreditStatus,
    GroundRiskMitigations,
    SoraAdvisory,
    SoraAdvisoryCode,
)

# JARUS SORA 2.5 Main Body, Table 2.  The left-most column satisfying both
# maximum characteristic dimension and maximum speed must be selected.
_MAX_DIMENSIONS_M = (1.0, 3.0, 8.0, 20.0, 40.0)
_MAX_SPEEDS_MPS = (25.0, 35.0, 75.0, 120.0, 200.0)
_CONTROLLED_GROUND_AREA_ROW = 0
_IGRC_TABLE: tuple[tuple[int | None, ...], ...] = (
    (1, 1, 2, 3, 3),
    (2, 3, 4, 5, 6),
    (3, 4, 5, 6, 7),
    (4, 5, 6, 7, 8),
    (5, 6, 7, 8, 9),
    (6, 7, 8, 9, 10),
    (7, 8, None, None, None),
)

_GROUND_MITIGATION_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("M1(A)", "m1a_sheltering", "Strategic mitigation by sheltering"),
    (
        "M1(B)",
        "m1b_operational_restrictions",
        "Strategic mitigation by operational restrictions",
    ),
    ("M1(C)", "m1c_ground_observation", "Tactical ground observation"),
    ("M2", "m2_impact_reduction", "Reduction of the effects of ground impact"),
)


@dataclass(frozen=True, slots=True)
class GrcMitigationResult:
    """Unmitigated GRC result; applied declarations earn no credit.

    ``credits`` records each applied declaration with
    ``credit_rejected_pending_annex_b`` and zero GRC credit.
    """

    final_grc: int
    credits: list[GrcMitigationCredit] = field(default_factory=list)
    advisories: list[SoraAdvisory] = field(default_factory=list)


def supported_sora_versions() -> tuple[str, ...]:
    return (DEFAULT_SORA_VERSION,)


def apply_grc_mitigations(
    intrinsic_grc: int,
    mitigations: GroundRiskMitigations | None,
    *,
    sora_version: str,
    controlled_ground_floor: int | None = None,
) -> GrcMitigationResult:
    """Return the intrinsic GRC, recording rejected mitigation credit.

    A robustness label and free-text evidence reference do not demonstrate the
    integrity and assurance criteria in Annex B. Crediting any applied M1/M2
    declaration would therefore be unsafe until a criteria evaluator is part of
    the operational workflow. Instead of aborting, the evaluator fails closed:
    the final GRC stays at the intrinsic GRC and every applied declaration is
    recorded as ``credit_rejected_pending_annex_b``.
    """

    if sora_version != DEFAULT_SORA_VERSION:
        supported = ", ".join(supported_sora_versions())
        raise ValueError(
            f"unsupported SORA version {sora_version!r}; supported versions: {supported}"
        )
    del controlled_ground_floor
    if mitigations is None:
        return GrcMitigationResult(final_grc=intrinsic_grc)

    applied = [
        (mitigation_id, title, getattr(mitigations, field_name))
        for mitigation_id, field_name, title in _GROUND_MITIGATION_FIELDS
        if getattr(mitigations, field_name).applied
    ]
    if not applied:
        return GrcMitigationResult(final_grc=intrinsic_grc)

    credits: list[GrcMitigationCredit] = []
    for mitigation_id, title, declaration in applied:
        # The declaration validator guarantees nonblank evidence when applied.
        assert declaration.evidence is not None
        credits.append(
            GrcMitigationCredit(
                mitigation_id=mitigation_id,
                title=title,
                robustness=declaration.robustness,
                evidence=declaration.evidence,
                nominal_grc_credit=0,
                grc_credit=0,
                credit_status=(
                    GrcMitigationCreditStatus.CREDIT_REJECTED_PENDING_ANNEX_B
                ),
            )
        )
    declared = ", ".join(mitigation_id for mitigation_id, _, _ in applied)
    advisory = SoraAdvisory(
        code=SoraAdvisoryCode.GROUND_MITIGATION_CREDIT_REJECTED,
        message=(
            f"Applied ground-risk mitigation declarations ({declared}) earn no "
            "GRC credit until an Annex B integrity-and-assurance criteria "
            "evaluator is implemented; a robustness label and free-text "
            "evidence reference cannot earn GRC credit. The assessment assumes "
            "no mitigation credit: the final GRC equals the intrinsic GRC."
        ),
    )
    return GrcMitigationResult(
        final_grc=intrinsic_grc,
        credits=credits,
        advisories=[advisory],
    )


def _aircraft_column(
    *,
    characteristic_dimension_m: float,
    max_speed_mps: float,
) -> int:
    if characteristic_dimension_m <= 0.0 or max_speed_mps <= 0.0:
        raise ValueError("SORA aircraft dimension and maximum speed must be positive")
    for column, (dimension_limit, speed_limit) in enumerate(
        zip(_MAX_DIMENSIONS_M, _MAX_SPEEDS_MPS, strict=True)
    ):
        if (
            characteristic_dimension_m <= dimension_limit
            and max_speed_mps <= speed_limit
        ):
            return column
    raise ValueError(
        "aircraft characteristic dimension / maximum speed combination is not "
        "supported by the SORA 2.5 iGRC table"
    )


def _density_row(density_ppl_km2: float) -> int:
    """Select the conservative population band at every displayed boundary.

    In particular, exactly 50,000 people/km² is conservatively assigned to the
    highest displayed density row (the row labelled ``>50k``), instead of the
    less-conservative preceding row.
    """
    if density_ppl_km2 < 0.0:
        raise ValueError("population density must be non-negative")
    if density_ppl_km2 < 5.0:
        return 1
    if density_ppl_km2 < 50.0:
        return 2
    if density_ppl_km2 < 500.0:
        return 3
    if density_ppl_km2 < 5_000.0:
        return 4
    if density_ppl_km2 < 50_000.0:
        return 5
    return 6


def intrinsic_ground_risk_class(
    *,
    characteristic_dimension_m: float | None,
    max_speed_mps: float,
    density_ppl_km2: float,
    aircraft_mass_kg: float | None = None,
) -> int:
    if aircraft_mass_kg is not None and aircraft_mass_kg <= 0.0:
        raise ValueError("SORA aircraft mass must be positive")
    if (
        aircraft_mass_kg is not None
        and aircraft_mass_kg <= 0.250
        and max_speed_mps <= 25.0
    ):
        return 1
    if characteristic_dimension_m is None:
        raise ValueError("SORA aircraft characteristic dimension is required")
    column = _aircraft_column(
        characteristic_dimension_m=characteristic_dimension_m,
        max_speed_mps=max_speed_mps,
    )
    value = _IGRC_TABLE[_density_row(density_ppl_km2)][column]
    if value is None:
        raise ValueError(
            "population density / aircraft combination is outside the SORA 2.5 table"
        )
    return value


def controlled_ground_area_igrc(
    characteristic_dimension_m: float,
    max_speed_mps: float,
) -> int:
    column = _aircraft_column(
        characteristic_dimension_m=characteristic_dimension_m,
        max_speed_mps=max_speed_mps,
    )
    value = _IGRC_TABLE[_CONTROLLED_GROUND_AREA_ROW][column]
    assert value is not None
    return value


def compute_ground_risk(
    estimate: MissionEstimate,
    *,
    population_provider: GridPopulationProvider | None,
    characteristic_dimension_m: float | None,
    max_speed_mps: float | None = None,
    aircraft_mass_kg: float | None = None,
    sora_version: str = DEFAULT_SORA_VERSION,
    geod: Geod,
    max_segment_length_m: float | None,
    population_assessment_buffer_m: float = 0.0,
) -> tuple[GroundRiskEstimate | None, list[EstimatorWarning]]:
    if population_provider is None:
        return None, []
    lightweight_exception = (
        aircraft_mass_kg is not None
        and aircraft_mass_kg <= 0.250
        and max_speed_mps is not None
        and max_speed_mps <= 25.0
    )
    if characteristic_dimension_m is None and not lightweight_exception:
        return None, [
            EstimatorWarning(
                code=WarningCode.POPULATION_DENSITY_DIMENSION_MISSING,
                message=(
                    "Population grid is configured but "
                    "vehicle.characteristic_dimension_m is missing; "
                    "SORA ground risk class was not computed."
                ),
                leg_index=None,
                route_item_index=None,
                route_item_id=None,
            )
        ]
    if max_speed_mps is None:
        _raise_ground_risk_failure(
            estimate,
            code=FailureCode.SORA_INPUT_UNSUPPORTED,
            message="vehicle.performance.max_speed_mps is required for SORA 2.5 iGRC",
            kind=FailureKind.INVALID_INPUT,
        )
    if sora_version not in supported_sora_versions():
        _raise_ground_risk_failure(
            estimate,
            code=FailureCode.SORA_INPUT_UNSUPPORTED,
            message=f"SORA version {sora_version!r} is unsupported",
            kind=FailureKind.UNSUPPORTED,
        )
    if (
        not math.isfinite(population_assessment_buffer_m)
        or population_assessment_buffer_m < 0.0
    ):
        _raise_ground_risk_failure(
            estimate,
            code=FailureCode.SORA_INPUT_UNSUPPORTED,
            message="population assessment buffer must be finite and non-negative",
            kind=FailureKind.INVALID_INPUT,
        )

    assert max_speed_mps is not None
    try:
        column = (
            None
            if lightweight_exception
            else _aircraft_column(
                characteristic_dimension_m=characteristic_dimension_m,
                max_speed_mps=max_speed_mps,
            )
        )
        controlled_floor = (
            1
            if lightweight_exception
            else controlled_ground_area_igrc(
                characteristic_dimension_m,
                max_speed_mps,
            )
        )
        samples_by_leg = route_leg_samples(
            estimate.legs,
            geod=geod,
            max_segment_length_m=max_segment_length_m,
            resolution_providers=(population_provider,),
        )
    except (ValueError, SpatialSamplingError) as exc:
        leg = exc.leg if isinstance(exc, SpatialSamplingError) else None
        _raise_ground_risk_failure(
            estimate,
            code=(
                FailureCode.INVALID_GEOMETRY
                if isinstance(exc, SpatialSamplingError)
                else FailureCode.SORA_INPUT_UNSUPPORTED
            ),
            message=str(exc),
            kind=FailureKind.INVALID_INPUT,
            leg=leg,
        )

    leg_results = [
        _ground_risk_for_leg(
            leg,
            samples=samples,
            population_provider=population_provider,
            characteristic_dimension_m=characteristic_dimension_m,
            max_speed_mps=max_speed_mps,
            aircraft_mass_kg=aircraft_mass_kg,
            estimate=estimate,
            population_assessment_buffer_m=population_assessment_buffer_m,
            geod=geod,
        )
        for leg, samples in zip(estimate.legs, samples_by_leg, strict=True)
    ]
    legs = [result[0] for result in leg_results]
    numerical_dilation_m = max((result[1] for result in leg_results), default=0.0)
    mission_igrc = max((leg.igrc for leg in legs), default=0)
    return (
        GroundRiskEstimate(
            characteristic_dimension_m=characteristic_dimension_m,
            aircraft_mass_kg=aircraft_mass_kg,
            max_speed_mps=max_speed_mps,
            sora_version=sora_version,
            aircraft_column=None if column is None else column + 1,
            controlled_ground_area_reference_igrc=controlled_floor,
            population_assessment_buffer_m=population_assessment_buffer_m,
            population_numerical_dilation_m=numerical_dilation_m,
            mission_igrc=mission_igrc,
            legs=legs,
        ),
        [],
    )


def _ground_risk_for_leg(
    leg: LegEstimate,
    *,
    samples: list[SpatialSample],
    population_provider: GridPopulationProvider,
    characteristic_dimension_m: float | None,
    max_speed_mps: float,
    aircraft_mass_kg: float | None,
    estimate: MissionEstimate,
    population_assessment_buffer_m: float,
    geod: Geod,
) -> tuple[GroundRiskLegEstimate, float]:
    densities: list[float] = []
    max_numerical_dilation_m = 0.0
    for index, sample in enumerate(samples):
        half_gap_m = 0.5 * _maximum_adjacent_sample_gap_m(
            samples,
            index=index,
            geod=geod,
        )
        # Triangle inequality gives a path-shape-independent bound: every point
        # within the declared footprint of any unsampled route point is within
        # buffer + half-gap of a neighbouring sample. A Pythagorean radius is
        # insufficient on curved paths where the two offsets are not orthogonal.
        coverage_radius_m = population_assessment_buffer_m + half_gap_m
        max_numerical_dilation_m = max(
            max_numerical_dilation_m,
            coverage_radius_m - population_assessment_buffer_m,
        )
        density = population_provider.conservative_max_density_in_radius(
            sample.lat,
            sample.lon,
            coverage_radius_m,
            geod=geod,
        )
        if density is None:
            _raise_ground_risk_failure(
                estimate,
                code=FailureCode.POPULATION_COVERAGE_MISSING,
                message=(
                    "Population coverage is missing for the assessed route footprint."
                    if population_assessment_buffer_m > 0.0
                    else "Population coverage is missing at a sampled route position."
                ),
                kind=FailureKind.INVALID_INPUT,
                leg=leg,
                context={"sample_lat": sample.lat, "sample_lon": sample.lon},
            )
        assert density is not None
        densities.append(density)

    max_density = max(densities, default=0.0)
    try:
        igrc = intrinsic_ground_risk_class(
            characteristic_dimension_m=characteristic_dimension_m,
            max_speed_mps=max_speed_mps,
            density_ppl_km2=max_density,
            aircraft_mass_kg=aircraft_mass_kg,
        )
    except ValueError as exc:
        _raise_ground_risk_failure(
            estimate,
            code=FailureCode.SORA_INPUT_UNSUPPORTED,
            message=str(exc),
            kind=FailureKind.UNSUPPORTED,
            leg=leg,
            context={"max_density_ppl_km2": max_density},
        )
    return (
        GroundRiskLegEstimate(
            leg_index=leg.leg_index,
            route_item_id=leg.route_item_id,
            max_density_ppl_km2=max_density,
            igrc=igrc,
        ),
        max_numerical_dilation_m,
    )


def _maximum_adjacent_sample_gap_m(
    samples: list[SpatialSample],
    *,
    index: int,
    geod: Geod,
) -> float:
    sample = samples[index]
    distances: list[float] = []
    for other_index in (index - 1, index + 1):
        if not 0 <= other_index < len(samples):
            continue
        other = samples[other_index]
        _, _, distance_m = geod.inv(sample.lon, sample.lat, other.lon, other.lat)
        distances.append(abs(float(distance_m)))
    return max(distances, default=0.0)


def _raise_ground_risk_failure(
    estimate: MissionEstimate,
    *,
    code: FailureCode,
    message: str,
    kind: FailureKind,
    leg: LegEstimate | None = None,
    context: dict[str, str | int | float | bool | None] | None = None,
) -> NoReturn:
    failure = EstimatorFailure(
        kind=kind,
        code=code,
        message=message,
        leg_index=leg.leg_index if leg is not None else None,
        route_item_index=leg.route_item_index if leg is not None else None,
        route_item_id=leg.route_item_id if leg is not None else None,
        context=context or {},
    )
    raise error_from_failure(
        failure,
        partial_legs=estimate.legs,
        energy=estimate.energy,
        resource=estimate.resource,
        link=estimate.link,
        geofence=estimate.geofence,
        landing_zone=estimate.landing_zone,
        obstacle=estimate.obstacle,
        weather=estimate.weather,
        totals_are_partial=False,
        warnings=estimate.warnings,
        metadata=estimate.metadata,
    )


__all__ = [
    "GrcMitigationResult",
    "apply_grc_mitigations",
    "compute_ground_risk",
    "controlled_ground_area_igrc",
    "intrinsic_ground_risk_class",
    "supported_sora_versions",
]
