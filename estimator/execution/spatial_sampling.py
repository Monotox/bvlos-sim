"""Safety-oriented sampling of the complete route footprint.

The transit estimator historically represented a turn arc as a zero-displacement
leg at its waypoint.  Risk checks cannot treat that representation as a point:
this module reconstructs the circular fillet from its adjacent tracks and also
trims the adjacent straight samples to the arc tangent points.
"""

import bisect
from dataclasses import dataclass
import math
from typing import Protocol, Sequence

from pyproj import Geod

from estimator.core.enums import LegPhase
from estimator.core.results import LegEstimate
from estimator.math.wind_triangle import normalize_signed

_DEFAULT_SAFETY_SPACING_M = 50.0
_MIN_SUPPORTED_SPACING_M = 0.01
_POSITION_TOLERANCE_M = 0.01
_ANGLE_TOLERANCE_DEG = 1e-6


class SamplingResolutionProvider(Protocol):
    def recommended_sample_spacing_m(self, lat: float) -> float:
        """Return a maximum sampling interval appropriate for this provider."""


@dataclass(frozen=True, slots=True)
class SpatialSample:
    leg: LegEstimate
    fraction: float
    lat: float
    lon: float
    altitude_amsl_m: float


class SpatialSamplingError(ValueError):
    """Raised when a stored route leg cannot be mapped to a safe footprint."""

    def __init__(self, message: str, *, leg: LegEstimate) -> None:
        super().__init__(message)
        self.leg = leg


@dataclass(frozen=True, slots=True)
class _TurnFootprint:
    leg: LegEstimate
    waypoint_lat: float
    waypoint_lon: float
    tangent_start_east_m: float
    tangent_start_north_m: float
    tangent_end_east_m: float
    tangent_end_north_m: float
    center_east_m: float
    center_north_m: float
    signed_turn_rad: float
    radius_m: float
    entry_lat: float
    entry_lon: float
    exit_lat: float
    exit_lon: float
    adjust_adjacent_straights: bool

    def point_at(self, fraction: float, geod: Geod) -> tuple[float, float]:
        start_radius_east = self.tangent_start_east_m - self.center_east_m
        start_radius_north = self.tangent_start_north_m - self.center_north_m
        # Heading increases clockwise, whereas the standard Cartesian rotation
        # below is counter-clockwise, hence the negative signed turn angle.
        rotation = -self.signed_turn_rad * fraction
        cos_rotation = math.cos(rotation)
        sin_rotation = math.sin(rotation)
        east = self.center_east_m + (
            start_radius_east * cos_rotation - start_radius_north * sin_rotation
        )
        north = self.center_north_m + (
            start_radius_east * sin_rotation + start_radius_north * cos_rotation
        )
        return _offset_point(
            self.waypoint_lat,
            self.waypoint_lon,
            east_m=east,
            north_m=north,
            geod=geod,
        )

    def tangent_start(self, geod: Geod) -> tuple[float, float]:
        return _offset_point(
            self.waypoint_lat,
            self.waypoint_lon,
            east_m=self.tangent_start_east_m,
            north_m=self.tangent_start_north_m,
            geod=geod,
        )

    def tangent_end(self, geod: Geod) -> tuple[float, float]:
        return _offset_point(
            self.waypoint_lat,
            self.waypoint_lon,
            east_m=self.tangent_end_east_m,
            north_m=self.tangent_end_north_m,
            geod=geod,
        )


def route_leg_samples(
    legs: Sequence[LegEstimate],
    *,
    geod: Geod,
    max_segment_length_m: float | None,
    resolution_providers: Sequence[object] = (),
    hazard_footprint_m: float | None = None,
) -> list[list[SpatialSample]]:
    """Sample every leg, including endpoints and reconstructed turn arcs.

    ``max_segment_length_m`` remains an upper bound when supplied.  Omitting it
    no longer collapses a whole leg to one midpoint: a conservative default is
    combined with provider grid resolution and known hazard footprint sizes.
    """

    spacing_m = _sampling_spacing_m(
        legs,
        max_segment_length_m=max_segment_length_m,
        resolution_providers=resolution_providers,
        hazard_footprint_m=hazard_footprint_m,
    )
    turns = {
        index: _reconstruct_turn(legs, index=index, geod=geod)
        for index, leg in enumerate(legs)
        if leg.phase == LegPhase.TURN_ARC and leg.path_coordinates is None
    }

    sampled: list[list[SpatialSample]] = []
    for index, leg in enumerate(legs):
        if leg.path_coordinates is not None:
            sampled.append(
                _sample_polyline_leg(
                    leg,
                    coordinates=leg.path_coordinates,
                    geod=geod,
                    spacing_m=spacing_m,
                )
            )
            continue
        turn = turns.get(index)
        if turn is not None:
            sampled.append(_sample_turn(turn, geod=geod, spacing_m=spacing_m))
            continue

        start_lat, start_lon = leg.start_lat, leg.start_lon
        end_lat, end_lon = leg.end_lat, leg.end_lon
        previous_turn = turns.get(index - 1)
        next_turn = turns.get(index + 1)
        if previous_turn is not None and previous_turn.adjust_adjacent_straights:
            start_lat, start_lon = previous_turn.tangent_end(geod)
        if next_turn is not None and next_turn.adjust_adjacent_straights:
            end_lat, end_lon = next_turn.tangent_start(geod)
        sampled.append(
            _sample_geodesic_leg(
                leg,
                start_lat=start_lat,
                start_lon=start_lon,
                end_lat=end_lat,
                end_lon=end_lon,
                geod=geod,
                spacing_m=spacing_m,
            )
        )
    return sampled


def _sample_polyline_leg(
    leg: LegEstimate,
    *,
    coordinates: tuple[tuple[float, float], ...],
    geod: Geod,
    spacing_m: float,
) -> list[SpatialSample]:
    """Sample a stored lon/lat path, preserving its exact vertices."""

    if len(coordinates) < 2:
        raise SpatialSamplingError(
            "stored leg path must contain at least two coordinates",
            leg=leg,
        )
    for lon, lat in coordinates:
        if (
            not math.isfinite(lat)
            or not math.isfinite(lon)
            or not -90.0 <= lat <= 90.0
            or not -180.0 <= lon <= 180.0
        ):
            raise SpatialSamplingError(
                "stored leg path contains an invalid coordinate",
                leg=leg,
            )
    _require_connected_endpoint(
        leg,
        coordinate=coordinates[0],
        expected_lat=leg.start_lat,
        expected_lon=leg.start_lon,
        label="start",
        geod=geod,
    )
    _require_connected_endpoint(
        leg,
        coordinate=coordinates[-1],
        expected_lat=leg.end_lat,
        expected_lon=leg.end_lon,
        label="end",
        geod=geod,
    )

    segments: list[tuple[float, float, float, float, float, float, float]] = []
    total_distance_m = 0.0
    for (start_lon, start_lat), (end_lon, end_lat) in zip(coordinates, coordinates[1:]):
        track_deg, _, distance_m = geod.inv(
            start_lon,
            start_lat,
            end_lon,
            end_lat,
        )
        distance_m = abs(float(distance_m))
        if distance_m <= _POSITION_TOLERANCE_M:
            continue
        segments.append(
            (
                start_lon,
                start_lat,
                end_lon,
                end_lat,
                float(track_deg),
                distance_m,
                total_distance_m,
            )
        )
        total_distance_m += distance_m
    if total_distance_m <= _POSITION_TOLERANCE_M:
        raise SpatialSamplingError(
            "stored leg path has no positive horizontal length",
            leg=leg,
        )

    samples: list[SpatialSample] = []
    for segment_index, (
        start_lon,
        start_lat,
        end_lon,
        end_lat,
        track_deg,
        distance_m,
        cumulative_start_m,
    ) in enumerate(segments):
        intervals = max(1, math.ceil(distance_m / spacing_m))
        first_index = 0 if segment_index == 0 else 1
        for index in range(first_index, intervals + 1):
            segment_fraction = index / intervals
            lon, lat, _ = geod.fwd(
                start_lon,
                start_lat,
                track_deg,
                distance_m * segment_fraction,
            )
            if index == 0:
                lon, lat = start_lon, start_lat
            elif index == intervals:
                lon, lat = end_lon, end_lat
            fraction = (
                cumulative_start_m + distance_m * segment_fraction
            ) / total_distance_m
            samples.append(
                SpatialSample(
                    leg=leg,
                    fraction=fraction,
                    lat=lat,
                    lon=lon,
                    altitude_amsl_m=_interpolate_altitude(leg, fraction),
                )
            )
    return _include_vertical_completion_sample(
        samples,
        leg=leg,
        end_lat=leg.end_lat,
        end_lon=leg.end_lon,
    )


def _require_connected_endpoint(
    leg: LegEstimate,
    *,
    coordinate: tuple[float, float],
    expected_lat: float,
    expected_lon: float,
    label: str,
    geod: Geod,
) -> None:
    lon, lat = coordinate
    _, _, distance_m = geod.inv(lon, lat, expected_lon, expected_lat)
    if abs(float(distance_m)) > _POSITION_TOLERANCE_M:
        raise SpatialSamplingError(
            f"stored leg path {label} is disconnected from the leg endpoint",
            leg=leg,
        )


def _sampling_spacing_m(
    legs: Sequence[LegEstimate],
    *,
    max_segment_length_m: float | None,
    resolution_providers: Sequence[object],
    hazard_footprint_m: float | None,
) -> float:
    candidates = [_DEFAULT_SAFETY_SPACING_M]
    if max_segment_length_m is not None:
        if not math.isfinite(max_segment_length_m) or max_segment_length_m <= 0.0:
            leg = legs[0] if legs else None
            if leg is not None:
                raise SpatialSamplingError(
                    "max_segment_length_m must be finite and positive",
                    leg=leg,
                )
            raise ValueError("max_segment_length_m must be finite and positive")
        candidates.append(max_segment_length_m)
    if hazard_footprint_m is not None:
        if not math.isfinite(hazard_footprint_m) or hazard_footprint_m < 0.0:
            leg = legs[0] if legs else None
            if leg is not None:
                raise SpatialSamplingError(
                    "hazard_footprint_m must be finite and non-negative",
                    leg=leg,
                )
            raise ValueError("hazard_footprint_m must be finite and non-negative")
        if hazard_footprint_m > 0.0:
            candidates.append(hazard_footprint_m / 2.0)

    representative_lats = [
        coordinate for leg in legs for coordinate in (leg.start_lat, leg.end_lat)
    ] or [0.0]
    for provider in resolution_providers:
        resolver = getattr(provider, "recommended_sample_spacing_m", None)
        if not callable(resolver):
            continue
        for lat in representative_lats:
            value = float(resolver(lat))
            if not math.isfinite(value) or value <= 0.0:
                leg = legs[0] if legs else None
                if leg is not None:
                    raise SpatialSamplingError(
                        "hazard provider returned an invalid sampling resolution",
                        leg=leg,
                    )
                raise ValueError(
                    "hazard provider returned an invalid sampling resolution"
                )
            candidates.append(value)
    spacing_m = min(candidates)
    if spacing_m < _MIN_SUPPORTED_SPACING_M:
        leg = legs[0] if legs else None
        message = (
            "required spatial resolution is below the supported 0.01 m safety limit"
        )
        if leg is not None:
            raise SpatialSamplingError(message, leg=leg)
        raise ValueError(message)
    return spacing_m


def _sample_geodesic_leg(
    leg: LegEstimate,
    *,
    start_lat: float,
    start_lon: float,
    end_lat: float,
    end_lon: float,
    geod: Geod,
    spacing_m: float,
) -> list[SpatialSample]:
    track_deg, _, distance_m = geod.inv(start_lon, start_lat, end_lon, end_lat)
    distance_m = abs(float(distance_m))
    if distance_m <= _POSITION_TOLERANCE_M:
        start = SpatialSample(
            leg=leg,
            fraction=0.0,
            lat=start_lat,
            lon=start_lon,
            altitude_amsl_m=leg.start_alt_amsl_m,
        )
        if math.isclose(leg.start_alt_amsl_m, leg.end_alt_amsl_m):
            return [start]
        if leg.timing_profile is None:
            raise SpatialSamplingError(
                "altitude-changing leg has no transit timing profile",
                leg=leg,
            )
        return [
            start,
            SpatialSample(
                leg=leg,
                fraction=1.0,
                lat=end_lat,
                lon=end_lon,
                altitude_amsl_m=leg.end_alt_amsl_m,
            ),
        ]
    intervals = max(1, math.ceil(distance_m / spacing_m))
    samples = [
        _geodesic_sample(
            leg,
            fraction=index / intervals,
            start_lat=start_lat,
            start_lon=start_lon,
            track_deg=track_deg,
            distance_m=distance_m,
            geod=geod,
        )
        for index in range(intervals + 1)
    ]
    return _include_vertical_completion_sample(
        samples,
        leg=leg,
        end_lat=end_lat,
        end_lon=end_lon,
    )


def _geodesic_sample(
    leg: LegEstimate,
    *,
    fraction: float,
    start_lat: float,
    start_lon: float,
    track_deg: float,
    distance_m: float,
    geod: Geod,
) -> SpatialSample:
    lon, lat, _ = geod.fwd(
        start_lon,
        start_lat,
        track_deg,
        distance_m * fraction,
    )
    return SpatialSample(
        leg=leg,
        fraction=fraction,
        lat=lat,
        lon=lon,
        altitude_amsl_m=_interpolate_altitude(leg, fraction),
    )


def _sample_turn(
    turn: _TurnFootprint,
    *,
    geod: Geod,
    spacing_m: float,
) -> list[SpatialSample]:
    intervals = max(1, math.ceil(turn.leg.path_distance_m / spacing_m))
    samples: list[SpatialSample] = []
    for index in range(intervals + 1):
        fraction = index / intervals
        lat, lon = turn.point_at(fraction, geod)
        if index == 0:
            lat, lon = turn.entry_lat, turn.entry_lon
        elif index == intervals:
            lat, lon = turn.exit_lat, turn.exit_lon
        samples.append(
            SpatialSample(
                leg=turn.leg,
                fraction=fraction,
                lat=lat,
                lon=lon,
                altitude_amsl_m=_interpolate_altitude(turn.leg, fraction),
            )
        )
    return samples


def _reconstruct_turn(
    legs: Sequence[LegEstimate],
    *,
    index: int,
    geod: Geod,
) -> _TurnFootprint:
    leg = legs[index]
    if leg.path_distance_m <= 0.0:
        raise SpatialSamplingError(
            "turn-arc leg has no positive arc length",
            leg=leg,
        )
    previous = _adjacent_horizontal_leg(legs, index=index, step=-1, geod=geod)
    following = _adjacent_horizontal_leg(legs, index=index, step=1, geod=geod)
    if previous is None or following is None:
        raise SpatialSamplingError(
            "turn-arc footprint requires adjacent incoming and outgoing legs",
            leg=leg,
        )

    incoming_track, _, incoming_distance_m = geod.inv(
        previous.start_lon,
        previous.start_lat,
        leg.start_lon,
        leg.start_lat,
    )
    outgoing_track, _, outgoing_distance_m = geod.inv(
        leg.end_lon,
        leg.end_lat,
        following.end_lon,
        following.end_lat,
    )
    signed_turn_deg = normalize_signed(outgoing_track - incoming_track)
    if (
        abs(signed_turn_deg) <= _ANGLE_TOLERANCE_DEG
        or abs(signed_turn_deg) >= 180.0 - _ANGLE_TOLERANCE_DEG
    ):
        raise SpatialSamplingError(
            "turn-arc heading change must be strictly between 0 and 180 degrees",
            leg=leg,
        )
    signed_turn_rad = math.radians(signed_turn_deg)
    radius_m = leg.path_distance_m / abs(signed_turn_rad)
    if not math.isfinite(radius_m) or radius_m <= 0.0:
        raise SpatialSamplingError("turn-arc radius is invalid", leg=leg)
    _, _, explicit_chord_m = geod.inv(
        leg.start_lon,
        leg.start_lat,
        leg.end_lon,
        leg.end_lat,
    )
    if abs(explicit_chord_m) > _POSITION_TOLERANCE_M:
        incoming_rad = math.radians(incoming_track)
        turn_sign = 1.0 if signed_turn_rad > 0.0 else -1.0
        right_normal_east = math.cos(incoming_rad)
        right_normal_north = -math.sin(incoming_rad)
        exit_azimuth, _, exit_distance_m = geod.inv(
            leg.start_lon,
            leg.start_lat,
            leg.end_lon,
            leg.end_lat,
        )
        exit_azimuth_rad = math.radians(exit_azimuth)
        return _TurnFootprint(
            leg=leg,
            waypoint_lat=leg.start_lat,
            waypoint_lon=leg.start_lon,
            tangent_start_east_m=0.0,
            tangent_start_north_m=0.0,
            tangent_end_east_m=abs(exit_distance_m) * math.sin(exit_azimuth_rad),
            tangent_end_north_m=abs(exit_distance_m) * math.cos(exit_azimuth_rad),
            center_east_m=turn_sign * radius_m * right_normal_east,
            center_north_m=turn_sign * radius_m * right_normal_north,
            signed_turn_rad=signed_turn_rad,
            radius_m=radius_m,
            entry_lat=leg.start_lat,
            entry_lon=leg.start_lon,
            exit_lat=leg.end_lat,
            exit_lon=leg.end_lon,
            adjust_adjacent_straights=False,
        )

    tangent_offset_m = radius_m * math.tan(abs(signed_turn_rad) / 2.0)
    if (
        not math.isfinite(radius_m)
        or radius_m <= 0.0
        or tangent_offset_m > abs(incoming_distance_m) + _POSITION_TOLERANCE_M
        or tangent_offset_m > abs(outgoing_distance_m) + _POSITION_TOLERANCE_M
    ):
        raise SpatialSamplingError(
            "turn-arc tangent points exceed adjacent route-leg geometry",
            leg=leg,
        )

    incoming_rad = math.radians(incoming_track)
    outgoing_rad = math.radians(outgoing_track)
    incoming_east = math.sin(incoming_rad)
    incoming_north = math.cos(incoming_rad)
    outgoing_east = math.sin(outgoing_rad)
    outgoing_north = math.cos(outgoing_rad)
    tangent_start_east = -tangent_offset_m * incoming_east
    tangent_start_north = -tangent_offset_m * incoming_north
    tangent_end_east = tangent_offset_m * outgoing_east
    tangent_end_north = tangent_offset_m * outgoing_north

    turn_sign = 1.0 if signed_turn_rad > 0.0 else -1.0
    right_normal_east = incoming_north
    right_normal_north = -incoming_east
    center_east = tangent_start_east + turn_sign * radius_m * right_normal_east
    center_north = tangent_start_north + turn_sign * radius_m * right_normal_north
    turn_start_lat, turn_start_lon = _offset_point(
        leg.start_lat,
        leg.start_lon,
        east_m=tangent_start_east,
        north_m=tangent_start_north,
        geod=geod,
    )
    turn_end_lat, turn_end_lon = _offset_point(
        leg.start_lat,
        leg.start_lon,
        east_m=tangent_end_east,
        north_m=tangent_end_north,
        geod=geod,
    )
    return _TurnFootprint(
        leg=leg,
        waypoint_lat=leg.start_lat,
        waypoint_lon=leg.start_lon,
        tangent_start_east_m=tangent_start_east,
        tangent_start_north_m=tangent_start_north,
        tangent_end_east_m=tangent_end_east,
        tangent_end_north_m=tangent_end_north,
        center_east_m=center_east,
        center_north_m=center_north,
        signed_turn_rad=signed_turn_rad,
        radius_m=radius_m,
        entry_lat=turn_start_lat,
        entry_lon=turn_start_lon,
        exit_lat=turn_end_lat,
        exit_lon=turn_end_lon,
        adjust_adjacent_straights=True,
    )


def _adjacent_horizontal_leg(
    legs: Sequence[LegEstimate],
    *,
    index: int,
    step: int,
    geod: Geod,
) -> LegEstimate | None:
    candidate_index = index + step
    while 0 <= candidate_index < len(legs):
        candidate = legs[candidate_index]
        if candidate.phase == LegPhase.TURN_ARC:
            return None
        _, _, distance_m = geod.inv(
            candidate.start_lon,
            candidate.start_lat,
            candidate.end_lon,
            candidate.end_lat,
        )
        if abs(distance_m) > _POSITION_TOLERANCE_M:
            return candidate
        candidate_index += step
    return None


def _offset_point(
    origin_lat: float,
    origin_lon: float,
    *,
    east_m: float,
    north_m: float,
    geod: Geod,
) -> tuple[float, float]:
    distance_m = math.hypot(east_m, north_m)
    if distance_m <= _POSITION_TOLERANCE_M:
        return origin_lat, origin_lon
    azimuth_deg = math.degrees(math.atan2(east_m, north_m))
    lon, lat, _ = geod.fwd(origin_lon, origin_lat, azimuth_deg, distance_m)
    return lat, lon


def _interpolate_altitude(leg: LegEstimate, fraction: float) -> float:
    altitude_delta_m = leg.end_alt_amsl_m - leg.start_alt_amsl_m
    if math.isclose(altitude_delta_m, 0.0):
        return leg.start_alt_amsl_m

    profile = leg.timing_profile
    if profile is None:
        raise SpatialSamplingError(
            "altitude-changing leg has no transit timing profile",
            leg=leg,
        )
    if profile.vertical_time_s <= 0.0:
        raise SpatialSamplingError(
            "altitude-changing leg has an invalid vertical timing profile",
            leg=leg,
        )

    points = profile.distance_time_points
    fractions = tuple(point[0] for point in points)
    upper_index = bisect.bisect_right(fractions, fraction)
    if upper_index <= 0:
        elapsed_time_s = points[0][1]
    elif upper_index >= len(points):
        elapsed_time_s = points[-1][1]
    else:
        lower_fraction, lower_time_s = points[upper_index - 1]
        upper_fraction, upper_time_s = points[upper_index]
        if math.isclose(lower_fraction, upper_fraction):
            elapsed_time_s = min(lower_time_s, upper_time_s)
        else:
            local_fraction = (fraction - lower_fraction) / (
                upper_fraction - lower_fraction
            )
            elapsed_time_s = lower_time_s + local_fraction * (
                upper_time_s - lower_time_s
            )
    altitude_fraction = min(1.0, elapsed_time_s / profile.vertical_time_s)
    return leg.start_alt_amsl_m + altitude_delta_m * altitude_fraction


def _include_vertical_completion_sample(
    samples: list[SpatialSample],
    *,
    leg: LegEstimate,
    end_lat: float,
    end_lon: float,
) -> list[SpatialSample]:
    """Append the endpoint of a climb/descent that outlasts horizontal travel."""

    if not samples or math.isclose(
        samples[-1].altitude_amsl_m,
        leg.end_alt_amsl_m,
    ):
        return samples
    samples.append(
        SpatialSample(
            leg=leg,
            fraction=1.0,
            lat=end_lat,
            lon=end_lon,
            altitude_amsl_m=leg.end_alt_amsl_m,
        )
    )
    return samples


__all__ = [
    "SpatialSample",
    "SpatialSamplingError",
    "route_leg_samples",
]
