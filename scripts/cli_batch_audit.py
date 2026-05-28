"""Release-oriented CLI batch audit for bvlos-sim.

This script exercises the installed CLI through subprocess commands. It is
intended as an exhaustive smoke/regression sweep before release, not as a
replacement for the pytest suite.

Default invocation:

    uv run python scripts/cli_batch_audit.py

Use a different command prefix when needed:

    uv run python scripts/cli_batch_audit.py --command bvlos-sim
    uv run python scripts/cli_batch_audit.py --command python -m main
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

SUCCESS = 0
INFEASIBLE = 10
INVALID_INPUT = 11
UNSUPPORTED = 12
INTERNAL_ERROR = 13
USAGE_ERROR = 2


@dataclass(frozen=True)
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


CaseCheck = Callable[[CommandResult], None]


@dataclass(frozen=True)
class Case:
    name: str
    args: list[str]
    expected_exit: int
    check: CaseCheck | None = None


def _vehicle_payload() -> dict[str, Any]:
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


def _mission_payload() -> dict[str, Any]:
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


def _population_grid_payload(density_ppl_km2: float) -> dict[str, Any]:
    return {
        "origin_lat": 51.99,
        "origin_lon": 3.99,
        "step_lat_deg": 0.01,
        "step_lon_deg": 0.01,
        "density_ppl_km2": [
            [density_ppl_km2, density_ppl_km2, density_ppl_km2],
            [density_ppl_km2, density_ppl_km2, density_ppl_km2],
            [density_ppl_km2, density_ppl_km2, density_ppl_km2],
        ],
    }


def _scenario_payload(
    *,
    scenario_id: str = "audit-scenario",
    mission_file: str = "mission.yaml",
    vehicle_file: str = "vehicle.yaml",
    initial_conditions: dict[str, Any] | None = None,
    events: list[dict[str, Any]] | None = None,
    assertions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "scenario.v1",
        "scenario_id": scenario_id,
        "mission_file": mission_file,
        "vehicle_file": vehicle_file,
        "initial_conditions": initial_conditions or {},
        "events": events or [],
        "assertions": assertions
        or [{"assertion_id": "estimate-ok", "kind": "estimate_succeeds"}],
    }


def _write_yaml(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _payload_copy(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload))


def _json_stdout(result: CommandResult) -> dict[str, Any]:
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(
            f"stdout was not JSON for {' '.join(result.args)}:\n{result.stdout}\n{result.stderr}"
        ) from exc


def _expect_json_field(path: str, expected: Any) -> CaseCheck:
    def check(result: CommandResult) -> None:
        value: Any = _json_stdout(result)
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        if value != expected:
            raise AssertionError(f"{path}: expected {expected!r}, got {value!r}")

    return check


def _expect_markdown(prefix: str) -> CaseCheck:
    def check(result: CommandResult) -> None:
        if not result.stdout.startswith(prefix):
            raise AssertionError(
                f"expected markdown prefix {prefix!r}, got {result.stdout[:80]!r}"
            )

    return check


def _expect_output_file(
    path: Path, *, kind: str, expected_status: str | None = None
) -> CaseCheck:
    def check(result: CommandResult) -> None:
        if result.stdout:
            raise AssertionError(f"expected stdout to be empty, got {result.stdout!r}")
        if not path.exists():
            raise AssertionError(f"expected output file {path} to exist")
        text = path.read_text(encoding="utf-8")
        if kind == "json":
            payload = json.loads(text)
            if expected_status is not None and payload["status"] != expected_status:
                raise AssertionError(
                    f"{path} status: expected {expected_status!r}, got {payload['status']!r}"
                )
        elif kind == "markdown" and not text.startswith("#"):
            raise AssertionError(f"expected markdown report in {path}")
        elif kind not in {"json", "markdown"}:
            raise ValueError(kind)

    return check


def _expect_json_has(path: str) -> CaseCheck:
    def check(result: CommandResult) -> None:
        value: Any = _json_stdout(result)
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        if value is None:
            raise AssertionError(f"{path} should not be None")

    return check


def _estimate_case_status(status: str) -> CaseCheck:
    return _expect_json_field("status", status)


def _scenario_status(status: str) -> CaseCheck:
    return _expect_json_field("status", status)


def _write_common_files(root: Path) -> dict[str, Path]:
    paths = {
        "mission": _write_yaml(root / "mission.yaml", _mission_payload()),
        "mission_json": _write_json(root / "mission.json", _mission_payload()),
        "vehicle": _write_yaml(root / "vehicle.yaml", _vehicle_payload()),
        "vehicle_json": _write_json(root / "vehicle.json", _vehicle_payload()),
    }
    paths["scenario"] = _write_yaml(
        root / "scenario.yaml",
        _scenario_payload(),
    )
    paths["scenario_v2"] = _write_yaml(
        root / "scenario-v2.yaml",
        _scenario_payload(
            scenario_id="audit-scenario-v2",
            initial_conditions={
                "fidelity": "v2",
                "wind_layers": [
                    {"altitude_m": 0.0, "wind_east_mps": 2.0, "wind_north_mps": 0.0},
                    {"altitude_m": 120.0, "wind_east_mps": 4.0, "wind_north_mps": -1.0},
                ],
                "max_segment_length_m": 500.0,
            },
        ),
    )
    return paths


def _write_contract_only_sitl_evidence(
    scenario_path: Path,
    evidence_path: Path,
) -> Path:
    completed = subprocess.run(
        [sys.executable, "-m", "main", "sitl", str(scenario_path)],
        cwd=REPO_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if completed.returncode != SUCCESS:
        raise RuntimeError(
            "failed to build contract-only SITL evidence for CLI audit: "
            f"stdout={completed.stdout!r} stderr={completed.stderr!r}"
        )
    evidence_path.write_text(completed.stdout, encoding="utf-8")
    return evidence_path


def _geofence_feature(kind: str = "forbidden") -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": "audit_zone",
        "properties": {"kind": kind},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [4.001, 51.999],
                    [4.003, 51.999],
                    [4.003, 52.003],
                    [4.001, 52.003],
                    [4.001, 51.999],
                ]
            ],
        },
    }


def _landing_zone_feature(lon: float = 4.002, lat: float = 52.001) -> dict[str, Any]:
    return {
        "type": "Feature",
        "id": "audit_lz",
        "properties": {},
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
    }


def _build_cases(root: Path) -> list[Case]:
    paths = _write_common_files(root)

    output_json = root / "estimate-output.json"
    output_md = root / "estimate-output.md"
    scenario_output_json = root / "scenario-output.json"
    scenario_output_md = root / "scenario-output.md"
    output_dir = root / "output-dir"
    output_dir.mkdir()

    mission_with_fidelity_v2 = _payload_copy(_mission_payload())
    mission_with_fidelity_v2["estimation"] = {"fidelity": "v2"}
    mission_fidelity_v2_path = _write_yaml(
        root / "mission-fidelity-v2.yaml", mission_with_fidelity_v2
    )

    mission_with_layers = _payload_copy(_mission_payload())
    mission_with_layers["estimation"] = {
        "wind_layers": [
            {"altitude_m": 0.0, "wind_east_mps": 5.0, "wind_north_mps": 0.0}
        ],
        "max_segment_length_m": 250.0,
    }
    mission_layers_path = _write_yaml(root / "mission-layers.yaml", mission_with_layers)

    population_grid_path = _write_yaml(
        root / "population.yaml", _population_grid_payload(12.0)
    )
    ground_risk_vehicle = _payload_copy(_vehicle_payload())
    ground_risk_vehicle["characteristic_dimension_m"] = 1.0
    ground_risk_vehicle_path = _write_yaml(
        root / "vehicle-ground-risk.yaml", ground_risk_vehicle
    )
    mission_ground_risk = _payload_copy(_mission_payload())
    mission_ground_risk["assets"] = {
        "population_grid_file": population_grid_path.name
    }
    mission_ground_risk_path = _write_yaml(
        root / "mission-ground-risk.yaml", mission_ground_risk
    )

    mission_bad_extension = root / "mission.txt"
    mission_bad_extension.write_text("not used", encoding="utf-8")

    mission_bad_yaml = root / "mission-bad-yaml.yaml"
    mission_bad_yaml.write_text("{bad yaml: [", encoding="utf-8")

    mission_unknown_key = _payload_copy(_mission_payload())
    mission_unknown_key["unexpected"] = True
    mission_unknown_key_path = _write_yaml(
        root / "mission-unknown-key.yaml", mission_unknown_key
    )

    mission_profile_mismatch = _payload_copy(_mission_payload())
    mission_profile_mismatch["vehicle_profile"] = "different_vehicle"
    mission_profile_mismatch_path = _write_yaml(
        root / "mission-profile-mismatch.yaml", mission_profile_mismatch
    )

    low_energy_vehicle = _payload_copy(_vehicle_payload())
    low_energy_vehicle["energy"]["battery_capacity_wh"] = 45.0
    low_energy_vehicle_path = _write_yaml(
        root / "vehicle-low-energy.yaml", low_energy_vehicle
    )

    fixed_wing_vehicle = _payload_copy(_vehicle_payload())
    fixed_wing_vehicle["vehicle_class"] = "fixed_wing"
    fixed_wing_vehicle["capabilities"] = {"hover": False, "forward_flight": True}
    fixed_wing_vehicle_path = _write_yaml(
        root / "vehicle-fixed-wing.yaml", fixed_wing_vehicle
    )

    loiter_only_mission = _payload_copy(_mission_payload())
    loiter_only_mission["route"] = [loiter_only_mission["route"][2]]
    loiter_only_mission_path = _write_yaml(
        root / "mission-loiter-only.yaml", loiter_only_mission
    )

    infeasible_wind_mission = _payload_copy(_mission_payload())
    infeasible_wind_mission["route"] = [infeasible_wind_mission["route"][1]]
    infeasible_wind_mission["route"][0]["lat"] = 52.01
    infeasible_wind_mission["route"][0]["lon"] = 4.0
    infeasible_wind_mission["estimation"] = {
        "wind_east_mps": 30.0,
        "wind_north_mps": 0.0,
        "min_groundspeed_mps": 3.0,
    }
    infeasible_wind_mission_path = _write_yaml(
        root / "mission-infeasible-wind.yaml", infeasible_wind_mission
    )

    geofence_path = _write_json(
        root / "geofence.geojson",
        {"type": "FeatureCollection", "features": [_geofence_feature()]},
    )
    mission_geofence = _payload_copy(_mission_payload())
    mission_geofence["assets"] = {"geofences_file": geofence_path.name}
    mission_geofence["route"] = [mission_geofence["route"][1]]
    mission_geofence_path = _write_yaml(
        root / "mission-geofence.yaml", mission_geofence
    )

    geofence_bad_geometry = _write_json(
        root / "bad-geofence.geojson",
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "bad",
                    "properties": {"kind": "forbidden"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[4.0, 52.0], [4.1, 52.1]],
                    },
                }
            ],
        },
    )
    mission_bad_geofence = _payload_copy(_mission_payload())
    mission_bad_geofence["assets"] = {"geofences_file": geofence_bad_geometry.name}
    mission_bad_geofence_path = _write_yaml(
        root / "mission-bad-geofence.yaml", mission_bad_geofence
    )

    landing_zone_path = _write_json(
        root / "landing-zones.geojson",
        {"type": "FeatureCollection", "features": [_landing_zone_feature()]},
    )
    mission_landing_zone = _payload_copy(_mission_payload())
    mission_landing_zone["assets"] = {"landing_zones_file": landing_zone_path.name}
    mission_landing_zone["route"] = [mission_landing_zone["route"][1]]
    mission_landing_zone_path = _write_yaml(
        root / "mission-landing-zone.yaml", mission_landing_zone
    )

    far_landing_zone_path = _write_json(
        root / "far-landing-zones.geojson",
        {
            "type": "FeatureCollection",
            "features": [_landing_zone_feature(lon=5.0, lat=53.0)],
        },
    )
    mission_no_lz = _payload_copy(_mission_payload())
    mission_no_lz["assets"] = {"landing_zones_file": far_landing_zone_path.name}
    mission_no_lz["constraints"]["min_distance_to_landing_zone_m"] = 50.0
    mission_no_lz["route"] = [mission_no_lz["route"][1]]
    mission_no_lz_path = _write_yaml(root / "mission-no-lz.yaml", mission_no_lz)

    missing_asset_mission = _payload_copy(_mission_payload())
    missing_asset_mission["assets"] = {"geofences_file": "does-not-exist.geojson"}
    missing_asset_mission_path = _write_yaml(
        root / "mission-missing-geofence.yaml", missing_asset_mission
    )

    scenario_fail = _write_yaml(
        root / "scenario-fail.yaml",
        _scenario_payload(
            scenario_id="audit-scenario-fail",
            assertions=[
                {
                    "assertion_id": "too-fast",
                    "kind": "field_lt",
                    "field_path": "estimate.total_time_s",
                    "expected": 1.0,
                }
            ],
        ),
    )
    scenario_bad_schema = root / "scenario-bad-schema.yaml"
    scenario_bad_schema.write_text("scenario_id: missing-version\n", encoding="utf-8")
    scenario_bad_yaml = root / "scenario-bad-yaml.yaml"
    scenario_bad_yaml.write_text("{bad yaml: [", encoding="utf-8")
    scenario_missing_mission = _write_yaml(
        root / "scenario-missing-mission.yaml",
        _scenario_payload(mission_file="missing-mission.yaml"),
    )
    scenario_duplicate_events = _write_yaml(
        root / "scenario-duplicate-events.yaml",
        _scenario_payload(
            events=[
                {"event_id": "dup", "kind": "observe", "trigger": "at_mission_start"},
                {"event_id": "dup", "kind": "observe", "trigger": "at_mission_end"},
            ]
        ),
    )
    scenario_wind_change = _write_yaml(
        root / "scenario-wind-change.yaml",
        _scenario_payload(
            scenario_id="audit-scenario-wind-change",
            events=[
                {
                    "event_id": "wind",
                    "kind": "wind_change",
                    "trigger": "at_mission_start",
                    "wind_east_mps": 4.0,
                    "wind_north_mps": 0.0,
                }
            ],
        ),
    )
    scenario_skipped_assertion = _write_yaml(
        root / "scenario-skipped-assertion.yaml",
        _scenario_payload(
            assertions=[
                {
                    "assertion_id": "missing-geofence",
                    "kind": "field_eq",
                    "field_path": "estimate.geofence.is_feasible",
                    "expected": True,
                }
            ]
        ),
    )
    scenario_unsupported_assertion = _write_yaml(
        root / "scenario-unsupported-assertion.yaml",
        _scenario_payload(
            assertions=[
                {
                    "assertion_id": "boolean-with-numeric-op",
                    "kind": "field_lt",
                    "field_path": "estimate.energy.is_feasible",
                    "expected": 1.0,
                }
            ]
        ),
    )
    scenario_policy_pass = _write_yaml(
        root / "scenario-policy-pass.yaml",
        _scenario_payload(
            initial_conditions={
                "lost_link_policy": {"action": "rtl", "loiter_s": 30.0}
            },
            events=[
                {
                    "event_id": "lost-link",
                    "kind": "lost_link",
                    "trigger": "at_route_item",
                    "trigger_route_item_id": "wp1",
                }
            ],
            assertions=[
                {
                    "assertion_id": "policy-action",
                    "kind": "policy_action_eq",
                    "event_id": "lost-link",
                    "expected": "rtl",
                }
            ],
        ),
    )
    scenario_policy_fail = _write_yaml(
        root / "scenario-policy-fail.yaml",
        _scenario_payload(
            initial_conditions={
                "lost_link_policy": {"action": "rtl", "loiter_s": 30.0}
            },
            events=[
                {
                    "event_id": "lost-link",
                    "kind": "lost_link",
                    "trigger": "at_route_item",
                    "trigger_route_item_id": "wp1",
                }
            ],
            assertions=[
                {
                    "assertion_id": "policy-action",
                    "kind": "policy_action_eq",
                    "event_id": "lost-link",
                    "expected": "land",
                }
            ],
        ),
    )
    sitl_evidence_path = _write_contract_only_sitl_evidence(
        paths["scenario"],
        root / "sitl-evidence.json",
    )

    cases = [
        Case("top-level help", ["--help"], SUCCESS),
        Case("estimate help", ["estimate", "--help"], SUCCESS),
        Case("scenario help", ["scenario", "--help"], SUCCESS),
        Case("estimate no args usage error", ["estimate"], USAGE_ERROR),
        Case("scenario no args usage error", ["scenario"], USAGE_ERROR),
        Case(
            "estimate example yaml json stdout",
            ["estimate", str(paths["mission"]), str(paths["vehicle"])],
            SUCCESS,
            _estimate_case_status("success"),
        ),
        Case(
            "estimate mission json vehicle json",
            ["estimate", str(paths["mission_json"]), str(paths["vehicle_json"])],
            SUCCESS,
            _expect_json_field("result.status", "success"),
        ),
        Case(
            "estimate markdown stdout",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--format",
                "markdown",
            ],
            SUCCESS,
            _expect_markdown("# Estimator Report"),
        ),
        Case(
            "estimate ground risk markdown",
            [
                "estimate",
                str(mission_ground_risk_path),
                str(ground_risk_vehicle_path),
                "--format",
                "ground-risk",
            ],
            SUCCESS,
            _expect_markdown("# Ground Risk Class"),
        ),
        Case(
            "estimate json output file",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--output",
                str(output_json),
            ],
            SUCCESS,
            _expect_output_file(output_json, kind="json", expected_status="success"),
        ),
        Case(
            "estimate markdown output file",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--format",
                "markdown",
                "--output",
                str(output_md),
            ],
            SUCCESS,
            _expect_output_file(output_md, kind="markdown"),
        ),
        Case(
            "estimate invalid format option",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--format",
                "html",
            ],
            USAGE_ERROR,
        ),
        Case(
            "estimate output path is directory",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--output",
                str(output_dir),
            ],
            INTERNAL_ERROR,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate fidelity v2",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--fidelity",
                "v2",
            ],
            SUCCESS,
            _expect_json_field("result.metadata.estimator_version", "v2"),
        ),
        Case(
            "estimate explicit fidelity v1 overrides mission yaml v2",
            [
                "estimate",
                str(mission_fidelity_v2_path),
                str(paths["vehicle"]),
                "--fidelity",
                "v1",
            ],
            SUCCESS,
            _expect_json_field("result.metadata.estimator_version", "v1"),
        ),
        Case(
            "estimate mission yaml fidelity v2",
            ["estimate", str(mission_fidelity_v2_path), str(paths["vehicle"])],
            SUCCESS,
            _expect_json_field("result.metadata.estimator_version", "v2"),
        ),
        Case(
            "estimate invalid fidelity option",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--fidelity",
                "v3",
            ],
            USAGE_ERROR,
        ),
        Case(
            "estimate wind layer",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--wind-layer",
                "0:2:0",
            ],
            SUCCESS,
            _expect_json_field("result.metadata.wind_provider_id", "layered"),
        ),
        Case(
            "estimate malformed wind layer too few parts",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--wind-layer",
                "0:2",
            ],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate malformed wind layer nonnumeric",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--wind-layer",
                "0:east:0",
            ],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate max segment length zero",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--max-segment-length-m",
                "0",
            ],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate max segment length negative",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--max-segment-length-m",
                "-1",
            ],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate combined v2 layered max segment",
            [
                "estimate",
                str(paths["mission"]),
                str(paths["vehicle"]),
                "--fidelity",
                "v2",
                "--wind-layer",
                "0:2:0",
                "--wind-layer",
                "120:4:-1",
                "--max-segment-length-m",
                "500",
            ],
            SUCCESS,
            _expect_json_field("result.metadata.wind_provider_id", "layered"),
        ),
        Case(
            "estimate mission yaml wind layers",
            ["estimate", str(mission_layers_path), str(paths["vehicle"])],
            SUCCESS,
            _expect_json_field("result.metadata.wind_provider_id", "layered"),
        ),
        Case(
            "estimate unsupported extension",
            ["estimate", str(mission_bad_extension), str(paths["vehicle"])],
            INVALID_INPUT,
            _expect_json_field("diagnostics.0.code", "INPUT_LOAD_ERROR"),
        ),
        Case(
            "estimate malformed mission yaml",
            ["estimate", str(mission_bad_yaml), str(paths["vehicle"])],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate unknown mission field",
            ["estimate", str(mission_unknown_key_path), str(paths["vehicle"])],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate missing mission file",
            ["estimate", str(root / "missing.yaml"), str(paths["vehicle"])],
            USAGE_ERROR,
        ),
        Case(
            "estimate mission vehicle mismatch",
            ["estimate", str(mission_profile_mismatch_path), str(paths["vehicle"])],
            INVALID_INPUT,
            _expect_json_field("diagnostics.0.kind", "invalid_input"),
        ),
        Case(
            "estimate energy reserve infeasible",
            ["estimate", str(paths["mission"]), str(low_energy_vehicle_path)],
            INFEASIBLE,
            _expect_json_field("result.failure.code", "RESERVE_BELOW_THRESHOLD"),
        ),
        Case(
            "estimate fixed-wing loiter unsupported in v1",
            ["estimate", str(loiter_only_mission_path), str(fixed_wing_vehicle_path)],
            UNSUPPORTED,
            _expect_json_field("diagnostics.0.kind", "unsupported"),
        ),
        Case(
            "estimate fixed-wing loiter supported in v2",
            [
                "estimate",
                str(loiter_only_mission_path),
                str(fixed_wing_vehicle_path),
                "--fidelity",
                "v2",
            ],
            SUCCESS,
            _estimate_case_status("success"),
        ),
        Case(
            "estimate wind infeasible",
            ["estimate", str(infeasible_wind_mission_path), str(paths["vehicle"])],
            INFEASIBLE,
            _expect_json_field("diagnostics.0.kind", "infeasible"),
        ),
        Case(
            "estimate geofence conflict",
            ["estimate", str(mission_geofence_path), str(paths["vehicle"])],
            INFEASIBLE,
            _expect_json_field("diagnostics.1.code", "ROUTE_ENTERS_FORBIDDEN_ZONE"),
        ),
        Case(
            "estimate geofence unsupported geometry",
            ["estimate", str(mission_bad_geofence_path), str(paths["vehicle"])],
            UNSUPPORTED,
            _expect_json_has("diagnostics.0.code"),
        ),
        Case(
            "estimate missing geofence asset",
            ["estimate", str(missing_asset_mission_path), str(paths["vehicle"])],
            INVALID_INPUT,
            _estimate_case_status("error"),
        ),
        Case(
            "estimate landing zone reachable",
            ["estimate", str(mission_landing_zone_path), str(paths["vehicle"])],
            SUCCESS,
            _expect_json_field("result.landing_zone.is_feasible", True),
        ),
        Case(
            "estimate no reachable landing zone",
            ["estimate", str(mission_no_lz_path), str(paths["vehicle"])],
            INFEASIBLE,
            _expect_json_field("diagnostics.1.code", "NO_REACHABLE_LANDING_ZONE"),
        ),
        Case(
            "scenario baseline passes",
            ["scenario", str(paths["scenario"])],
            SUCCESS,
            _scenario_status("passed"),
        ),
        Case(
            "scenario v2 passes",
            ["scenario", str(paths["scenario_v2"])],
            SUCCESS,
            _expect_json_field("estimate.metadata.estimator_version", "v2"),
        ),
        Case(
            "scenario markdown stdout",
            ["scenario", str(paths["scenario"]), "--format", "markdown"],
            SUCCESS,
            _expect_markdown("# Scenario Report"),
        ),
        Case(
            "scenario json output file",
            ["scenario", str(paths["scenario"]), "--output", str(scenario_output_json)],
            SUCCESS,
            _expect_output_file(
                scenario_output_json, kind="json", expected_status="passed"
            ),
        ),
        Case(
            "scenario markdown output file",
            [
                "scenario",
                str(paths["scenario"]),
                "--format",
                "markdown",
                "--output",
                str(scenario_output_md),
            ],
            SUCCESS,
            _expect_output_file(scenario_output_md, kind="markdown"),
        ),
        Case(
            "scenario invalid format option",
            ["scenario", str(paths["scenario"]), "--format", "html"],
            USAGE_ERROR,
        ),
        Case(
            "scenario output path is directory",
            ["scenario", str(paths["scenario"]), "--output", str(output_dir)],
            INTERNAL_ERROR,
            _scenario_status("error"),
        ),
        Case(
            "scenario assertion failure exits 10",
            ["scenario", str(scenario_fail)],
            INFEASIBLE,
            _scenario_status("failed"),
        ),
        Case(
            "scenario invalid schema",
            ["scenario", str(scenario_bad_schema)],
            INVALID_INPUT,
            _scenario_status("error"),
        ),
        Case(
            "scenario malformed yaml",
            ["scenario", str(scenario_bad_yaml)],
            INVALID_INPUT,
            _scenario_status("error"),
        ),
        Case(
            "scenario missing referenced mission",
            ["scenario", str(scenario_missing_mission)],
            INVALID_INPUT,
            _scenario_status("error"),
        ),
        Case(
            "scenario missing file",
            ["scenario", str(root / "missing-scenario.yaml")],
            USAGE_ERROR,
        ),
        Case(
            "scenario duplicate event ids",
            ["scenario", str(scenario_duplicate_events)],
            INVALID_INPUT,
            _scenario_status("error"),
        ),
        Case(
            "scenario wind_change event fires",
            ["scenario", str(scenario_wind_change)],
            SUCCESS,
            _expect_json_field("event_outcomes.0.fired", True),
        ),
        Case(
            "scenario wind_change uses time-varying provider",
            ["scenario", str(scenario_wind_change)],
            SUCCESS,
            _expect_json_field("estimate.metadata.wind_provider_id", "time-varying"),
        ),
        Case(
            "scenario skipped assertion remains passed",
            ["scenario", str(scenario_skipped_assertion)],
            SUCCESS,
            _expect_json_field("assertion_results.0.outcome", "skipped"),
        ),
        Case(
            "scenario unsupported assertion remains passed",
            ["scenario", str(scenario_unsupported_assertion)],
            SUCCESS,
            _expect_json_field("assertion_results.0.outcome", "unsupported"),
        ),
        Case(
            "scenario policy assertion passes",
            ["scenario", str(scenario_policy_pass)],
            SUCCESS,
            _expect_json_field("assertion_results.0.outcome", "passed"),
        ),
        Case(
            "scenario policy assertion fails",
            ["scenario", str(scenario_policy_fail)],
            INFEASIBLE,
            _scenario_status("failed"),
        ),
        Case("propagate help", ["propagate", "--help"], SUCCESS),
        Case("propagate no args usage error", ["propagate"], USAGE_ERROR),
        Case(
            "propagate example yaml",
            [
                "propagate",
                str(
                    Path(__file__).resolve().parents[1]
                    / "examples/stochastic/pipeline_demo_001_stochastic.yaml"
                ),
                "--format",
                "summary",
            ],
            SUCCESS,
        ),
        Case(
            "propagate bad schema exits invalid input",
            ["propagate", str(scenario_bad_schema)],
            INVALID_INPUT,
        ),
        Case("convert help", ["convert", "--help"], SUCCESS),
        Case("convert no args usage error", ["convert"], USAGE_ERROR),
        Case(
            "convert missing vehicle profile exits invalid input",
            ["convert", str(paths["scenario"])],
            INVALID_INPUT,
        ),
        Case(
            "convert example plan",
            [
                "convert",
                str(
                    Path(__file__).resolve().parents[1]
                    / "examples/missions/pipeline_demo_001.plan"
                ),
                "--vehicle-profile",
                "quadplane_v1",
                "--validate-only",
            ],
            SUCCESS,
        ),
        Case("batch help", ["batch", "--help"], SUCCESS),
        Case("batch no args usage error", ["batch"], USAGE_ERROR),
        Case(
            "batch example manifest summary",
            [
                "batch",
                str(
                    Path(__file__).resolve().parents[1]
                    / "examples/batch/demo_batch.yaml"
                ),
                "--format",
                "summary",
            ],
            INFEASIBLE,
        ),
        Case(
            "batch bad schema exits invalid input",
            ["batch", str(scenario_bad_schema)],
            INVALID_INPUT,
        ),
        Case("size-battery help", ["size-battery", "--help"], SUCCESS),
        Case("size-battery no args usage error", ["size-battery"], USAGE_ERROR),
        Case(
            "size-battery example summary",
            [
                "size-battery",
                str(
                    Path(__file__).resolve().parents[1]
                    / "examples/missions/pipeline_demo_001.yaml"
                ),
                str(
                    Path(__file__).resolve().parents[1]
                    / "examples/vehicles/quadplane_v1.yaml"
                ),
                "--format",
                "summary",
            ],
            SUCCESS,
        ),
        Case("sample help", ["sample", "--help"], SUCCESS),
        Case("sample no args usage error", ["sample"], USAGE_ERROR),
        Case(
            "sample example yaml",
            [
                "sample",
                str(
                    Path(__file__).resolve().parents[1]
                    / "examples/uncertainty/pipeline_demo_001_wind_uncertainty.yaml"
                ),
            ],
            SUCCESS,
        ),
        Case(
            "sample bad schema exits invalid input",
            ["sample", str(scenario_bad_schema)],
            INVALID_INPUT,
        ),
        Case("sitl help", ["sitl", "--help"], SUCCESS),
        Case("sitl no args usage error", ["sitl"], USAGE_ERROR),
        Case(
            "sitl contract only",
            ["sitl", str(paths["scenario"])],
            SUCCESS,
        ),
        Case(
            "sitl bad schema exits invalid input",
            ["sitl", str(scenario_bad_schema)],
            INVALID_INPUT,
        ),
        Case(
            "sitl live missing artifact dir exits invalid input",
            ["sitl", str(paths["scenario"]), "--live"],
            INVALID_INPUT,
        ),
        Case("compare help", ["compare", "--help"], SUCCESS),
        Case("compare no args usage error", ["compare"], USAGE_ERROR),
        Case(
            "compare contract only exits unsupported",
            ["compare", str(sitl_evidence_path)],
            UNSUPPORTED,
        ),
        Case(
            "compare bad evidence exits invalid input",
            ["compare", str(scenario_bad_yaml)],
            INVALID_INPUT,
        ),
        Case(
            "compare bad comparison id exits invalid input",
            ["compare", str(sitl_evidence_path), "--comparison-id", "bad id"],
            INVALID_INPUT,
        ),
    ]
    return cases


def _run_case(command: list[str], case: Case, *, env: dict[str, str]) -> CommandResult:
    args = [*command, *case.args]
    completed = subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return CommandResult(
        args=args,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _format_failure(case: Case, result: CommandResult, message: str) -> str:
    return "\n".join(
        [
            f"case: {case.name}",
            f"command: {' '.join(result.args)}",
            f"expected exit: {case.expected_exit}",
            f"actual exit: {result.returncode}",
            f"failure: {message}",
            "stdout:",
            result.stdout or "<empty>",
            "stderr:",
            result.stderr or "<empty>",
        ]
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a broad bvlos-sim CLI batch audit."
    )
    parser.add_argument(
        "--command",
        nargs="+",
        default=["uv", "run", "bvlos-sim"],
        help="CLI command prefix to run. Default: uv run bvlos-sim",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep generated temporary files for debugging.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every command before running it.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", ".uv-cache")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")

    failures: list[str] = []
    temp_dir = tempfile.TemporaryDirectory(prefix="bvlos-cli-audit-")
    try:
        root = Path(temp_dir.name)
        cases = _build_cases(root)
        print(f"CLI batch audit: {len(cases)} cases")
        print(f"command prefix: {' '.join(args.command)}")
        print(f"temp dir: {root}")

        for index, case in enumerate(cases, start=1):
            if args.verbose:
                print(
                    f"[{index:02d}/{len(cases):02d}] {' '.join([*args.command, *case.args])}"
                )
            result = _run_case(args.command, case, env=env)
            try:
                if result.returncode != case.expected_exit:
                    raise AssertionError(
                        f"expected exit {case.expected_exit}, got {result.returncode}"
                    )
                if case.check is not None:
                    case.check(result)
            except AssertionError as exc:
                failures.append(_format_failure(case, result, str(exc)))
                print(f"[FAIL] {case.name}")
            else:
                print(f"[ OK ] {case.name}")

        if failures:
            print("\nCLI batch audit failures:\n", file=sys.stderr)
            print("\n\n".join(failures), file=sys.stderr)
            return 1

        print(f"\nCLI batch audit passed: {len(cases)} cases")
        return 0
    finally:
        if args.keep_temp:
            print(f"kept temp dir: {temp_dir.name}")
        else:
            temp_dir.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
