"""Unit tests for LayeredWindProvider."""

import pytest

from estimator import LayeredWindProvider, WindLayer
from estimator.environment.wind import (
    ConstantWindProvider,
    TimedWindChange,
    TimeVaryingWindProvider,
)


def _wind_at(provider: LayeredWindProvider, altitude_m: float) -> tuple[float, float]:
    v = provider.wind_at(
        lat=0.0, lon=0.0, altitude_amsl_m=altitude_m, elapsed_time_s=0.0
    )
    return v.wind_east_mps, v.wind_north_mps


def test_single_layer_always_returns_that_layer() -> None:
    p = LayeredWindProvider(
        [WindLayer(altitude_m=0.0, wind_east_mps=3.0, wind_north_mps=1.0)]
    )
    assert _wind_at(p, 0.0) == (3.0, 1.0)
    assert _wind_at(p, 500.0) == (3.0, 1.0)
    assert _wind_at(p, 2000.0) == (3.0, 1.0)


def test_two_layers_returns_correct_layer_above_boundary() -> None:
    p = LayeredWindProvider(
        [
            WindLayer(altitude_m=0.0, wind_east_mps=2.0, wind_north_mps=0.0),
            WindLayer(altitude_m=1000.0, wind_east_mps=8.0, wind_north_mps=0.0),
        ]
    )
    assert _wind_at(p, 999.9) == (2.0, 0.0)
    assert _wind_at(p, 1000.0) == (8.0, 0.0)
    assert _wind_at(p, 2000.0) == (8.0, 0.0)


def test_query_below_all_layers_returns_lowest_layer() -> None:
    p = LayeredWindProvider(
        [
            WindLayer(altitude_m=500.0, wind_east_mps=5.0, wind_north_mps=0.0),
            WindLayer(altitude_m=1500.0, wind_east_mps=10.0, wind_north_mps=0.0),
        ]
    )
    assert _wind_at(p, 0.0) == (5.0, 0.0)
    assert _wind_at(p, 499.9) == (5.0, 0.0)


def test_three_layers_selects_matching_band() -> None:
    p = LayeredWindProvider(
        [
            WindLayer(altitude_m=0.0, wind_east_mps=1.0, wind_north_mps=0.0),
            WindLayer(altitude_m=500.0, wind_east_mps=5.0, wind_north_mps=0.0),
            WindLayer(altitude_m=1500.0, wind_east_mps=12.0, wind_north_mps=0.0),
        ]
    )
    assert _wind_at(p, 0.0)[0] == 1.0
    assert _wind_at(p, 499.0)[0] == 1.0
    assert _wind_at(p, 500.0)[0] == 5.0
    assert _wind_at(p, 1499.0)[0] == 5.0
    assert _wind_at(p, 1500.0)[0] == 12.0


def test_layers_can_be_provided_in_any_order() -> None:
    p = LayeredWindProvider(
        [
            WindLayer(altitude_m=1000.0, wind_east_mps=8.0, wind_north_mps=0.0),
            WindLayer(altitude_m=0.0, wind_east_mps=2.0, wind_north_mps=0.0),
        ]
    )
    assert _wind_at(p, 500.0) == (2.0, 0.0)
    assert _wind_at(p, 1500.0) == (8.0, 0.0)


def test_empty_layers_raises_value_error() -> None:
    with pytest.raises(ValueError, match="at least one layer"):
        LayeredWindProvider([])


def test_provider_id_is_layered() -> None:
    p = LayeredWindProvider(
        [WindLayer(altitude_m=0.0, wind_east_mps=0.0, wind_north_mps=0.0)]
    )
    assert p.provider_id == "layered"


def test_time_varying_provider_switches_by_elapsed_time() -> None:
    p = TimeVaryingWindProvider(
        ConstantWindProvider(0.0, 0.0),
        [
            TimedWindChange(
                effective_elapsed_time_s=10.0,
                provider=ConstantWindProvider(4.0, -1.0),
            )
        ],
    )

    before = p.wind_at(lat=0.0, lon=0.0, altitude_amsl_m=0.0, elapsed_time_s=9.9)
    after = p.wind_at(lat=0.0, lon=0.0, altitude_amsl_m=0.0, elapsed_time_s=10.0)

    assert (before.wind_east_mps, before.wind_north_mps) == (0.0, 0.0)
    assert (after.wind_east_mps, after.wind_north_mps) == (4.0, -1.0)
