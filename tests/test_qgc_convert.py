import pytest

from adapters.qgc_plan import parse_qgc_plan


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
        )
    )

    assert diagnostics == []
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
    assert "constraints" not in mission


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
        )
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
        )
    )

    assert mission["route"] == [{"id": "rtl", "action": "rtl"}]
    assert len(diagnostics) == 1
    assert diagnostics[0].item_index == 0
    assert diagnostics[0].command == 16
    assert "unsupported mission item type" in diagnostics[0].message


def test_unknown_command_produces_diagnostic_and_item_is_skipped() -> None:
    mission, diagnostics = parse_qgc_plan(_plan([_simple_item(999)]))

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].item_index == 0
    assert diagnostics[0].command == 999
    assert "unsupported MAVLink command" in diagnostics[0].message


def test_invalid_waypoint_coordinate_produces_diagnostic() -> None:
    mission, diagnostics = parse_qgc_plan(
        _plan([_simple_item(16, coordinate=[52.001, "bad-lon", 120.0])])
    )

    assert mission["route"] == []
    assert len(diagnostics) == 1
    assert diagnostics[0].command == 16
    assert diagnostics[0].message == "waypoint coordinate missing or invalid"


def test_invalid_file_type_raises_value_error() -> None:
    plan = _plan([])
    plan["fileType"] = "Mission"

    with pytest.raises(ValueError, match="fileType"):
        parse_qgc_plan(plan)


def test_non_list_items_raises_value_error() -> None:
    plan = _plan([])
    mission = plan["mission"]
    assert isinstance(mission, dict)
    mission["items"] = "not-a-list"

    with pytest.raises(ValueError, match="mission.items"):
        parse_qgc_plan(plan)


def test_missing_planned_home_raises_value_error() -> None:
    with pytest.raises(ValueError, match="plannedHomePosition missing"):
        parse_qgc_plan({"fileType": "Plan", "mission": {"items": []}})


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
        )
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].message == "mission item is not an object; item skipped"
    assert mission["defaults"]["altitude_reference"] == "amsl"
