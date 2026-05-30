"""SORA intrinsic Ground Risk Class computation and mitigation credits."""

from dataclasses import dataclass, field

from pyproj import Geod

from estimator.core.enums import WarningCode
from estimator.core.results import (
    EstimatorWarning,
    GroundRiskEstimate,
    GroundRiskLegEstimate,
    LegEstimate,
    MissionEstimate,
)
from estimator.environment.population import GridPopulationProvider
from estimator.execution.transit import sub_segment_midpoint_fractions
from schemas.sora import (
    GrcMitigationCredit,
    GroundRiskMitigation,
    GroundRiskMitigations,
    MitigationRobustness,
    SoraAdvisory,
    SoraAdvisoryCode,
)

_R = MitigationRobustness

# Minimum final GRC reachable after applying mitigation credits. SORA never
# lowers the final GRC below 1.
_FINAL_GRC_FLOOR = 1

# (mitigation id, declaration attribute, human title) in the SORA ladder order.
_GRC_MITIGATION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("M1", "m1_strategic", "Strategic mitigations for ground risk"),
    ("M2", "m2_impact_reduction", "Effects of ground impact reduced"),
    ("M3", "m3_erp", "Emergency Response Plan (ERP)"),
)

# Signed GRC credit per mitigation and robustness, keyed by SORA version.
# Negative lowers the final GRC; positive (an insufficient ERP) raises it.
# Source: JARUS SORA 2.0 main body, final-GRC mitigation table.
_GRC_MITIGATION_CREDITS: dict[str, dict[str, dict[MitigationRobustness, int]]] = {
    "2.0": {
        "M1": {_R.NONE: 0, _R.LOW: 0, _R.MEDIUM: -1, _R.HIGH: -2},
        "M2": {_R.NONE: 0, _R.LOW: 0, _R.MEDIUM: -1, _R.HIGH: -2},
        "M3": {_R.NONE: 0, _R.LOW: 1, _R.MEDIUM: 0, _R.HIGH: -1},
    },
}


@dataclass(frozen=True, slots=True)
class GrcMitigationResult:
    """Outcome of applying the GRC mitigation ladder to the intrinsic GRC."""

    final_grc: int
    credits: list[GrcMitigationCredit] = field(default_factory=list)
    advisories: list[SoraAdvisory] = field(default_factory=list)


def supported_sora_versions() -> tuple[str, ...]:
    """Return the SORA revisions whose mitigation tables are encoded."""
    return tuple(_GRC_MITIGATION_CREDITS)


def apply_grc_mitigations(
    intrinsic_grc: int,
    mitigations: GroundRiskMitigations | None,
    *,
    sora_version: str,
) -> GrcMitigationResult:
    """Step the intrinsic GRC down by the declared M1/M2/M3 credits.

    With no declared mitigations (or an unsupported SORA version) the final GRC
    equals the intrinsic GRC, so the assessment is unchanged.
    """
    table = _GRC_MITIGATION_CREDITS.get(sora_version)
    if mitigations is None:
        return GrcMitigationResult(final_grc=intrinsic_grc)
    if table is None:
        return GrcMitigationResult(
            final_grc=intrinsic_grc,
            advisories=[_unsupported_version_advisory(sora_version)],
        )

    credits: list[GrcMitigationCredit] = []
    running_grc = intrinsic_grc
    for mitigation_id, attr, title in _GRC_MITIGATION_SPECS:
        declaration: GroundRiskMitigation = getattr(mitigations, attr)
        if not declaration.applied:
            continue
        credit = table[mitigation_id][declaration.robustness]
        credits.append(
            GrcMitigationCredit(
                mitigation_id=mitigation_id,
                title=title,
                robustness=declaration.robustness,
                grc_credit=credit,
            )
        )
        running_grc += credit

    final_grc = max(running_grc, _FINAL_GRC_FLOOR)
    return GrcMitigationResult(final_grc=final_grc, credits=credits)


def _unsupported_version_advisory(sora_version: str) -> SoraAdvisory:
    supported = ", ".join(supported_sora_versions())
    return SoraAdvisory(
        code=SoraAdvisoryCode.MITIGATION_VERSION_UNSUPPORTED,
        message=(
            f"SORA version {sora_version!r} has no encoded mitigation table; "
            f"declared mitigations were not applied. Supported versions: {supported}."
        ),
    )

_CONTROLLED_GROUND_AREA_ROW = 0
_IGRC_TABLE: tuple[tuple[int, int, int, int], ...] = (
    (1, 2, 3, 4),
    (2, 3, 4, 5),
    (3, 4, 5, 6),
    (4, 5, 6, 7),
    (5, 6, 7, 8),
    (6, 7, 8, 9),
    (7, 8, 9, 10),
)


def _dimension_column(dimension_m: float) -> int:
    if dimension_m <= 1.0:
        return 0
    if dimension_m <= 3.0:
        return 1
    if dimension_m <= 8.0:
        return 2
    return 3


def _density_row(density_ppl_km2: float) -> int:
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
    characteristic_dimension_m: float,
    density_ppl_km2: float,
) -> int:
    return _IGRC_TABLE[_density_row(density_ppl_km2)][
        _dimension_column(characteristic_dimension_m)
    ]


def controlled_ground_area_igrc(characteristic_dimension_m: float) -> int:
    return _IGRC_TABLE[_CONTROLLED_GROUND_AREA_ROW][
        _dimension_column(characteristic_dimension_m)
    ]


def compute_ground_risk(
    estimate: MissionEstimate,
    *,
    population_provider: GridPopulationProvider | None,
    characteristic_dimension_m: float | None,
    geod: Geod,
    max_segment_length_m: float | None,
) -> tuple[GroundRiskEstimate | None, list[EstimatorWarning]]:
    if population_provider is None:
        return None, []
    if characteristic_dimension_m is None:
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

    legs = [
        _ground_risk_for_leg(
            leg,
            population_provider=population_provider,
            characteristic_dimension_m=characteristic_dimension_m,
            geod=geod,
            max_segment_length_m=max_segment_length_m,
        )
        for leg in estimate.legs
    ]
    mission_igrc = max((leg.igrc for leg in legs), default=0)
    return (
        GroundRiskEstimate(
            characteristic_dimension_m=characteristic_dimension_m,
            mission_igrc=mission_igrc,
            legs=legs,
        ),
        [],
    )


def _ground_risk_for_leg(
    leg: LegEstimate,
    *,
    population_provider: GridPopulationProvider,
    characteristic_dimension_m: float,
    geod: Geod,
    max_segment_length_m: float | None,
) -> GroundRiskLegEstimate:
    densities = [
        density
        for lat, lon in _leg_sample_points(
            leg, geod=geod, max_segment_length_m=max_segment_length_m
        )
        if (density := population_provider.density_at(lat, lon)) is not None
    ]
    max_density = max(densities, default=0.0)
    return GroundRiskLegEstimate(
        leg_index=leg.leg_index,
        route_item_id=leg.route_item_id,
        max_density_ppl_km2=max_density,
        igrc=intrinsic_ground_risk_class(
            characteristic_dimension_m=characteristic_dimension_m,
            density_ppl_km2=max_density,
        ),
    )


def _leg_sample_points(
    leg: LegEstimate,
    *,
    geod: Geod,
    max_segment_length_m: float | None,
) -> list[tuple[float, float]]:
    if leg.horizontal_distance_m <= 0.0:
        return [(leg.start_lat, leg.start_lon)]

    track_deg = leg.ground_track_deg
    if track_deg is None:
        track_deg, _, _ = geod.inv(
            leg.start_lon, leg.start_lat, leg.end_lon, leg.end_lat
        )

    return [
        _point_at_fraction(leg, geod=geod, track_deg=track_deg, fraction=fraction)
        for fraction in sub_segment_midpoint_fractions(
            leg.horizontal_distance_m, max_segment_length_m
        )
    ]


def _point_at_fraction(
    leg: LegEstimate,
    *,
    geod: Geod,
    track_deg: float,
    fraction: float,
) -> tuple[float, float]:
    lon, lat, _ = geod.fwd(
        leg.start_lon,
        leg.start_lat,
        track_deg,
        leg.horizontal_distance_m * fraction,
    )
    return lat, lon


__all__ = [
    "GrcMitigationResult",
    "apply_grc_mitigations",
    "compute_ground_risk",
    "controlled_ground_area_igrc",
    "intrinsic_ground_risk_class",
    "supported_sora_versions",
]
