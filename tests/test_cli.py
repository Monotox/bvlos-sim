import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

import adapters.cli as cli_module
from adapters.cli import CliExitCode, app
from adapters.envelope import RESULT_ENVELOPE_SCHEMA_VERSION
from adapters.version import tool_version
from tests.helpers import make_mission_payload, make_vehicle_payload

runner = CliRunner()


def _write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_cli_success_json_output_is_deterministic_and_complete(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.json"
    _write_yaml(mission_path, make_mission_payload())
    _write_json(vehicle_path, make_vehicle_payload())

    first = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])
    second = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert first.exit_code == int(CliExitCode.SUCCESS)
    assert second.exit_code == int(CliExitCode.SUCCESS)
    assert first.stdout == second.stdout

    envelope = json.loads(first.stdout)
    assert envelope["schema_version"] == RESULT_ENVELOPE_SCHEMA_VERSION
    assert envelope["tool_version"] == tool_version()
    assert envelope["status"] == "success"
    assert envelope["result_validity"]["is_complete"] is True
    assert envelope["result_validity"]["is_valid_for_full_mission"] is True
    assert envelope["result"]["status"] == "success"


def test_cli_markdown_can_write_to_file(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    output_path = tmp_path / "report.md"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "markdown",
            "--output",
            str(output_path),
        ],
    )
    stdout_result = runner.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--format",
            "markdown",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert stdout_result.exit_code == int(CliExitCode.SUCCESS)
    assert result.stdout == ""
    report = output_path.read_text(encoding="utf-8")
    assert report == stdout_result.stdout


def test_cli_partial_invalid_result_is_marked_partial(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["route"] = [
        mission_payload["route"][1],
        mission_payload["route"][2],
    ]
    mission_payload["route"][1]["loiter_time_s"] = -1.0

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["result_validity"]["is_partial"] is True
    assert envelope["result_validity"]["scope"] == "completed_legs_only"
    assert envelope["result"]["totals_are_partial"] is True
    assert envelope["diagnostics"][-1]["kind"] == "invalid_input"


def test_cli_unsupported_result_maps_to_exit_code(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["route"] = [mission_payload["route"][2]]
    vehicle_payload = make_vehicle_payload()
    vehicle_payload["vehicle_class"] = "fixed_wing"
    vehicle_payload["capabilities"] = {
        "hover": False,
        "forward_flight": True,
    }

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, vehicle_payload)

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    envelope = json.loads(result.stdout)
    assert envelope["diagnostics"][-1]["kind"] == "unsupported"
    assert envelope["result_validity"]["is_valid_for_full_mission"] is False


def test_cli_infeasible_result_maps_to_exit_code(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["route"] = [mission_payload["route"][1]]
    mission_payload["route"][0]["lat"] = 52.01
    mission_payload["route"][0]["lon"] = 4.0
    mission_payload["estimation"] = {
        "wind_east_mps": 30.0,
        "wind_north_mps": 0.0,
        "min_groundspeed_mps": 3.0,
    }

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "infeasible"
    assert envelope["diagnostics"][-1]["kind"] == "infeasible"


def test_cli_energy_infeasible_result_has_complete_result_validity(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    vehicle_payload = make_vehicle_payload()
    vehicle_payload["energy"]["battery_capacity_wh"] = 45.0
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, vehicle_payload)

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "infeasible"
    assert envelope["diagnostics"][-1]["code"] == "RESERVE_BELOW_THRESHOLD"
    assert envelope["result_validity"]["is_complete"] is True
    assert envelope["result_validity"]["is_valid_for_full_mission"] is True
    assert envelope["result"]["totals_are_partial"] is False
    assert envelope["result"]["energy"]["is_feasible"] is False


def test_cli_loads_relative_geofence_asset_and_reports_conflict(
    tmp_path: Path,
) -> None:
    mission_payload = make_mission_payload()
    mission_payload["assets"] = {"geofences_file": "geofences.geojson"}
    mission_payload["route"] = [mission_payload["route"][1]]

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    geofence_path = tmp_path / "geofences.geojson"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())
    _write_json(
        geofence_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "no_fly",
                    "properties": {"kind": "forbidden"},
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
            ],
        },
    )

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INFEASIBLE)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "infeasible"
    assert envelope["diagnostics"][-1]["code"] == "ROUTE_ENTERS_FORBIDDEN_ZONE"
    assert envelope["result_validity"]["is_complete"] is True
    assert envelope["provenance"]["inputs"]["geofences"]["format"] == "geojson"
    assert envelope["result"]["geofence"]["is_feasible"] is False


def test_cli_loads_relative_landing_zone_asset_and_reports_reachability(
    tmp_path: Path,
) -> None:
    mission_payload = make_mission_payload()
    mission_payload["assets"] = {"landing_zones_file": "landing_zones.geojson"}
    mission_payload["route"] = [mission_payload["route"][1]]

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    landing_zone_path = tmp_path / "landing_zones.geojson"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())
    _write_json(
        landing_zone_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "wp1_lz",
                    "properties": {},
                    "geometry": {
                        "type": "Point",
                        "coordinates": [4.002, 52.001],
                    },
                }
            ],
        },
    )

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "success"
    assert envelope["provenance"]["inputs"]["landing_zones"]["format"] == "geojson"
    assert envelope["result"]["landing_zone"]["is_feasible"] is True
    assert envelope["result"]["landing_zone"]["checked_zone_count"] == 1


def test_cli_unsupported_input_extension_maps_to_invalid_input(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.txt"
    vehicle_path = tmp_path / "vehicle.yaml"
    mission_path.write_text("not-used", encoding="utf-8")
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][-1]["kind"] == "invalid_input"
    assert envelope["diagnostics"][-1]["code"] == "INPUT_LOAD_ERROR"


def test_cli_mission_vehicle_profile_mismatch_maps_to_invalid_input(
    tmp_path: Path,
) -> None:
    mission_payload = make_mission_payload()
    mission_payload["vehicle_profile"] = "different_vehicle"

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][-1]["kind"] == "invalid_input"
    assert envelope["diagnostics"][-1]["message"] == (
        "mission.vehicle_profile must match vehicle.vehicle_id."
    )


def test_cli_internal_error_outputs_internal_error_envelope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    def raise_runtime_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        cli_module,
        "try_estimate_mission_distance_time",
        raise_runtime_error,
    )

    result = runner.invoke(app, ["estimate", str(mission_path), str(vehicle_path)])

    assert result.exit_code == int(CliExitCode.INTERNAL_ERROR)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][-1]["kind"] == "internal_error"
    assert envelope["diagnostics"][-1]["context"] == {"error_type": "RuntimeError"}


def test_cli_wind_layer_flag_tailwind_is_faster_than_headwind(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["route"] = [
        {
            "id": "wp_east",
            "action": "waypoint",
            "lat": 52.0,
            "lon": 4.05,
            "altitude_reference": "amsl",
            "altitude_m": 12.0,
            "acceptance_radius_m": 10.0,
        }
    ]

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    tail = runner.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--wind-layer", "12:5:0"],
    )
    head = runner.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--wind-layer", "12:-5:0"],
    )

    assert tail.exit_code == int(CliExitCode.SUCCESS)
    assert head.exit_code == int(CliExitCode.SUCCESS)
    tail_time = json.loads(tail.stdout)["result"]["total_time_s"]
    head_time = json.loads(head.stdout)["result"]["total_time_s"]
    assert tail_time < head_time


def test_cli_wind_layer_malformed_entry_returns_invalid_input(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--wind-layer", "12:5"],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][-1]["kind"] == "invalid_input"


def test_cli_fidelity_v2_returns_success(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--fidelity", "v2"],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "success"
    assert envelope["result"]["metadata"]["estimator_version"] == "v2"


def test_cli_explicit_fidelity_v1_overrides_mission_yaml_v2(tmp_path: Path) -> None:
    mission_payload = make_mission_payload()
    mission_payload["estimation"] = {"fidelity": "v2"}

    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, mission_payload)
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path), "--fidelity", "v1"],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    envelope = json.loads(result.stdout)
    assert envelope["result"]["metadata"]["options_source"] == "runtime_options"
    assert envelope["result"]["metadata"]["estimator_version"] == "v1"


def test_cli_combines_fidelity_wind_layer_and_max_segment_length(
    tmp_path: Path,
) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--fidelity",
            "v2",
            "--wind-layer",
            "0:2:0",
            "--wind-layer",
            "120:4:-1",
            "--max-segment-length-m",
            "500",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    envelope = json.loads(result.stdout)
    metadata = envelope["result"]["metadata"]
    assert metadata["estimator_version"] == "v2"
    assert metadata["options_source"] == "runtime_options"
    assert metadata["wind_provider_id"] == "layered"


def test_cli_fidelity_v1_default_unchanged(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        ["estimate", str(mission_path), str(vehicle_path)],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    envelope = json.loads(result.stdout)
    assert envelope["result"]["metadata"]["estimator_version"] == "v1"


def test_cli_max_segment_length_m_zero_returns_invalid_input(tmp_path: Path) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    result = runner.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--max-segment-length-m",
            "0",
        ],
    )

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][-1]["kind"] == "invalid_input"


def test_cli_output_write_failure_falls_back_to_stdout_internal_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    mission_path = tmp_path / "mission.yaml"
    vehicle_path = tmp_path / "vehicle.yaml"
    output_path = tmp_path / "report.json"
    _write_yaml(mission_path, make_mission_payload())
    _write_yaml(vehicle_path, make_vehicle_payload())

    def fail_write_text(self, data: str, encoding: str = "utf-8") -> int:
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", fail_write_text)

    result = runner.invoke(
        app,
        [
            "estimate",
            str(mission_path),
            str(vehicle_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == int(CliExitCode.INTERNAL_ERROR)
    envelope = json.loads(result.stdout)
    assert envelope["status"] == "error"
    assert envelope["diagnostics"][-1]["kind"] == "internal_error"
    assert envelope["diagnostics"][-1]["context"] == {"error_type": "OutputWriteError"}
