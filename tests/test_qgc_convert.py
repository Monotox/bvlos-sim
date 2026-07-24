import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from bvlos_sim.adapters.cli import CliExitCode, app
from bvlos_sim.adapters.qgc_plan import load_and_convert_plan, parse_qgc_plan

_runner = CliRunner()

PLAN_FILE = Path(__file__).resolve().parents[1] / "examples" / "missions" / "pipeline_demo_001.plan"

_VP = "test_vehicle"


def _simple_item(
    command: int,
    *,
    frame: int = 3,
    coordinate: list[object] | None = None,
    params: list[object] | None = None,
) -> dict[str, object]:
    return {
        "type": "SimpleItem",
        "command": command,
        "frame": frame,
        "coordinate": [52.0, 4.0, 80.0] if coordinate is None else coordinate,
        "params": [0, 0, 0, None, 0, 0, 80.0] if params is None else params,
    }


def _plan(items: list[object]) -> dict[str, object]:
    return {
        "fileType": "Plan",
        "mission": {
            "plannedHomePosition": [52.0, 4.0, 12.0],
            "cruiseSpeed": 18.0,
            "hoverSpeed": 5.0,
            "items": items,
        },
    }


def test_minimal_valid_plan_converts_takeoff_and_rtl() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                _simple_item(22),
                _simple_item(20, coordinate=[0, 0, 0], params=[0, 0, 0, 0, 0, 0, 0]),
            ]
        ),
        vehicle_profile=_VP,
    )

    # MAV_CMD_NAV_TAKEOFF (22) emits a normalisation warning
    assert len(diagnostics) == 1
    assert diagnostics[0].command == 22
    assert "vtol_takeoff" in diagnostics[0].message
    assert mission["planned_home"] == {
        "lat": 52.0,
        "lon": 4.0,
        "altitude_amsl_m": 12.0,
    }
    assert mission["defaults"] == {
        "cruise_speed_mps": 18.0,
        "hover_speed_mps": 5.0,
        "altitude_reference": "relative_home",
    }
    assert mission["route"] == [
        {"id": "takeoff", "action": "vtol_takeoff", "altitude_m": 80.0},
        {"id": "rtl", "action": "rtl"},
    ]
    assert mission["constraints"] == {}


def test_plan_with_waypoints_and_loiter_extracts_fields() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                _simple_item(16, coordinate=[52.001, 4.002, 120.0]),
                _simple_item(
                    19,
                    coordinate=[52.002, 4.004, 120.0],
                    params=[60.0, 0, 80.0, 0, 0, 0, 120.0],
                ),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert diagnostics == []
    assert mission["route"] == [
        {
            "id": "wp1",
            "action": "waypoint",
            "lat": 52.001,
            "lon": 4.002,
            "altitude_m": 120.0,
        },
        {
            "id": "loiter1",
            "action": "loiter_time",
            "lat": 52.002,
            "lon": 4.004,
            "altitude_m": 120.0,
            "loiter_time_s": 60.0,
            "loiter_radius_m": 80.0,
        },
    ]


def test_complex_item_produces_diagnostic_and_rest_of_route_is_parsed() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                {"type": "ComplexItem", "command": 16, "frame": 3},
                _simple_item(20, coordinate=[0, 0, 0], params=[0, 0, 0, 0, 0, 0, 0]),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert mission["route"] == [{"id": "rtl", "action": "rtl"}]
    assert len(diagnostics) == 1
    assert diagnostics[0].item_index == 0
    assert diagnostics[0].command == 16
    assert "unsupported mission item type" in diagnostics[0].message


def test_unknown_command_produces_diagnostic_and_item_is_skipped() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(999)]),
        vehicle_profile=_VP,
    )

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].item_index == 0
    assert diagnostics[0].command == 999
    assert "unsupported MAVLink command" in diagnostics[0].message


def test_loiter_with_zero_time_produces_diagnostic() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(19, params=[0.0, 0, 80.0, 0, 0, 0, 120.0])]),
        vehicle_profile=_VP,
    )

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].command == 19
    assert "loiter time must be a positive number" in diagnostics[0].message


def test_land_action_preserves_coordinates() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(21, coordinate=[52.003, 4.005, 0.0])]),
        vehicle_profile=_VP,
    )

    assert diagnostics == []
    assert mission["route"] == [
        {"id": "land", "action": "land", "lat": 52.003, "lon": 4.005, "altitude_m": 0.0}
    ]


def test_vtol_land_action_preserves_coordinates() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(85, coordinate=[52.004, 4.006, 0.0])]),
        vehicle_profile=_VP,
    )

    assert diagnostics == []
    assert mission["route"] == [
        {"id": "land", "action": "land", "lat": 52.004, "lon": 4.006, "altitude_m": 0.0}
    ]


def test_land_with_missing_coordinate_produces_diagnostic() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(21, coordinate=[52.001, "bad-lon", 0.0])]),
        vehicle_profile=_VP,
    )

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].command == 21
    assert diagnostics[0].message == "land coordinate missing or invalid"


def test_invalid_waypoint_coordinate_produces_diagnostic() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(16, coordinate=[52.001, "bad-lon", 120.0])]),
        vehicle_profile=_VP,
    )

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].command == 16
    assert diagnostics[0].message == "waypoint coordinate missing or invalid"


def test_invalid_file_type_raises_value_error() -> None:
    plan = _plan([])
    plan["fileType"] = "Mission"

    with pytest.raises(ValueError, match="fileType"):
        parse_qgc_plan(plan, vehicle_profile=_VP)


def test_non_list_items_raises_value_error() -> None:
    plan = _plan([])
    mission = plan["mission"]
    assert isinstance(mission, dict)
    mission["items"] = "not-a-list"

    with pytest.raises(ValueError, match="mission.items"):
        parse_qgc_plan(plan, vehicle_profile=_VP)


def test_missing_planned_home_raises_value_error() -> None:
    with pytest.raises(ValueError, match="plannedHomePosition missing"):
        parse_qgc_plan(
            {"fileType": "Plan", "mission": {"items": []}},
            vehicle_profile=_VP,
        )


def test_vehicle_profile_is_threaded_into_converted_mission() -> None:
    from bvlos_sim.schemas.mission import MissionPlan

    mission, _ = parse_qgc_plan(
        _plan([_simple_item(16, coordinate=[52.001, 4.002, 120.0])]),
        vehicle_profile="quadplane_v1",
    )

    assert mission["vehicle_profile"] == "quadplane_v1"
    loaded = MissionPlan.model_validate(mission)
    assert loaded.vehicle_profile == "quadplane_v1"


def test_converted_mission_contains_no_fixme_placeholder() -> None:
    mission, _ = parse_qgc_plan(
        _plan([_simple_item(22)]),
        vehicle_profile="my_drone",
    )

    assert "FIXME" not in str(mission)


def test_metadata_note_does_not_mention_placeholder() -> None:
    mission, _ = parse_qgc_plan(
        _plan([]),
        vehicle_profile=_VP,
    )

    note = str(mission.get("metadata", {}).get("notes", ""))
    assert "FIXME" not in note
    assert "Replace" not in note


def test_all_amsl_frames_sets_altitude_reference_amsl() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                "not-an-item",
                _simple_item(22, frame=0),
                _simple_item(
                    20,
                    frame=0,
                    coordinate=[0, 0, 0],
                    params=[0, 0, 0, 0, 0, 0, 0],
                ),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert len(diagnostics) == 2
    assert diagnostics[0].message == "mission item is not an object; item skipped"
    assert "vtol_takeoff" in diagnostics[1].message
    assert mission["defaults"]["altitude_reference"] == "amsl"


def test_simple_item_with_null_command_produces_preflight_diagnostic() -> None:
    plan = _plan([{"type": "SimpleItem", "command": None, "frame": 3, "coordinate": [52.0, 4.0, 80.0], "params": []}])
    mission, diagnostics = parse_qgc_plan(plan, vehicle_profile=_VP)

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert "command missing or invalid" in diagnostics[0].message


def test_loiter_with_invalid_coordinate_produces_diagnostic() -> None:
    plan = _plan([_simple_item(19, coordinate=[52.0, "bad", 0.0], params=[60.0, 0, 0, 0, 0, 0, 120.0])])
    mission, diagnostics = parse_qgc_plan(plan, vehicle_profile=_VP)

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert "loiter coordinate missing or invalid" in diagnostics[0].message


def test_takeoff_with_missing_altitude_produces_diagnostic() -> None:
    plan = _plan([{"type": "SimpleItem", "command": 22, "frame": 3, "coordinate": None, "params": [0, 0, 0, 0, 0, 0, None]}])
    mission, diagnostics = parse_qgc_plan(plan, vehicle_profile=_VP)

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert "takeoff altitude missing or invalid" in diagnostics[0].message


def test_frame_10_terrain_sets_terrain_altitude_reference() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                _simple_item(84, frame=10),
                _simple_item(16, frame=10, coordinate=[52.001, 4.002, 120.0]),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert diagnostics == []
    assert mission["defaults"]["altitude_reference"] == "terrain"
    assert all("altitude_reference" not in item for item in mission["route"])


def test_mixed_frames_keep_per_item_altitude_reference_override() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                _simple_item(16, frame=3, coordinate=[52.001, 4.002, 120.0]),
                _simple_item(16, frame=3, coordinate=[52.002, 4.003, 120.0]),
                _simple_item(16, frame=0, coordinate=[52.003, 4.004, 120.0]),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert diagnostics == []
    assert mission["defaults"]["altitude_reference"] == "relative_home"
    assert "altitude_reference" not in mission["route"][0]
    assert "altitude_reference" not in mission["route"][1]
    assert mission["route"][2]["altitude_reference"] == "amsl"


def test_unknown_frame_is_a_lossy_diagnostic() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(16, frame=5, coordinate=[52.001, 4.002, 120.0])]),
        vehicle_profile=_VP,
    )

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].lossy is True
    assert "unsupported altitude frame 5" in diagnostics[0].message


def test_rtl_mission_frame_is_ignored_for_altitude_reference() -> None:
    # QGC writes RTL with the non-positional MAV_FRAME_MISSION (2); it must
    # neither count as a loss nor drag the mission default off amsl.
    mission, diagnostics = parse_qgc_plan(
        _plan(
            [
                _simple_item(16, frame=0, coordinate=[52.001, 4.002, 120.0]),
                _simple_item(
                    20, frame=2, coordinate=[0, 0, 0], params=[0, 0, 0, 0, 0, 0, 0]
                ),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert diagnostics == []
    assert mission["defaults"]["altitude_reference"] == "amsl"


def test_takeoff_normalisation_warning_is_not_lossy() -> None:
    _, diagnostics = parse_qgc_plan(_plan([_simple_item(22)]), vehicle_profile=_VP)

    assert len(diagnostics) == 1
    assert diagnostics[0].lossy is False


def test_dropped_item_diagnostics_are_lossy() -> None:
    _, diagnostics = parse_qgc_plan(
        _plan(
            [
                {"type": "ComplexItem", "complexItemType": "survey", "command": 16},
                _simple_item(999),
            ]
        ),
        vehicle_profile=_VP,
    )

    assert [diagnostic.lossy for diagnostic in diagnostics] == [True, True]


def test_populated_geofence_and_rally_sections_are_lossy_diagnostics() -> None:
    plan = _plan([])
    plan["geoFence"] = {
        "circles": [],
        "polygons": [{"polygon": [[52.0, 4.0]]}],
        "version": 2,
    }
    plan["rallyPoints"] = {"points": [[52.0, 4.0, 20.0]], "version": 2}

    mission, diagnostics = parse_qgc_plan(plan, vehicle_profile=_VP)

    assert [diagnostic.section for diagnostic in diagnostics] == [
        "geoFence",
        "rallyPoints",
    ]
    assert all(diagnostic.lossy for diagnostic in diagnostics)
    assert all(diagnostic.item_index is None for diagnostic in diagnostics)


def test_empty_geofence_and_rally_sections_are_not_losses() -> None:
    plan = _plan([])
    plan["geoFence"] = {"circles": [], "polygons": [], "version": 2}
    plan["rallyPoints"] = {"points": [], "version": 2}

    _, diagnostics = parse_qgc_plan(plan, vehicle_profile=_VP)

    assert diagnostics == []


def test_mission_without_cruise_or_hover_speed_defaults_are_omitted() -> None:
    raw = {
        "fileType": "Plan",
        "mission": {
            "plannedHomePosition": [52.0, 4.0, 12.0],
            "items": [],
        },
    }
    mission, diagnostics = parse_qgc_plan(raw, vehicle_profile=_VP)

    assert diagnostics == []
    assert "cruise_speed_mps" not in mission["defaults"]
    assert "hover_speed_mps" not in mission["defaults"]


# ---------------------------------------------------------------------------
# load_and_convert_plan
# ---------------------------------------------------------------------------


def test_load_and_convert_plan_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unable to read"):
        load_and_convert_plan(tmp_path / "nonexistent.plan", vehicle_profile=_VP)


def test_load_and_convert_plan_raises_on_invalid_json(tmp_path: Path) -> None:
    plan_file = tmp_path / "bad.plan"
    plan_file.write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="Unable to parse"):
        load_and_convert_plan(plan_file, vehicle_profile=_VP)


def test_load_and_convert_plan_raises_on_non_object_root(tmp_path: Path) -> None:
    plan_file = tmp_path / "array.plan"
    plan_file.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError, match="must be a JSON object"):
        load_and_convert_plan(plan_file, vehicle_profile=_VP)


def test_load_and_convert_plan_sets_mission_id_from_filename(tmp_path: Path) -> None:
    plan_file = tmp_path / "my_mission.plan"
    plan_file.write_text(json.dumps(_plan([])), encoding="utf-8")

    mission, _ = load_and_convert_plan(plan_file, vehicle_profile=_VP)

    assert mission["mission_id"] == "my_mission"


def test_load_and_convert_plan_threads_vehicle_profile(tmp_path: Path) -> None:
    plan_file = tmp_path / "demo.plan"
    plan_file.write_text(json.dumps(_plan([])), encoding="utf-8")

    mission, _ = load_and_convert_plan(plan_file, vehicle_profile="quadplane_v1")

    assert mission["vehicle_profile"] == "quadplane_v1"


# ---------------------------------------------------------------------------
# CLI acceptance tests
# ---------------------------------------------------------------------------


def _yaml_from_output(output: str) -> str:
    """Strip CLI warning lines so the remainder parses as YAML."""
    return "\n".join(
        line for line in output.splitlines() if not line.startswith("Warning:")
    )


def test_convert_cli_writes_vehicle_profile_in_output() -> None:
    result = _runner.invoke(
        app, ["convert", str(PLAN_FILE), "--vehicle-profile", "quadplane_v1"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    parsed = yaml.safe_load(_yaml_from_output(result.output))
    assert parsed["vehicle_profile"] == "quadplane_v1"


def test_convert_cli_output_contains_no_fixme() -> None:
    result = _runner.invoke(
        app, ["convert", str(PLAN_FILE), "--vehicle-profile", "my_vehicle"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "FIXME" not in result.output


def test_convert_cli_missing_vehicle_profile_exits_invalid_input() -> None:
    result = _runner.invoke(app, ["convert", str(PLAN_FILE)])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
    assert "--vehicle-profile" in result.output or "--vehicle-profile" in (result.stderr or "")


def test_convert_cli_blank_vehicle_profile_exits_invalid_input() -> None:
    result = _runner.invoke(app, ["convert", str(PLAN_FILE), "--vehicle-profile", "   "])
    assert result.exit_code == int(CliExitCode.INVALID_INPUT)


def test_convert_cli_validate_only_with_vehicle_profile_exits_success() -> None:
    result = _runner.invoke(
        app, ["convert", str(PLAN_FILE), "--vehicle-profile", "quadplane_v1", "--validate-only"]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "OK" in result.output
    assert "route:" not in result.output


def test_convert_cli_writes_to_output_file_with_profile(tmp_path: Path) -> None:
    out = tmp_path / "mission.yaml"
    result = _runner.invoke(
        app, ["convert", str(PLAN_FILE), "--vehicle-profile", "quadplane_v1", "--output", str(out)]
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    parsed = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert parsed["vehicle_profile"] == "quadplane_v1"
    assert "FIXME" not in out.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI fail-closed lossy conversion contract
# ---------------------------------------------------------------------------


def _write_plan(tmp_path: Path, plan: dict[str, object]) -> Path:
    path = tmp_path / "input.plan"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


def _survey_plan() -> dict[str, object]:
    return _plan(
        [
            {"type": "ComplexItem", "complexItemType": "survey", "command": 16},
            _simple_item(16, coordinate=[52.001, 4.002, 120.0]),
        ]
    )


def test_convert_cli_survey_complex_item_fails_closed(tmp_path: Path) -> None:
    plan_file = _write_plan(tmp_path, _survey_plan())
    out = tmp_path / "mission.yaml"

    result = _runner.invoke(
        app,
        ["convert", str(plan_file), "--vehicle-profile", _VP, "--output", str(out)],
    )

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert not out.exists()
    assert "unsupported mission item type" in result.stderr
    assert "lossy conversion: 1 item(s) dropped" in result.stderr


def test_convert_cli_survey_complex_item_allow_lossy_converts(tmp_path: Path) -> None:
    plan_file = _write_plan(tmp_path, _survey_plan())
    out = tmp_path / "mission.yaml"

    result = _runner.invoke(
        app,
        [
            "convert",
            str(plan_file),
            "--vehicle-profile",
            _VP,
            "--allow-lossy",
            "--output",
            str(out),
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "Warning: item 0 (command 16): unsupported mission item type" in result.stderr
    assert "lossy conversion: 1 item(s) dropped" in result.stderr
    parsed = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert [item["action"] for item in parsed["route"]] == ["waypoint"]


def test_convert_cli_geofence_section_fails_closed(tmp_path: Path) -> None:
    plan = _plan([_simple_item(16, coordinate=[52.001, 4.002, 120.0])])
    plan["geoFence"] = {
        "circles": [],
        "polygons": [{"polygon": [[52.0, 4.0]]}],
        "version": 2,
    }
    plan_file = _write_plan(tmp_path, plan)

    result = _runner.invoke(app, ["convert", str(plan_file), "--vehicle-profile", _VP])

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert "section geoFence" in result.stderr
    assert "lossy conversion: 0 item(s) dropped, sections: geoFence" in result.stderr


def test_convert_cli_geofence_section_allow_lossy_prints_summary(tmp_path: Path) -> None:
    plan = _plan([_simple_item(16, coordinate=[52.001, 4.002, 120.0])])
    plan["geoFence"] = {
        "circles": [],
        "polygons": [{"polygon": [[52.0, 4.0]]}],
        "version": 2,
    }
    plan_file = _write_plan(tmp_path, plan)

    result = _runner.invoke(
        app, ["convert", str(plan_file), "--vehicle-profile", _VP, "--allow-lossy"]
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "lossy conversion: 0 item(s) dropped, sections: geoFence" in result.stderr
    parsed = yaml.safe_load(result.stdout)
    assert [item["action"] for item in parsed["route"]] == ["waypoint"]


def test_convert_cli_combined_losses_list_every_loss(tmp_path: Path) -> None:
    plan = _survey_plan()
    plan["geoFence"] = {
        "circles": [],
        "polygons": [{"polygon": [[52.0, 4.0]]}],
        "version": 2,
    }
    plan["rallyPoints"] = {"points": [[52.0, 4.0, 20.0]], "version": 2}
    plan_file = _write_plan(tmp_path, plan)

    result = _runner.invoke(app, ["convert", str(plan_file), "--vehicle-profile", _VP])

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert "Error: item 0 (command 16): unsupported mission item type" in result.stderr
    assert "Error: section geoFence" in result.stderr
    assert "Error: section rallyPoints" in result.stderr
    assert (
        "lossy conversion: 1 item(s) dropped, sections: geoFence, rallyPoints"
        in result.stderr
    )


def test_convert_cli_frame_10_imports_terrain_reference(tmp_path: Path) -> None:
    plan_file = _write_plan(
        tmp_path,
        _plan(
            [
                _simple_item(84, frame=10),
                _simple_item(16, frame=10, coordinate=[52.001, 4.002, 120.0]),
            ]
        ),
    )

    result = _runner.invoke(app, ["convert", str(plan_file), "--vehicle-profile", _VP])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "lossy conversion" not in result.stderr
    parsed = yaml.safe_load(result.stdout)
    assert parsed["defaults"]["altitude_reference"] == "terrain"


def test_convert_cli_unknown_frame_fails_closed(tmp_path: Path) -> None:
    plan_file = _write_plan(
        tmp_path, _plan([_simple_item(16, frame=5, coordinate=[52.001, 4.002, 120.0])])
    )

    result = _runner.invoke(app, ["convert", str(plan_file), "--vehicle-profile", _VP])

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert "unsupported altitude frame 5" in result.stderr
    assert "lossy conversion: 1 item(s) dropped" in result.stderr


def test_convert_cli_validate_only_lossy_fails_closed(tmp_path: Path) -> None:
    plan_file = _write_plan(tmp_path, _survey_plan())

    result = _runner.invoke(
        app, ["convert", str(plan_file), "--vehicle-profile", _VP, "--validate-only"]
    )

    assert result.exit_code == int(CliExitCode.UNSUPPORTED)
    assert "lossy conversion: 1 item(s) dropped" in result.stderr


def test_convert_cli_validate_only_allow_lossy_reports_and_passes(tmp_path: Path) -> None:
    plan_file = _write_plan(tmp_path, _survey_plan())

    result = _runner.invoke(
        app,
        [
            "convert",
            str(plan_file),
            "--vehicle-profile",
            _VP,
            "--validate-only",
            "--allow-lossy",
        ],
    )

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "OK" in result.stdout
    assert "lossy conversion: 1 item(s) dropped" in result.stderr
