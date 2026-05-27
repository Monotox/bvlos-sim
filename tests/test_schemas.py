from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from schemas import MissionPlan, RouteItem, ScenarioPlan, VehicleProfile
from schemas.vehicle_energy import EnergyModel, FailsafeProfile
from schemas.vehicle_sensors import AirspeedModel, BatteryMeterModel, GpsModel, SensorProfile

ROOT = Path(__file__).resolve().parents[1]


def valid_vehicle_payload() -> dict:
    return {
        "vehicle_id": "quadplane_v1",
        "display_name": "QuadPlane v1",
        "vehicle_class": "vtol",
        "mav_type": "MAV_TYPE_VTOL_QUADROTOR",
        "autopilot": "ardupilot",
        "mass": {
            "empty_kg": 8.0,
            "max_payload_kg": 2.0,
            "max_takeoff_kg": 12.0,
        },
        "performance": {
            "cruise_speed_mps": 18.0,
            "hover_speed_mps": 5.0,
            "max_speed_mps": 25.0,
            "climb_rate_mps": 3.0,
            "descent_rate_mps": 2.0,
            "turn_radius_m": 80.0,
            "max_wind_mps": 10.0,
        },
        "energy": {
            "battery_capacity_wh": 900.0,
            "reserve_percent_default": 25.0,
            "cruise_power_w": 450.0,
            "hover_power_w": 1200.0,
            "climb_power_w": 1500.0,
        },
        "failsafe": {
            "low_battery_warn_percent": 30,
            "low_battery_abort_percent": 25,
            "emergency_land_percent": 10,
        },
        "sitl": {
            "backend": "ardupilot",
            "frame": "quadplane",
        },
    }


def valid_mission_payload() -> dict:
    return {
        "mission_id": "pipeline_demo_001",
        "vehicle_profile": "quadplane_v1",
        "planned_home": {
            "lat": 52.0,
            "lon": 4.0,
            "altitude_amsl_m": 12.0,
        },
        "defaults": {
            "cruise_speed_mps": 18.0,
            "hover_speed_mps": 5.0,
            "altitude_reference": "relative_home",
        },
        "route": [
            {
                "id": "takeoff",
                "action": "vtol_takeoff",
                "altitude_m": 80.0,
            },
            {
                "id": "wp1",
                "action": "waypoint",
                "lat": 52.001,
                "lon": 4.002,
                "altitude_m": 120.0,
                "acceptance_radius_m": 20.0,
            },
            {
                "id": "loiter",
                "action": "loiter_time",
                "lat": 52.002,
                "lon": 4.004,
                "altitude_m": 120.0,
                "loiter_time_s": 60.0,
                "loiter_radius_m": 80.0,
            },
            {
                "id": "rtl",
                "action": "rtl",
            },
        ],
        "constraints": {
            "min_landing_reserve_percent": 25.0,
            "max_wind_mps": 10.0,
            "min_distance_to_landing_zone_m": 2500.0,
        },
        "assets": {
            "geofences_file": "data/geofences/demo.geojson",
            "landing_zones_file": "data/landing_zones/demo.geojson",
            "comms_coverage_file": "data/comms/demo.geojson",
        },
        "policy": {
            "lost_link_policy": "standard_lost_link_v1",
        },
    }


def test_vehicle_profile_accepts_valid_vtol_profile() -> None:
    profile = VehicleProfile.model_validate(valid_vehicle_payload())

    assert profile.vehicle_id == "quadplane_v1"
    assert profile.performance.turn_radius_m == 80.0
    assert profile.energy.hover_power_w == 1200.0


def test_vehicle_profile_accepts_resource_systems() -> None:
    payload = valid_vehicle_payload()
    payload["resource_systems"] = [
        {
            "resource_id": "fiber-power",
            "kind": "external_power",
            "delivery": "optical_fiber",
            "continuous_power_w": 2000.0,
            "max_tether_length_m": 2500.0,
        }
    ]

    profile = VehicleProfile.model_validate(payload)

    assert profile.resource_systems[0].resource_id == "fiber-power"


def test_resource_system_rejects_unknown_keys() -> None:
    payload = valid_vehicle_payload()
    payload["resource_systems"] = [
        {
            "resource_id": "fiber-power",
            "kind": "external_power",
            "continuous_power_w": 2000.0,
            "unexpected": True,
        }
    ]

    with pytest.raises(ValidationError):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_rejects_inconsistent_mass_limits() -> None:
    payload = valid_vehicle_payload()
    payload["mass"]["max_takeoff_kg"] = 9.0

    with pytest.raises(ValidationError, match="empty_kg \\+ max_payload_kg"):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_requires_hover_model_for_vtol() -> None:
    payload = valid_vehicle_payload()
    payload["performance"]["hover_speed_mps"] = None

    with pytest.raises(ValidationError, match="hover_speed_mps is required"):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_requires_hover_power_for_vtol() -> None:
    payload = valid_vehicle_payload()
    payload["energy"]["hover_power_w"] = None

    with pytest.raises(ValidationError, match="hover_power_w is required"):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_rejects_hover_speed_above_max_speed() -> None:
    payload = valid_vehicle_payload()
    payload["performance"]["hover_speed_mps"] = 30.0

    with pytest.raises(
        ValidationError,
        match="max_speed_mps must be greater than or equal to hover_speed_mps",
    ):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_rejects_non_positive_max_crab_angle() -> None:
    payload = valid_vehicle_payload()
    payload["performance"]["max_crab_angle_deg"] = 0.0

    with pytest.raises(ValidationError, match="greater than 0"):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_rejects_negative_station_keep_wind_limit() -> None:
    payload = valid_vehicle_payload()
    payload["performance"]["max_station_keep_wind_mps"] = -1.0

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_rejects_cruise_speed_above_max_speed() -> None:
    payload = valid_vehicle_payload()
    payload["performance"]["cruise_speed_mps"] = 30.0  # max_speed_mps is 25.0

    with pytest.raises(
        ValidationError,
        match="max_speed_mps must be greater than or equal to cruise_speed_mps",
    ):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_rejects_max_crab_angle_at_90_degrees() -> None:
    payload = valid_vehicle_payload()
    payload["performance"]["max_crab_angle_deg"] = 90.0

    with pytest.raises(ValidationError, match="less than 90"):
        VehicleProfile.model_validate(payload)


def test_vehicle_profile_requires_turn_radius_for_fixed_wing() -> None:
    payload = valid_vehicle_payload()
    payload["vehicle_class"] = "fixed_wing"
    payload["performance"]["hover_speed_mps"] = None
    payload["performance"]["turn_radius_m"] = None
    payload["energy"]["hover_power_w"] = None

    with pytest.raises(ValidationError, match="turn_radius_m is required"):
        VehicleProfile.model_validate(payload)


def test_mission_plan_accepts_valid_route() -> None:
    mission = MissionPlan.model_validate(valid_mission_payload())

    assert mission.mission_id == "pipeline_demo_001"
    assert len(mission.route) == 4
    assert mission.route[1].acceptance_radius_m == 20.0


def test_mission_plan_accepts_link_systems() -> None:
    payload = valid_mission_payload()
    payload["link_systems"] = [
        {
            "link_id": "satcom",
            "kind": "starlink",
            "max_range_m": 100000.0,
        }
    ]

    mission = MissionPlan.model_validate(payload)

    assert mission.link_systems[0].link_id == "satcom"


def test_link_system_rejects_unknown_keys() -> None:
    payload = valid_mission_payload()
    payload["link_systems"] = [
        {
            "link_id": "satcom",
            "kind": "starlink",
            "unexpected": True,
        }
    ]

    with pytest.raises(ValidationError):
        MissionPlan.model_validate(payload)


def test_mission_plan_allows_vehicle_default_reserve_threshold() -> None:
    payload = valid_mission_payload()
    payload["constraints"].pop("min_landing_reserve_percent")

    mission = MissionPlan.model_validate(payload)

    assert mission.constraints.min_landing_reserve_percent is None


def test_mission_plan_rejects_waypoint_without_coordinates() -> None:
    payload = valid_mission_payload()
    payload["route"][1].pop("lat")

    with pytest.raises(ValidationError, match="waypoint requires lat and lon"):
        MissionPlan.model_validate(payload)


def test_mission_plan_rejects_partial_coordinate_pair() -> None:
    payload = valid_mission_payload()
    payload["route"][0]["lat"] = 52.0

    with pytest.raises(
        ValidationError,
        match="lat and lon must either both be provided or both be omitted",
    ):
        MissionPlan.model_validate(payload)


def test_mission_plan_rejects_altitude_reference_without_altitude() -> None:
    payload = valid_mission_payload()
    payload["route"][0]["action"] = "land"
    payload["route"][0]["lat"] = 52.0
    payload["route"][0]["lon"] = 4.0
    payload["route"][0].pop("altitude_m")
    payload["route"][0]["altitude_reference"] = "amsl"

    with pytest.raises(ValidationError, match="altitude_reference requires altitude_m"):
        MissionPlan.model_validate(payload)


def test_mission_plan_rejects_duplicate_route_ids() -> None:
    payload = valid_mission_payload()
    payload["route"][1]["id"] = "takeoff"

    with pytest.raises(ValidationError, match="route item ids must be unique"):
        MissionPlan.model_validate(payload)


def test_mission_plan_rejects_rtl_with_target_fields() -> None:
    payload = valid_mission_payload()
    payload["route"][3]["altitude_reference"] = "amsl"

    with pytest.raises(
        ValidationError,
        match="rtl should not define target coordinates or loiter fields",
    ):
        MissionPlan.model_validate(payload)


def test_example_vehicle_yaml_matches_schema() -> None:
    payload = yaml.safe_load((ROOT / "examples/vehicles/quadplane_v1.yaml").read_text())

    profile = VehicleProfile.model_validate(payload)

    assert profile.vehicle_id == "quadplane_v1"


def test_example_mission_yaml_matches_schema() -> None:
    payload = yaml.safe_load(
        (ROOT / "examples/missions/pipeline_demo_001.yaml").read_text()
    )

    mission = MissionPlan.model_validate(payload)

    assert mission.vehicle_profile == "quadplane_v1"


def test_free_form_metadata_fields_accept_arbitrary_keys() -> None:
    mission_payload = valid_mission_payload()
    mission_payload["metadata"] = {"source": "test", "nested": {"ok": True}}
    mission_payload["route"][1]["metadata"] = {"reviewed": True, "tags": ["demo"]}
    vehicle_payload = valid_vehicle_payload()
    vehicle_payload["metadata"] = {"calibration": {"status": "placeholder"}}
    scenario_payload = {
        "schema_version": "scenario.v1",
        "scenario_id": "metadata-test",
        "mission_file": "mission.yaml",
        "vehicle_file": "vehicle.yaml",
        "metadata": {"owner": "tests", "nested": {"ok": True}},
    }

    mission = MissionPlan.model_validate(mission_payload)
    vehicle = VehicleProfile.model_validate(vehicle_payload)
    scenario = ScenarioPlan.model_validate(scenario_payload)

    assert mission.metadata["nested"]["ok"] is True
    assert mission.route[1].metadata["tags"] == ["demo"]
    assert vehicle.metadata["calibration"]["status"] == "placeholder"
    assert scenario.metadata["nested"]["ok"] is True


# ---------------------------------------------------------------------------
# RouteItem: loiter_time_s and loiter_radius_m validation
# ---------------------------------------------------------------------------


def _loiter_item(**overrides) -> dict:
    base: dict = {
        "id": "loiter",
        "action": "loiter_time",
        "lat": 52.002,
        "lon": 4.004,
        "altitude_m": 120.0,
        "loiter_time_s": 60.0,
    }
    base.update(overrides)
    return base


def test_loiter_time_s_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteItem.model_validate(_loiter_item(loiter_time_s=0.0))


def test_loiter_time_s_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteItem.model_validate(_loiter_item(loiter_time_s=-1.0))


def test_loiter_time_action_without_loiter_time_s_rejected() -> None:
    payload = _loiter_item()
    del payload["loiter_time_s"]
    with pytest.raises(ValidationError, match="loiter_time requires loiter_time_s"):
        RouteItem.model_validate(payload)


def test_loiter_radius_m_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteItem.model_validate(_loiter_item(loiter_radius_m=0.0))


def test_loiter_radius_m_positive_accepted() -> None:
    item = RouteItem.model_validate(_loiter_item(loiter_radius_m=50.0))
    assert item.loiter_radius_m == 50.0


def test_route_item_acceptance_radius_zero_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteItem.model_validate(
            {"id": "wp1", "action": "waypoint", "lat": 52.0, "lon": 4.0, "altitude_m": 100.0, "acceptance_radius_m": 0.0}
        )


def test_route_item_negative_altitude_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteItem.model_validate(
            {"id": "wp1", "action": "waypoint", "lat": 52.0, "lon": 4.0, "altitude_m": -1.0}
        )


def test_route_item_id_starting_with_dash_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteItem.model_validate({"id": "-bad", "action": "rtl"})


def test_mission_estimation_zero_segment_length_rejected() -> None:
    payload = valid_mission_payload()
    payload["estimation"] = {"max_segment_length_m": 0.0}
    with pytest.raises(ValidationError):
        MissionPlan.model_validate(payload)


# ---------------------------------------------------------------------------
# SensorProfile, GpsModel, BatteryMeterModel, AirspeedModel validation
# ---------------------------------------------------------------------------


def test_gps_model_rejects_zero_horizontal_accuracy() -> None:
    with pytest.raises(ValidationError):
        GpsModel(horizontal_accuracy_m=0.0)


def test_gps_model_rejects_availability_above_one() -> None:
    with pytest.raises(ValidationError):
        GpsModel(availability=1.1)


def test_gps_model_rejects_negative_availability() -> None:
    with pytest.raises(ValidationError):
        GpsModel(availability=-0.1)


def test_gps_model_accepts_valid_defaults() -> None:
    gps = GpsModel()
    assert gps.horizontal_accuracy_m == 2.5
    assert gps.availability == 1.0


def test_battery_meter_model_rejects_zero_update_rate() -> None:
    with pytest.raises(ValidationError):
        BatteryMeterModel(update_rate_hz=0.0)


def test_battery_meter_model_accepts_valid_noise() -> None:
    meter = BatteryMeterModel(current_sensor_noise_pct=0.5)
    assert meter.current_sensor_noise_pct == 0.5


def test_airspeed_model_rejects_zero_update_rate() -> None:
    with pytest.raises(ValidationError):
        AirspeedModel(update_rate_hz=0.0)


def test_airspeed_model_rejects_negative_noise_std() -> None:
    with pytest.raises(ValidationError):
        AirspeedModel(noise_std_mps=-0.1)


def test_sensor_profile_accepts_partial_sensors() -> None:
    profile = SensorProfile(gps=GpsModel(horizontal_accuracy_m=1.0))
    assert profile.gps is not None
    assert profile.battery_meter is None
    assert profile.airspeed is None


def test_sensor_profile_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        SensorProfile.model_validate({"gps": None, "lidar": {"range_m": 100.0}})


# ---------------------------------------------------------------------------
# FailsafeProfile threshold ordering validation
# ---------------------------------------------------------------------------


def test_failsafe_profile_accepts_valid_ordering() -> None:
    profile = FailsafeProfile(
        low_battery_warn_percent=30,
        low_battery_abort_percent=25,
        emergency_land_percent=10,
    )
    assert profile.low_battery_warn_percent == 30


def test_failsafe_profile_rejects_abort_above_warn() -> None:
    with pytest.raises(ValidationError, match="warn >= abort >= emergency land"):
        FailsafeProfile(
            low_battery_warn_percent=20,
            low_battery_abort_percent=25,
            emergency_land_percent=10,
        )


def test_failsafe_profile_rejects_emergency_above_abort() -> None:
    with pytest.raises(ValidationError, match="warn >= abort >= emergency land"):
        FailsafeProfile(
            low_battery_warn_percent=30,
            low_battery_abort_percent=15,
            emergency_land_percent=20,
        )


def test_failsafe_profile_accepts_equal_thresholds() -> None:
    profile = FailsafeProfile(
        low_battery_warn_percent=25,
        low_battery_abort_percent=25,
        emergency_land_percent=25,
    )
    assert profile.emergency_land_percent == 25


# ---------------------------------------------------------------------------
# EnergyModel boundary validation
# ---------------------------------------------------------------------------


def test_energy_model_rejects_zero_battery_capacity() -> None:
    with pytest.raises(ValidationError):
        EnergyModel(battery_capacity_wh=0.0, reserve_percent_default=25.0, cruise_power_w=450.0)


def test_energy_model_rejects_zero_cruise_power() -> None:
    with pytest.raises(ValidationError):
        EnergyModel(battery_capacity_wh=900.0, reserve_percent_default=25.0, cruise_power_w=0.0)


def test_energy_model_rejects_reserve_above_100() -> None:
    with pytest.raises(ValidationError):
        EnergyModel(battery_capacity_wh=900.0, reserve_percent_default=101.0, cruise_power_w=450.0)


def test_energy_model_accepts_valid_values() -> None:
    model = EnergyModel(
        battery_capacity_wh=900.0,
        reserve_percent_default=25.0,
        cruise_power_w=450.0,
    )
    assert model.battery_capacity_wh == 900.0
