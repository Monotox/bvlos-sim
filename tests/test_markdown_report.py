"""Focused tests for weather and ground-risk sections of the Markdown report."""

from adapters.markdown import _render_ground_risk, _render_weather_feasibility
from estimator.core.enums import FailureCode
from estimator.core.results import (
    GroundRiskEstimate,
    GroundRiskLegEstimate,
    WeatherEstimate,
    WeatherViolation,
)


def test_weather_section_omitted_when_block_absent() -> None:
    assert _render_weather_feasibility(None) == []


def test_weather_section_renders_summary_without_violations() -> None:
    weather = WeatherEstimate(
        is_feasible=True,
        checked_leg_count=4,
        max_wind_mps=10.0,
        worst_wind_speed_mps=2.0,
        worst_crosswind_mps=1.0,
    )
    lines = _render_weather_feasibility(weather)
    text = "\n".join(lines)
    assert "## Weather Feasibility" in text
    assert "- Feasible: `true`" in text
    assert "- Violations: `0`" in text
    # No violation table when there are no violations.
    assert "| Leg | ID | Limit |" not in text


def test_weather_section_renders_violation_table() -> None:
    weather = WeatherEstimate(
        is_feasible=False,
        checked_leg_count=2,
        max_wind_mps=8.0,
        worst_wind_speed_mps=12.0,
        worst_leg_index=1,
        worst_route_item_id="wp1",
        violations=[
            WeatherViolation(
                code=FailureCode.WIND_LIMIT_EXCEEDED,
                message="wind too high",
                leg_index=1,
                route_item_index=1,
                route_item_id="wp1",
                observed_mps=12.0,
                limit_mps=8.0,
            )
        ],
    )
    text = "\n".join(_render_weather_feasibility(weather))
    assert "- Feasible: `false`" in text
    assert "| Leg | ID | Limit |" in text
    assert "WIND_LIMIT_EXCEEDED" in text
    assert "12.00" in text


def test_ground_risk_section_omitted_when_block_absent() -> None:
    assert _render_ground_risk(None) == []


def test_ground_risk_section_renders_leg_table() -> None:
    ground_risk = GroundRiskEstimate(
        characteristic_dimension_m=1.5,
        mission_igrc=6,
        legs=[
            GroundRiskLegEstimate(
                leg_index=0,
                route_item_id="wp0",
                max_density_ppl_km2=120.0,
                igrc=5,
            )
        ],
    )
    text = "\n".join(_render_ground_risk(ground_risk))
    assert "## Ground Risk" in text
    assert "- Mission iGRC: `6`" in text
    assert "| Leg | ID | Max density ppl/km" in text
    assert "wp0" in text
