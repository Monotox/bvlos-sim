"""SORA intrinsic Ground Risk Class computation."""

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
    "compute_ground_risk",
    "controlled_ground_area_igrc",
    "intrinsic_ground_risk_class",
]
