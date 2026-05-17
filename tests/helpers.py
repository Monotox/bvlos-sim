from schemas import MissionPlan, VehicleClass, VehicleProfile


def make_vehicle_payload() -> dict:
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
            "max_crab_angle_deg": 35.0,
            "max_station_keep_wind_mps": 8.0,
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
        "capabilities": {
            "hover": True,
            "forward_flight": True,
        },
    }


def make_mission_payload() -> dict:
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
        "assets": {},
        "policy": {},
    }


def make_vehicle() -> VehicleProfile:
    return VehicleProfile.model_validate(make_vehicle_payload())


def make_fw_vehicle() -> VehicleProfile:
    v = make_vehicle()
    v.vehicle_class = VehicleClass.FIXED_WING
    v.capabilities.hover = False
    v.capabilities.forward_flight = True
    return v


def make_mission() -> MissionPlan:
    return MissionPlan.model_validate(make_mission_payload())
