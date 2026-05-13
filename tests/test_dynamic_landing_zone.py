"""Tests for dynamic landing-zone availability (Ticket 035)."""

import pytest

from estimator import (
    EstimateStatus,
    FailureCode,
    LandingZone,
    try_estimate_mission_distance_time,
)
from estimator.execution.scenario import run_scenario
from schemas.scenario import ScenarioPlan
from tests.helpers import make_mission, make_vehicle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point_zone(zone_id: str, *, lat: float, lon: float) -> LandingZone:
    return LandingZone.model_validate(
        {
            "id": zone_id,
            "geometry": {"points": [{"lat": lat, "lon": lon}]},
        }
    )


def _scenario(
    *,
    mission_file: str = "mission.yaml",
    events: list[dict] | None = None,
    assertions: list[dict] | None = None,
) -> ScenarioPlan:
    return ScenarioPlan.model_validate(
        {
            "schema_version": "scenario.v1",
            "scenario_id": "lz-avail-test",
            "mission_file": mission_file,
            "vehicle_file": "vehicle.yaml",
            "initial_conditions": {
                "wind_east_mps": 0.0,
                "wind_north_mps": 0.0,
            },
            "events": events or [],
            "assertions": assertions or [],
        }
    )


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_landing_zone_unavailable_event_schema_parses() -> None:
    plan = _scenario(
        events=[
            {
                "event_id": "close-lz",
                "kind": "landing_zone_unavailable",
                "trigger": "at_mission_start",
                "unavailable_zone_ids": ["lz1"],
            }
        ]
    )
    event = plan.events[0]
    assert event.kind.value == "landing_zone_unavailable"
    assert event.unavailable_zone_ids == ["lz1"]


def test_landing_zone_unavailable_event_rejects_empty_ids() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="at least one zone id"):
        _scenario(
            events=[
                {
                    "event_id": "close-lz",
                    "kind": "landing_zone_unavailable",
                    "trigger": "at_mission_start",
                    "unavailable_zone_ids": [],
                }
            ]
        )


def test_landing_zone_unavailable_event_rejects_missing_ids() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="unavailable_zone_ids is required"):
        _scenario(
            events=[
                {
                    "event_id": "close-lz",
                    "kind": "landing_zone_unavailable",
                    "trigger": "at_mission_start",
                }
            ]
        )


def test_unavailable_zone_ids_rejected_on_non_lz_event() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="only valid for landing_zone_unavailable"):
        _scenario(
            events=[
                {
                    "event_id": "obs",
                    "kind": "observe",
                    "trigger": "at_mission_start",
                    "unavailable_zone_ids": ["lz1"],
                }
            ]
        )


# ---------------------------------------------------------------------------
# Estimator direct API: lz_unavailability parameter
# ---------------------------------------------------------------------------


def test_lz_unavailability_none_leaves_behavior_unchanged() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
        lz_unavailability=None,
    )

    assert result.status == EstimateStatus.SUCCESS
    assert result.landing_zone is not None
    assert result.landing_zone.is_feasible is True
    assert result.landing_zone.unavailable_zone_ids == []
    assert result.landing_zone.states[0].available_zone_count is None


def test_lz_unavailability_all_zones_unavailable_at_all_states() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    n_legs = len(
        try_estimate_mission_distance_time(mission, make_vehicle(), landing_zones=[zone]).legs
    )
    schedule = [frozenset({"lz1"})] * n_legs

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
        lz_unavailability=schedule,
    )

    assert result.status == EstimateStatus.INFEASIBLE
    assert result.failure is not None
    assert result.failure.code == FailureCode.ALL_LANDING_ZONES_UNAVAILABLE
    assert result.landing_zone is not None
    assert result.landing_zone.is_feasible is False
    assert result.landing_zone.unavailable_zone_ids == ["lz1"]
    assert result.landing_zone.states[0].available_zone_count == 0


def test_lz_unavailability_partial_makes_nearest_unavailable() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone_near = _point_zone("near", lat=52.001, lon=4.002)
    zone_far = _point_zone("far", lat=52.002, lon=4.003)

    n_legs = len(
        try_estimate_mission_distance_time(
            mission, make_vehicle(), landing_zones=[zone_near, zone_far]
        ).legs
    )
    schedule = [frozenset({"near"})] * n_legs

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone_near, zone_far],
        lz_unavailability=schedule,
    )

    assert result.landing_zone is not None
    assert result.landing_zone.unavailable_zone_ids == ["near"]
    assert result.landing_zone.states[0].available_zone_count == 1
    # "near" is excluded; "far" is now the nearest available zone
    assert result.landing_zone.states[0].nearest_zone_id == "far"
    assert result.landing_zone.states[0].reachable_zone_id == "far"


def test_lz_unavailability_partial_schedule_affects_only_later_states() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    full_result = try_estimate_mission_distance_time(
        mission, make_vehicle(), landing_zones=[zone]
    )
    n_legs = len(full_result.legs)
    assert n_legs >= 1

    schedule = [frozenset() if i == 0 else frozenset({"lz1"}) for i in range(n_legs)]

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
        lz_unavailability=schedule,
    )

    assert result.landing_zone is not None
    assert result.landing_zone.states[0].available_zone_count == 1
    if n_legs > 1:
        assert result.landing_zone.states[1].available_zone_count == 0


def test_result_validity_scope_full_mission_when_all_zones_unavailable() -> None:
    from pathlib import Path as _Path

    from adapters.envelope import EnvelopeInputs, build_estimator_envelope
    from adapters.io import InputDocument

    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    n_legs = len(
        try_estimate_mission_distance_time(mission, make_vehicle(), landing_zones=[zone]).legs
    )
    schedule = [frozenset({"lz1"})] * n_legs

    result = try_estimate_mission_distance_time(
        mission,
        make_vehicle(),
        landing_zones=[zone],
        lz_unavailability=schedule,
    )

    # ALL_LANDING_ZONES_UNAVAILABLE: the full route was evaluated (feasibility verdict,
    # not missing data). result_validity must report scope=full_mission and is_complete=True.
    fake_doc = InputDocument(path=_Path("/fake/x.yaml"), format="yaml", sha256="0" * 64)
    envelope = build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(mission=fake_doc, vehicle=fake_doc),
    )
    assert envelope.result_validity.scope == "full_mission"
    assert envelope.result_validity.is_complete is True
    assert envelope.result_validity.is_valid_for_full_mission is True


# ---------------------------------------------------------------------------
# Scenario runner: landing_zone_unavailable events
# ---------------------------------------------------------------------------


def test_scenario_lz_unavailable_event_at_mission_start_makes_zone_infeasible() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    plan = _scenario(
        events=[
            {
                "event_id": "close-lz",
                "kind": "landing_zone_unavailable",
                "trigger": "at_mission_start",
                "unavailable_zone_ids": ["lz1"],
            }
        ],
        assertions=[{"assertion_id": "lz-fails", "kind": "estimate_fails"}],
    )

    result = run_scenario(plan, mission, make_vehicle(), landing_zones=[zone])

    assert result.estimate is not None
    assert result.estimate.status == EstimateStatus.INFEASIBLE
    assert result.estimate.failure is not None
    assert result.estimate.failure.code == FailureCode.ALL_LANDING_ZONES_UNAVAILABLE
    assert result.estimate.landing_zone is not None
    assert result.estimate.landing_zone.unavailable_zone_ids == ["lz1"]
    assert result.estimate.metadata.get("scenario_lz_unavailability_event_count") == 1


def test_scenario_lz_unavailable_event_does_not_fire_without_landing_zones() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]

    plan = _scenario(
        events=[
            {
                "event_id": "close-lz",
                "kind": "landing_zone_unavailable",
                "trigger": "at_mission_start",
                "unavailable_zone_ids": ["lz1"],
            }
        ],
        assertions=[{"assertion_id": "ok", "kind": "estimate_succeeds"}],
    )

    result = run_scenario(plan, mission, make_vehicle(), landing_zones=None)

    assert result.estimate is not None
    assert result.estimate.status == EstimateStatus.SUCCESS
    assert result.estimate.landing_zone is None


def test_scenario_static_lz_unchanged_without_availability_events() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    plan = _scenario(
        events=[
            {
                "event_id": "obs",
                "kind": "observe",
                "trigger": "at_mission_start",
            }
        ],
        assertions=[{"assertion_id": "lz-ok", "kind": "estimate_succeeds"}],
    )

    result = run_scenario(plan, mission, make_vehicle(), landing_zones=[zone])

    assert result.estimate is not None
    assert result.estimate.status == EstimateStatus.SUCCESS
    assert result.estimate.landing_zone is not None
    assert result.estimate.landing_zone.is_feasible is True
    assert result.estimate.landing_zone.unavailable_zone_ids == []
    assert "scenario_lz_unavailability_event_count" not in result.estimate.metadata


def test_scenario_lz_unavailable_combined_with_wind_change() -> None:
    mission = make_mission()
    mission.route = [mission.route[1]]
    zone = _point_zone("lz1", lat=52.001, lon=4.002)

    plan = _scenario(
        events=[
            {
                "event_id": "wind",
                "kind": "wind_change",
                "trigger": "at_mission_start",
                "wind_east_mps": 2.0,
                "wind_north_mps": 0.0,
            },
            {
                "event_id": "close-lz",
                "kind": "landing_zone_unavailable",
                "trigger": "at_mission_start",
                "unavailable_zone_ids": ["lz1"],
            },
        ],
        assertions=[{"assertion_id": "lz-fails", "kind": "estimate_fails"}],
    )

    result = run_scenario(plan, mission, make_vehicle(), landing_zones=[zone])

    assert result.estimate is not None
    assert result.estimate.failure is not None
    assert result.estimate.failure.code == FailureCode.ALL_LANDING_ZONES_UNAVAILABLE
    assert result.estimate.metadata.get("scenario_lz_unavailability_event_count") == 1
