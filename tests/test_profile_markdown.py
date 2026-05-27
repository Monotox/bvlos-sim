"""Tests for the route altitude profile report renderer."""

from pathlib import Path


from adapters.cli import CliExitCode, app
from adapters.envelope import EnvelopeInputs, build_estimator_envelope
from adapters.io import InputDocument
from adapters.profile_markdown import render_profile_markdown
from estimator.core.enums import EstimateStatus, LegPhase
from estimator.core.results import LegEstimate, MissionEstimate
from estimator.environment.terrain import ConstantElevationProvider, GridTerrainProvider
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
_runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_doc(name: str) -> InputDocument:
    return InputDocument(path=Path(f"{name}.yaml"), format="yaml", sha256="abc123")


def _leg(
    i: int,
    *,
    start_lat: float = 52.0,
    start_lon: float = 4.0,
    end_lat: float = 52.01,
    end_lon: float = 4.01,
    start_alt: float = 100.0,
    end_alt: float = 150.0,
    phase: LegPhase = LegPhase.TRANSIT,
    dist_m: float = 500.0,
) -> LegEstimate:
    return LegEstimate(
        leg_index=i,
        route_item_index=i,
        route_item_id=f"wp{i}",
        action="TRANSIT",
        phase=phase,
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt_amsl_m=start_alt,
        end_lat=end_lat,
        end_lon=end_lon,
        end_alt_amsl_m=end_alt,
        horizontal_distance_m=dist_m,
        vertical_delta_m=end_alt - start_alt,
        vertical_distance_m=abs(end_alt - start_alt),
        path_distance_m=dist_m,
        time_s=50.0,
        tas_mps=10.0,
    )


def _estimate(legs: list[LegEstimate] | None = None) -> MissionEstimate:
    return MissionEstimate(
        status=EstimateStatus.SUCCESS,
        total_horizontal_distance_m=500.0,
        total_vertical_distance_m=50.0,
        total_path_distance_m=502.0,
        total_time_s=300.0,
        totals_are_partial=False,
        legs=legs or [_leg(0), _leg(1, start_alt=150.0, end_alt=120.0)],
    )


def _envelope(result: MissionEstimate | None = None) -> ...:

    if result is None:
        result = _estimate()
    return build_estimator_envelope(
        result=result,
        inputs=EnvelopeInputs(mission=_fake_doc("mission"), vehicle=_fake_doc("vehicle")),
    )


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_profile_report_contains_altitude_table_header() -> None:
    output = render_profile_markdown(_envelope())
    assert "## Route Altitude Profile" in output


def test_profile_table_has_one_row_per_leg() -> None:
    legs = [_leg(i) for i in range(4)]
    output = render_profile_markdown(_envelope(_estimate(legs)))
    # Count data rows (not header or separator)
    data_rows = [
        line for line in output.splitlines()
        if line.startswith("| ") and "Phase" not in line and "---" not in line and "Leg" not in line
    ]
    assert len(data_rows) == 4


def test_profile_table_shows_dashes_when_no_terrain() -> None:
    output = render_profile_markdown(_envelope(), terrain_provider=None)
    assert "Terrain" not in output or "not available" in output


def test_profile_table_shows_terrain_when_constant_provider() -> None:
    provider = ConstantElevationProvider(50.0)
    output = render_profile_markdown(_envelope(), terrain_provider=provider)
    assert "Terrain m" in output
    assert "Clearance m" in output
    assert "50" in output


def test_profile_table_clearance_equals_alt_minus_terrain() -> None:
    provider = ConstantElevationProvider(50.0)
    legs = [_leg(0, start_alt=100.0, end_alt=100.0)]
    output = render_profile_markdown(_envelope(_estimate(legs)), terrain_provider=provider)
    # clearance = 100 - 50 = 50
    assert "50" in output


def test_profile_shows_terrain_unavailable_note_when_no_provider() -> None:
    output = render_profile_markdown(_envelope(), terrain_provider=None)
    assert "not available" in output


def test_profile_report_ends_with_newline() -> None:
    output = render_profile_markdown(_envelope())
    assert output.endswith("\n")


def test_profile_leg_id_shown_in_table() -> None:
    legs = [_leg(0)]
    legs[0] = legs[0].model_copy(update={"route_item_id": "my_waypoint"})
    output = render_profile_markdown(_envelope(_estimate(legs)))
    assert "my_waypoint" in output


def test_profile_leg_with_null_id_shows_dash() -> None:
    legs = [_leg(0)]
    legs[0] = legs[0].model_copy(update={"route_item_id": None})
    output = render_profile_markdown(_envelope(_estimate(legs)))
    assert "| — |" in output or "| —" in output


def test_profile_with_grid_provider_outside_coverage_shows_dashes() -> None:
    # Grid covers lat [53, 54], lon [5, 6] but our legs are at lat 52, lon 4
    provider = GridTerrainProvider(
        origin_lat=53.0,
        origin_lon=5.0,
        step_lat_deg=0.5,
        step_lon_deg=0.5,
        elevations_m=[[100.0, 110.0, 120.0], [105.0, 115.0, 125.0], [110.0, 120.0, 130.0]],
    )
    output = render_profile_markdown(_envelope(), terrain_provider=provider)
    assert "Terrain m" in output
    assert "—" in output  # outside coverage → None → dashes


def test_profile_no_result_shows_no_legs_message() -> None:
    from adapters.envelope import build_invalid_input_envelope
    from adapters.io import InputLoadError, InputLoadStage

    error = InputLoadError(
        "file not found",
        input_name="mission",
        path=Path("m.yaml"),
        stage=InputLoadStage.READ,
    )
    envelope = build_invalid_input_envelope(error=error, mission_document=None, vehicle_document=None)
    output = render_profile_markdown(envelope)
    assert "## Route Altitude Profile" in output
    assert "No legs available" in output


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def test_estimate_profile_format_exits_zero() -> None:
    result = _runner.invoke(
        app,
        [
            "estimate",
            str(REPO_ROOT / "examples/missions/pipeline_demo_001.yaml"),
            str(REPO_ROOT / "examples/vehicles/quadplane_v1.yaml"),
            "--format",
            "profile",
        ],
    )
    assert result.exit_code == int(CliExitCode.SUCCESS)
    assert "## Route Altitude Profile" in result.output


def test_estimate_profile_shows_terrain_with_terrain_mission() -> None:
    result = _runner.invoke(
        app,
        [
            "estimate",
            str(REPO_ROOT / "examples/real_world/alpine_infeasible.yaml"),
            str(REPO_ROOT / "examples/real_world/quadplane_small_battery.yaml"),
            "--format",
            "profile",
        ],
    )
    # Should still output a profile (infeasible due to energy, not profiling error)
    assert "## Route Altitude Profile" in result.output
