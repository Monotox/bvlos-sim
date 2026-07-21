from datetime import datetime, timedelta
import math
import sys
from types import ModuleType

import pytest

from scripts import (
    fetch_all,
    fetch_geofences,
    fetch_landing_zones,
    fetch_obstacles,
    fetch_population,
    fetch_terrain,
    fetch_wind,
)


_FETCH_ENTRYPOINTS: tuple[tuple[ModuleType, str, list[str]], ...] = (
    (fetch_all, "_requests", ["fetch-all", "0", "0"]),
    (fetch_geofences, "requests", ["fetch-geofences", "0", "1", "0", "1"]),
    (
        fetch_landing_zones,
        "requests",
        ["fetch-landing-zones", "0", "1", "0", "1"],
    ),
    (fetch_obstacles, "requests", ["fetch-obstacles", "0", "1", "0", "1"]),
    (
        fetch_population,
        "requests",
        ["fetch-population", "0", "1", "0", "1", "1"],
    ),
    (fetch_terrain, "srtm", ["fetch-terrain", "0", "1", "0", "1", "1"]),
    (fetch_wind, "requests", ["fetch-wind", "0", "0"]),
)


@pytest.mark.parametrize(("module", "dependency", "argv"), _FETCH_ENTRYPOINTS)
def test_fetch_entrypoint_help_works_without_optional_dependencies(
    module: ModuleType,
    dependency: str,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, dependency, None)
    monkeypatch.setattr(sys, "argv", [argv[0], "--help"])

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert exc_info.value.code == 0


@pytest.mark.parametrize(("module", "dependency", "argv"), _FETCH_ENTRYPOINTS)
def test_fetch_entrypoint_missing_dependency_has_wheel_install_guidance(
    module: ModuleType,
    dependency: str,
    argv: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, dependency, None)
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(SystemExit) as exc_info:
        module.main()

    assert "pip install 'bvlos-sim[scripts]'" in str(exc_info.value.code)


@pytest.mark.parametrize(
    "sample",
    [None, {}, {"value": None}, {"value": "bad"}, {"value": -1}, {"value": math.nan}],
)
def test_worldpop_malformed_samples_are_rejected(sample: object) -> None:
    with pytest.raises(ValueError):
        fetch_population._sample_value(sample)


def test_worldpop_nondivisible_axis_is_rejected() -> None:
    with pytest.raises(ValueError, match="divide"):
        fetch_population._axis(0.0, 1.0, 0.3)


def test_worldpop_partial_batch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"samples": [{"value": 1.0}]}

    class _Requests:
        @staticmethod
        def get(*args, **kwargs) -> _Response:
            return _Response()

    monkeypatch.setattr(fetch_population, "requests", _Requests())
    with pytest.raises(ValueError, match="partial coverage"):
        fetch_population._sample_density([(0.0, 0.0), (0.0, 1.0)])


def test_worldpop_requests_explicit_annual_slice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_params: dict[str, object] = {}

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"samples": [{"value": 1.0}]}

    class _Requests:
        @staticmethod
        def get(*args, **kwargs) -> _Response:
            captured_params.update(kwargs["params"])
            return _Response()

    monkeypatch.setattr(fetch_population, "requests", _Requests())
    fetch_population._sample_density([(0.0, 0.0)], year=2020)

    assert captured_params["time"] == "1577836800000"


@pytest.mark.parametrize("year", [1999, 2021])
def test_worldpop_rejects_unavailable_year(year: int) -> None:
    with pytest.raises(ValueError, match="between 2000 and 2020"):
        fetch_population._year_epoch_ms(year)


def test_srtm_missing_elevation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _ElevationData:
        @staticmethod
        def get_elevation(lat: float, lon: float) -> None:
            return None

    class _Srtm:
        @staticmethod
        def get_data() -> _ElevationData:
            return _ElevationData()

    monkeypatch.setattr(fetch_terrain, "srtm", _Srtm())
    with pytest.raises(ValueError, match="coverage missing"):
        fetch_terrain._sample_grid(0.0, 1.0, 0.0, 1.0, 1.0)


def _wind_payload() -> dict[str, object]:
    start = datetime(2026, 1, 1)
    hourly: dict[str, object] = {
        "time": [
            (start + timedelta(hours=index)).isoformat(timespec="minutes")
            for index in range(24)
        ]
    }
    for altitude_m in fetch_wind._ALTITUDES_M:
        hourly[f"wind_speed_{altitude_m}m"] = [5.0] * 24
        hourly[f"wind_direction_{altitude_m}m"] = [270.0] * 24
    return {"elevation": 100.0, "hourly": hourly}


def test_open_meteo_missing_series_is_rejected() -> None:
    payload = _wind_payload()
    hourly = payload["hourly"]
    assert isinstance(hourly, dict)
    del hourly["wind_speed_10m"]
    with pytest.raises(ValueError, match="missing hourly series"):
        fetch_wind._build_grid(payload, 52.0, 4.0, 0, 4)


def test_past_wind_uses_historical_forecast_vertical_levels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_url = ""

    class _Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return _wind_payload()

    class _Requests:
        @staticmethod
        def get(url: str, **kwargs) -> _Response:
            nonlocal captured_url
            captured_url = url
            return _Response()

    monkeypatch.setattr(fetch_wind, "requests", _Requests())
    fetch_wind._fetch(52.0, 4.0, datetime.now().date() - timedelta(days=1))

    assert captured_url == fetch_wind._HISTORICAL_FORECAST_URL


def test_wind_before_historical_forecast_vertical_coverage_is_rejected() -> None:
    with pytest.raises(ValueError, match="unavailable before 2022-01-01"):
        fetch_wind._fetch(52.0, 4.0, datetime(2021, 12, 31).date())


@pytest.mark.parametrize("invalid_speed", [None, "bad", -1.0, math.inf])
def test_open_meteo_invalid_wind_value_is_rejected(invalid_speed: object) -> None:
    payload = _wind_payload()
    hourly = payload["hourly"]
    assert isinstance(hourly, dict)
    speeds = hourly["wind_speed_10m"]
    assert isinstance(speeds, list)
    speeds[0] = invalid_speed
    with pytest.raises(ValueError):
        fetch_wind._build_grid(payload, 52.0, 4.0, 0, 4)


def test_open_meteo_partial_day_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="beyond"):
        fetch_wind._build_grid(_wind_payload(), 52.0, 4.0, 23, 2)


def test_open_meteo_single_sample_grid_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least two"):
        fetch_wind._build_grid(_wind_payload(), 52.0, 4.0, 3, 1)


def test_fetchers_reject_out_of_range_grid_coordinates() -> None:
    with pytest.raises(ValueError, match="latitude bounds"):
        fetch_terrain._sample_grid(-91.0, -90.0, 0.0, 1.0, 1.0)
    with pytest.raises(ValueError, match="longitude bounds"):
        fetch_population._sample_grid(0.0, 1.0, 179.5, 180.5, 0.5)
    with pytest.raises(ValueError, match="leave room"):
        fetch_wind._build_grid(_wind_payload(), 90.0, 4.0, 0, 4)


def test_open_meteo_complete_valid_window_builds_grid() -> None:
    grid = fetch_wind._build_grid(_wind_payload(), 52.0, 4.0, 3, 4)
    axes = grid["axes"]
    assert isinstance(axes, dict)
    assert axes["time_s"] == [0, 3600, 7200, 10800]
    assert axes["altitude_m"] == [110.0, 180.0, 220.0, 280.0]
    assert axes["lat"] == [51.999999, 52.000001]
    assert axes["lon"] == [3.999999, 4.000001]


def test_open_meteo_missing_surface_elevation_is_rejected() -> None:
    payload = _wind_payload()
    del payload["elevation"]
    with pytest.raises(ValueError, match="elevation"):
        fetch_wind._build_grid(payload, 52.0, 4.0, 0, 4)
