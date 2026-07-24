import json

from bvlos_sim.adapters.geojson_export import build_geojson_export
from bvlos_sim.adapters.kml_export import _route_style_id, build_kml_export
from bvlos_sim.adapters.route_export_support import energy_margin_pct, landing_zone_point
from bvlos_sim.estimator.core.enums import (
    EnergyPowerSource,
    EstimateStatus,
    FailureCode,
    GeofenceKind,
    LegPhase,
)
from bvlos_sim.estimator.core.geofence import (
    GeofenceCoordinate,
    GeofenceGeometry,
    GeofencePolygon,
    GeofenceZone,
)
from bvlos_sim.estimator.core.landing_zone import (
    LandingZone,
    LandingZoneCoordinate,
    LandingZoneGeometry,
)
from bvlos_sim.estimator.core.results import (
    EnergyEstimate,
    EnergyLegEstimate,
    GeofenceConflict,
    GeofenceEstimate,
    LandingZoneEstimate,
    LandingZoneStateReachability,
    LegEstimate,
    MissionEstimate,
    RthReserveTimelinePoint,
)


def _leg(leg_index: int, *, start_lon: float, end_lon: float) -> LegEstimate:
    return LegEstimate(
        leg_index=leg_index,
        route_item_index=leg_index,
        route_item_id=f"wp-{leg_index}",
        action="waypoint",
        phase=LegPhase.TRANSIT,
        start_lat=52.0,
        start_lon=start_lon,
        start_alt_amsl_m=100.0,
        end_lat=52.001,
        end_lon=end_lon,
        end_alt_amsl_m=110.0,
        horizontal_distance_m=100.0,
        vertical_delta_m=10.0,
        vertical_distance_m=10.0,
        path_distance_m=100.5,
        time_s=10.0,
    )


def _energy() -> EnergyEstimate:
    return EnergyEstimate(
        is_feasible=True,
        total_energy_wh=42.0,
        battery_capacity_wh=900.0,
        usable_energy_wh=675.0,
        reserve_threshold_percent=25.0,
        reserve_threshold_wh=225.0,
        reserve_at_landing_wh=585.0,
        reserve_at_landing_percent=65.0,
        legs=[
            _energy_leg(0, energy_wh=21.0),
            _energy_leg(1, energy_wh=21.0),
        ],
    )


def _energy_with_rth_margin(*, margin_wh: float = 180.0) -> EnergyEstimate:
    energy = _energy()
    return energy.model_copy(
        update={
            "rth_reserve_timeline": [
                RthReserveTimelinePoint(
                    leg_index=0,
                    route_item_index=0,
                    route_item_id="wp-0",
                    rth_distance_m=100.0,
                    rth_energy_wh=10.0,
                    energy_remaining_before_rth_wh=800.0,
                    reserve_after_rth_wh=energy.reserve_threshold_wh + margin_wh,
                    reserve_margin_wh=margin_wh,
                    is_feasible=margin_wh >= 0.0,
                )
            ]
        }
    )


def _energy_leg(leg_index: int, *, energy_wh: float) -> EnergyLegEstimate:
    return EnergyLegEstimate(
        leg_index=leg_index,
        route_item_index=leg_index,
        route_item_id=f"wp-{leg_index}",
        phase=LegPhase.TRANSIT,
        time_s=10.0,
        power_w=450.0,
        power_source=EnergyPowerSource.CRUISE_POWER,
        energy_wh=energy_wh,
    )


def _estimate(
    *,
    energy: EnergyEstimate | None = None,
    geofence: GeofenceEstimate | None = None,
    landing_zone: LandingZoneEstimate | None = None,
) -> MissionEstimate:
    return MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=200.0,
        total_vertical_distance_m=20.0,
        total_path_distance_m=201.0,
        total_time_s=20.0,
        totals_are_partial=False,
        legs=[
            _leg(0, start_lon=4.0, end_lon=4.001),
            _leg(1, start_lon=4.001, end_lon=4.002),
        ],
        energy=energy,
        geofence=geofence,
        landing_zone=landing_zone,
    )


def _geofence_zone() -> GeofenceZone:
    return GeofenceZone(
        id="EHR06A",
        kind=GeofenceKind.FORBIDDEN,
        geometry=GeofenceGeometry(
            polygons=[
                GeofencePolygon(
                    exterior=[
                        GeofenceCoordinate(lat=51.999, lon=4.001),
                        GeofenceCoordinate(lat=51.999, lon=4.003),
                        GeofenceCoordinate(lat=52.003, lon=4.003),
                        GeofenceCoordinate(lat=52.003, lon=4.001),
                        GeofenceCoordinate(lat=51.999, lon=4.001),
                    ]
                )
            ]
        ),
    )


def _geofence_estimate() -> GeofenceEstimate:
    return GeofenceEstimate(
        is_feasible=False,
        checked_zone_count=1,
        checked_leg_count=2,
        conflicts=[
            GeofenceConflict(
                code=FailureCode.ROUTE_ENTERS_FORBIDDEN_ZONE,
                message="route enters forbidden zone",
                zone_id="EHR06A",
                zone_kind=GeofenceKind.FORBIDDEN,
                leg_index=0,
                route_item_index=0,
                route_item_id="wp-0",
            )
        ],
    )


def _landing_zone() -> LandingZone:
    return LandingZone(
        id="EHRD",
        geometry=LandingZoneGeometry(
            points=[LandingZoneCoordinate(lat=52.002, lon=4.004)]
        ),
    )


def _landing_zone_estimate() -> LandingZoneEstimate:
    return LandingZoneEstimate(
        is_feasible=True,
        checked_zone_count=1,
        checked_state_count=1,
        reserve_threshold_percent=25.0,
        reserve_threshold_wh=225.0,
        states=[
            LandingZoneStateReachability(
                state_index=0,
                leg_index=0,
                route_item_index=0,
                route_item_id="wp-0",
                lat=52.0,
                lon=4.0,
                altitude_amsl_m=100.0,
                reachable_zone_id="EHRD",
                reachable_zone_distance_m=100.0,
                energy_remaining_before_divert_wh=585.0,
                reserve_ok=True,
                is_reachable=True,
            )
        ],
    )


def _features_by_layer(payload: dict, layer: str) -> list[dict]:
    return [
        feature
        for feature in payload["features"]
        if feature["properties"]["layer"] == layer
    ]


def test_geojson_export_minimal_estimate_has_route_features() -> None:
    payload = json.loads(build_geojson_export(_estimate(energy=_energy())))

    route_features = _features_by_layer(payload, "route")

    assert payload["type"] == "FeatureCollection"
    assert len(route_features) == 2
    assert route_features[0]["geometry"]["type"] == "LineString"
    assert isinstance(route_features[0]["properties"]["energy_margin_pct"], float)


def test_geojson_export_includes_geofence_layer() -> None:
    payload = json.loads(
        build_geojson_export(
            _estimate(energy=_energy(), geofence=_geofence_estimate()),
            geofence_zones=[_geofence_zone()],
        )
    )

    geofence_features = _features_by_layer(payload, "geofences")

    assert geofence_features
    assert isinstance(geofence_features[0]["properties"]["conflict"], bool)


def test_geojson_export_includes_landing_zone_layer() -> None:
    payload = json.loads(
        build_geojson_export(
            _estimate(energy=_energy(), landing_zone=_landing_zone_estimate()),
            landing_zones=[_landing_zone()],
        )
    )

    landing_zone_features = _features_by_layer(payload, "landing_zones")

    assert landing_zone_features
    assert isinstance(landing_zone_features[0]["properties"]["reachable"], bool)


def test_geojson_export_without_energy_uses_null_energy_margin() -> None:
    payload = json.loads(build_geojson_export(_estimate(energy=None)))

    route_features = _features_by_layer(payload, "route")

    assert route_features
    assert all(
        feature["properties"]["energy_margin_pct"] is None for feature in route_features
    )


def test_geojson_export_route_features_include_route_item_id() -> None:
    payload = json.loads(build_geojson_export(_estimate(energy=_energy())))

    route_features = _features_by_layer(payload, "route")

    assert all("route_item_id" in f["properties"] for f in route_features)
    assert route_features[0]["properties"]["route_item_id"] == "wp-0"
    assert route_features[1]["properties"]["route_item_id"] == "wp-1"


def test_geojson_export_colours_route_by_rth_margin() -> None:
    payload = json.loads(build_geojson_export(_estimate(energy=_energy_with_rth_margin())))

    route_features = _features_by_layer(payload, "route")

    properties = route_features[0]["properties"]
    assert properties["rth_reserve_margin_wh"] == 180.0
    assert properties["rth_reserve_margin_pct"] == 20.0
    assert properties["rth_reserve_color"] == "yellow"


def test_kml_export_renders_document_with_placemarks() -> None:
    output = build_kml_export(_estimate(energy=_energy()))

    assert output.startswith("<?xml")
    assert "<kml" in output
    assert "<Placemark" in output


def test_kml_export_placemark_name_includes_route_item_id() -> None:
    output = build_kml_export(_estimate(energy=_energy()))

    assert "wp-0" in output
    assert "wp-1" in output


# ---------------------------------------------------------------------------
# KML route style selection
# ---------------------------------------------------------------------------


def test_route_style_id_green_when_margin_above_30() -> None:
    assert _route_style_id(31.0) == "route-green"


def test_route_style_id_green_at_boundary_31() -> None:
    assert _route_style_id(30.1) == "route-green"


def test_route_style_id_amber_at_30_percent() -> None:
    assert _route_style_id(30.0) == "route-amber"


def test_route_style_id_amber_at_10_percent() -> None:
    assert _route_style_id(10.0) == "route-amber"


def test_route_style_id_red_when_margin_below_10() -> None:
    assert _route_style_id(9.9) == "route-red"


def test_route_style_id_red_when_margin_negative() -> None:
    assert _route_style_id(-5.0) == "route-red"


def test_route_style_id_red_when_margin_none() -> None:
    assert _route_style_id(None) == "route-red"


# ---------------------------------------------------------------------------
# KML landing-zone and geofence layers
# ---------------------------------------------------------------------------


def test_kml_export_includes_landing_zone_placemark() -> None:
    lz = _landing_zone()
    output = build_kml_export(
        _estimate(landing_zone=_landing_zone_estimate()),
        landing_zones=[lz],
    )
    assert lz.id in output
    assert "landing_zones" in output


def test_kml_export_includes_geofence_placemark() -> None:
    zone = _geofence_zone()
    output = build_kml_export(
        _estimate(geofence=_geofence_estimate()),
        geofence_zones=[zone],
    )
    assert "geofences" in output
    assert zone.kind.value in output


# ---------------------------------------------------------------------------
# route_export_support unit tests
# ---------------------------------------------------------------------------


def test_energy_margin_pct_returns_none_for_zero_battery_capacity() -> None:
    energy = _energy()
    energy = energy.model_copy(update={"battery_capacity_wh": 0.0})
    assert energy_margin_pct(energy) is None


def test_energy_margin_pct_returns_none_when_energy_is_none() -> None:
    assert energy_margin_pct(None) is None


def test_energy_margin_pct_computes_correct_value() -> None:
    energy = _energy()
    result = energy_margin_pct(energy)
    assert result is not None
    expected = (energy.reserve_at_landing_wh - energy.reserve_threshold_wh) / energy.battery_capacity_wh * 100.0
    assert abs(result - expected) < 1e-9


def test_landing_zone_point_returns_lon_lat_for_point_geometry() -> None:
    lz = _landing_zone()
    point = landing_zone_point(lz)
    assert point is not None
    lon, lat = point
    assert lon == lz.geometry.points[0].lon
    assert lat == lz.geometry.points[0].lat


def test_landing_zone_point_falls_back_to_polygon_centroid() -> None:
    from bvlos_sim.estimator.core.landing_zone import LandingZonePolygon
    polygon = LandingZonePolygon(
        exterior=[
            LandingZoneCoordinate(lat=52.0, lon=4.0),
            LandingZoneCoordinate(lat=52.0, lon=4.001),
            LandingZoneCoordinate(lat=52.001, lon=4.001),
            LandingZoneCoordinate(lat=52.001, lon=4.0),
            LandingZoneCoordinate(lat=52.0, lon=4.0),
        ]
    )
    lz = LandingZone(
        id="poly-lz",
        geometry=LandingZoneGeometry(polygons=[polygon]),
    )
    point = landing_zone_point(lz)
    assert point is not None
    lon, lat = point
    assert 4.0 < lon < 4.001
    assert 52.0 < lat < 52.001
