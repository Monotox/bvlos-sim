"""Position proximity comparison for SITL telemetry."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from pyproj import Geod

from bvlos_sim.adapters.sitl.comparison_artifacts import (
    _ArtifactRecord,
    _ArtifactRecords,
    _list_of_mappings,
)
from bvlos_sim.adapters.sitl.comparison_values import _SitlComparisonValueCoercer
from bvlos_sim.schemas.sitl_comparison import SitlComparisonItem, SitlComparisonOutcome


@dataclass(frozen=True)
class _TimelineTarget:
    index: int
    lat: float
    lon: float


@dataclass(frozen=True)
class _PositionObservation:
    lat: float
    lon: float


@dataclass(frozen=True)
class _PositionMatch:
    lat: float
    lon: float
    distance_m: float


@dataclass(frozen=True)
class _SitlPositionProximityComparator:
    """Compare expected timeline points with observed position telemetry."""

    values: _SitlComparisonValueCoercer = field(
        default_factory=_SitlComparisonValueCoercer,
    )
    geod: Geod = field(default_factory=lambda: Geod(ellps="WGS84"))

    def items(
        self,
        scenario_report: Mapping[str, object],
        telemetry: _ArtifactRecords,
        tolerance_m: float,
    ) -> list[SitlComparisonItem]:
        positions = self._global_position_records(telemetry.records)
        if not positions:
            return [self._unsupported_item(tolerance_m, telemetry.note)]

        return [
            self._item(target, positions, tolerance_m)
            for target in self._timeline_targets(scenario_report)
        ]

    def _unsupported_item(
        self,
        tolerance_m: float,
        telemetry_note: str | None,
    ) -> SitlComparisonItem:
        return SitlComparisonItem(
            dimension="position_proximity",
            outcome=SitlComparisonOutcome.UNSUPPORTED,
            tolerance=tolerance_m,
            notes=telemetry_note
            or "No GLOBAL_POSITION_INT telemetry records were observed.",
        )

    def _item(
        self,
        target: _TimelineTarget,
        positions: Sequence[_PositionObservation],
        tolerance_m: float,
    ) -> SitlComparisonItem:
        closest = self._closest_position(target, positions)
        return SitlComparisonItem(
            dimension=f"position:timeline_index_{target.index}",
            outcome=self._outcome(closest.distance_m, tolerance_m),
            expected={"lat": target.lat, "lon": target.lon},
            observed={
                "lat": closest.lat,
                "lon": closest.lon,
                "distance_m": closest.distance_m,
            },
            tolerance=tolerance_m,
        )

    def _timeline_targets(
        self,
        scenario_report: Mapping[str, object],
    ) -> list[_TimelineTarget]:
        return [
            target
            for point in _list_of_mappings(scenario_report.get("timeline"))
            for target in (self._timeline_target(point),)
            if target is not None
        ]

    def _timeline_target(self, point: _ArtifactRecord) -> _TimelineTarget | None:
        index = self.values.integer_value(point.get("index"))
        lat = self.values.float_value(point.get("lat"))
        lon = self.values.float_value(point.get("lon"))
        return (
            None
            if index is None or index == 0 or lat is None or lon is None
            else _TimelineTarget(index=index, lat=lat, lon=lon)
        )

    def _global_position_records(
        self,
        telemetry_records: Sequence[_ArtifactRecord],
    ) -> list[_PositionObservation]:
        return [
            position
            for record in telemetry_records
            for position in (self._global_position_record(record),)
            if position is not None
        ]

    def _global_position_record(
        self,
        record: _ArtifactRecord,
    ) -> _PositionObservation | None:
        if record.get("message_type") != "GLOBAL_POSITION_INT":
            return None
        fields = record.get("fields")
        if not isinstance(fields, Mapping):
            return None

        lat = self._mavlink_coordinate(fields.get("lat"))
        lon = self._mavlink_coordinate(fields.get("lon"))
        return (
            None
            if lat is None or lon is None
            else _PositionObservation(lat=lat, lon=lon)
        )

    def _mavlink_coordinate(self, value: object) -> float | None:
        coordinate = self.values.float_value(value)
        return None if coordinate is None else self._coordinate_degrees(coordinate)

    def _coordinate_degrees(self, coordinate: float) -> float:
        # MAVLink GLOBAL_POSITION_INT encodes lat/lon as int32 in 1e-7 degree
        # units. Valid decimal degrees never exceed ±180 for lon or ±90 for lat,
        # so any value with |x| > 180 must be a MAVLink integer.
        return coordinate / 10_000_000.0 if abs(coordinate) > 180.0 else coordinate

    def _closest_position(
        self,
        target: _TimelineTarget,
        positions: Sequence[_PositionObservation],
    ) -> _PositionMatch:
        return min(
            (self._position_match(target, position) for position in positions),
            key=lambda match: match.distance_m,
        )

    def _position_match(
        self,
        target: _TimelineTarget,
        position: _PositionObservation,
    ) -> _PositionMatch:
        _azimuth, _back_azimuth, distance_m = self.geod.inv(
            target.lon,
            target.lat,
            position.lon,
            position.lat,
        )
        return _PositionMatch(
            lat=position.lat,
            lon=position.lon,
            distance_m=distance_m,
        )

    def _outcome(
        self,
        distance_m: float,
        tolerance_m: float,
    ) -> SitlComparisonOutcome:
        rules = (
            (distance_m <= tolerance_m, SitlComparisonOutcome.MATCHED),
            (distance_m <= tolerance_m * 2, SitlComparisonOutcome.DRIFTED),
        )
        return next(
            (outcome for applies, outcome in rules if applies),
            SitlComparisonOutcome.MISSING,
        )


__all__: list[str] = []
