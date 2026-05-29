import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from adapters.cli import CliExitCode, app
from adapters.qgc_export import build_qgc_plan, render_qgc_plan
from adapters.qgc_plan import load_and_convert_plan
from schemas.mission import MissionPlan
from tests.helpers import make_mission_payload

_RUNNER = CliRunner()
_EXAMPLE_MISSION = "examples/missions/pipeline_demo_001.yaml"


def _all_actions_payload() -> dict:
    payload = make_mission_payload()
    payload["route"] = [
        {"id": "takeoff", "action": "vtol_takeoff", "altitude_m": 80.0},
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
        {"id": "land", "action": "land", "lat": 52.003, "lon": 4.006},
        {"id": "rtl", "action": "rtl"},
    ]
    return payload


def _mission(payload: dict) -> MissionPlan:
    return MissionPlan.model_validate(payload)


def test_build_qgc_plan_has_required_top_level_structure() -> None:
    plan, _ = build_qgc_plan(_mission(make_mission_payload()))

    assert plan["fileType"] == "Plan"
    assert plan["groundStation"] == "bvlos-sim"
    assert plan["version"] == 1
    mission = plan["mission"]
    assert mission["plannedHomePosition"] == [52.0, 4.0, 12.0]
    assert mission["cruiseSpeed"] == 18.0
    assert mission["hoverSpeed"] == 5.0


def test_all_action_types_map_to_expected_commands() -> None:
    plan, _ = build_qgc_plan(_mission(_all_actions_payload()))

    commands = [item["command"] for item in plan["mission"]["items"]]
    assert commands == [84, 16, 19, 21, 20]
    do_jump_ids = [item["doJumpId"] for item in plan["mission"]["items"]]
    assert do_jump_ids == [1, 2, 3, 4, 5]


def test_waypoint_params_carry_coordinate_and_acceptance_radius() -> None:
    plan, _ = build_qgc_plan(_mission(_all_actions_payload()))

    waypoint = plan["mission"]["items"][1]
    assert waypoint["coordinate"] == [52.001, 4.002, 120.0]
    assert waypoint["params"][1] == 20.0
    assert waypoint["params"][4:7] == [52.001, 4.002, 120.0]


def test_loiter_params_carry_time_and_radius() -> None:
    plan, _ = build_qgc_plan(_mission(_all_actions_payload()))

    loiter = plan["mission"]["items"][2]
    assert loiter["params"][0] == 60.0
    assert loiter["params"][2] == 80.0


def test_amsl_reference_uses_global_frame() -> None:
    payload = make_mission_payload()
    payload["defaults"]["altitude_reference"] = "amsl"
    plan, diagnostics = build_qgc_plan(_mission(payload))

    waypoint = next(item for item in plan["mission"]["items"] if item["command"] == 16)
    assert waypoint["frame"] == 0
    assert waypoint["AltitudeMode"] == 2
    assert diagnostics  # constraints/assets omitted note still present


def test_terrain_reference_emits_diagnostic_and_uses_relative_frame() -> None:
    payload = make_mission_payload()
    payload["defaults"]["altitude_reference"] = "terrain"
    plan, diagnostics = build_qgc_plan(_mission(payload))

    waypoint = next(item for item in plan["mission"]["items"] if item["command"] == 16)
    assert waypoint["frame"] == 3
    assert any(
        "terrain" in diagnostic.message and diagnostic.route_item_id is not None
        for diagnostic in diagnostics
    )


def test_constraints_and_assets_emit_omission_note() -> None:
    _, diagnostics = build_qgc_plan(_mission(make_mission_payload()))

    assert any(
        diagnostic.route_item_id is None and "omitted" in diagnostic.message
        for diagnostic in diagnostics
    )


def test_render_qgc_plan_is_valid_json() -> None:
    plan, _ = build_qgc_plan(_mission(make_mission_payload()))
    rendered = render_qgc_plan(plan)

    assert rendered.endswith("\n")
    assert json.loads(rendered)["fileType"] == "Plan"


def test_export_cli_emits_valid_json(tmp_path: Path) -> None:
    result = _RUNNER.invoke(app, ["export", _EXAMPLE_MISSION])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert json.loads(result.stdout)["fileType"] == "Plan"


def test_export_round_trips_through_convert(tmp_path: Path) -> None:
    result = _RUNNER.invoke(app, ["export", _EXAMPLE_MISSION])
    assert result.exit_code == int(CliExitCode.SUCCESS)

    plan_path = tmp_path / "exported.plan"
    plan_path.write_text(result.stdout, encoding="utf-8")

    mission, diagnostics = load_and_convert_plan(plan_path, vehicle_profile="quadplane_v1")

    assert diagnostics == []
    original = yaml.safe_load(Path(_EXAMPLE_MISSION).read_text(encoding="utf-8"))
    assert len(mission["route"]) == len(original["route"])

    def _coords(route: list[dict]) -> list[tuple[float, float]]:
        return [
            (item["lat"], item["lon"])
            for item in route
            if item.get("lat") is not None and item.get("lon") is not None
        ]

    assert _coords(mission["route"]) == _coords(original["route"])


def test_export_validate_only_writes_no_output(tmp_path: Path) -> None:
    result = _RUNNER.invoke(app, ["export", _EXAMPLE_MISSION, "--validate-only"])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "OK" in result.stdout
    assert "fileType" not in result.stdout


def test_export_writes_output_file(tmp_path: Path) -> None:
    out = tmp_path / "mission.plan"
    result = _RUNNER.invoke(app, ["export", _EXAMPLE_MISSION, "--output", str(out)])

    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert json.loads(out.read_text(encoding="utf-8"))["mission"]["items"]


def test_export_invalid_mission_exits_invalid_input(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("mission_id: 1\n", encoding="utf-8")

    result = _RUNNER.invoke(app, ["export", str(bad)])

    assert result.exit_code == int(CliExitCode.INVALID_INPUT)
