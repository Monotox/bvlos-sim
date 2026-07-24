from collections.abc import Callable
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import sys
from types import ModuleType

from types import SimpleNamespace

import pytest

from bvlos_sim.scripts import (
    _overpass,
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
    (
        fetch_obstacles,
        "requests",
        ["fetch-obstacles", "0", "1", "0", "1", "--base-altitude-amsl-m", "450"],
    ),
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
    [None, {"value": "bad"}, {"value": -1}, {"value": math.nan}],
)
def test_worldpop_malformed_samples_are_rejected(sample: object) -> None:
    with pytest.raises(ValueError):
        fetch_population._sample_value(sample)


@pytest.mark.parametrize("sample", [{}, {"value": None}, {"value": "NoData"}])
def test_worldpop_no_data_samples_are_detected(sample: object) -> None:
    assert fetch_population._sample_value(sample) is None


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


def _worldpop_requests(samples: list[object]) -> object:
    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {"samples": samples}

    class _Requests:
        @staticmethod
        def get(*args: object, **kwargs: object) -> _Response:
            return _Response()

    return _Requests()


def test_worldpop_water_cells_sample_as_zero_with_summary_warning(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    samples: list[object] = [{"value": None}, {"value": 2.5}, {"value": "NoData"}]
    monkeypatch.setattr(fetch_population, "requests", _worldpop_requests(samples))

    densities = fetch_population._sample_density(
        [(0.0, 0.0), (0.0, 1.0), (1.0, 0.0)]
    )

    assert densities == [0.0, 2.5, 0.0]
    assert "2 water/no-data cells" in capsys.readouterr().err


def test_worldpop_fail_on_missing_keeps_strict_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    samples: list[object] = [{"value": None}]
    monkeypatch.setattr(fetch_population, "requests", _worldpop_requests(samples))

    with pytest.raises(ValueError, match="no-data"):
        fetch_population._sample_density([(0.0, 0.0)], fail_on_missing=True)


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


@pytest.mark.parametrize(
    ("lat_min", "lat_max", "bound"),
    [(59.0, 61.0, "north of 60.0"), (-58.0, -56.5, "south of -56.0")],
)
def test_srtm_out_of_coverage_latitudes_are_rejected(
    lat_min: float, lat_max: float, bound: str
) -> None:
    with pytest.raises(ValueError, match=f"SRTM has no coverage {bound}"):
        fetch_terrain._sample_grid(lat_min, lat_max, 0.0, 1.0, 0.5)


def _wind_payload(hours: int = 24) -> dict[str, object]:
    start = datetime(2026, 1, 1)
    hourly: dict[str, object] = {
        "time": [
            (start + timedelta(hours=index)).isoformat(timespec="minutes")
            for index in range(hours)
        ]
    }
    for altitude_m in fetch_wind._ALTITUDES_M:
        hourly[f"wind_speed_{altitude_m}m"] = [5.0] * hours
        hourly[f"wind_direction_{altitude_m}m"] = [270.0] * hours
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


def test_open_meteo_midnight_crossing_window_builds_grid() -> None:
    grid = fetch_wind._build_grid(_wind_payload(hours=48), 52.0, 4.0, 23, 4)
    axes = grid["axes"]
    assert isinstance(axes, dict)
    assert axes["time_s"] == [0, 3600, 7200, 10800]


def test_open_meteo_short_response_for_midnight_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not cover"):
        fetch_wind._build_grid(_wind_payload(), 52.0, 4.0, 23, 2)


@pytest.mark.parametrize(
    ("end_hour", "expected_end_date"),
    [(24, "2026-03-01"), (27, "2026-03-02"), (49, "2026-03-03")],
)
def test_midnight_crossing_fetch_requests_following_days(
    end_hour: int,
    expected_end_date: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_params: dict[str, object] = {}

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return _wind_payload(hours=72)

    class _Requests:
        @staticmethod
        def get(url: str, **kwargs: object) -> _Response:
            params = kwargs["params"]
            assert isinstance(params, dict)
            captured_params.update(params)
            return _Response()

    monkeypatch.setattr(fetch_wind, "requests", _Requests())
    fetch_wind._fetch(52.0, 4.0, date(2026, 3, 1), end_hour=end_hour)

    assert captured_params["start_date"] == "2026-03-01"
    assert captured_params["end_date"] == expected_end_date


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


class _OverpassResponse:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    @staticmethod
    def json() -> dict[str, object]:
        return {"elements": []}


def test_overpass_retry_recovers_from_transient_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    attempts: list[str] = []

    class _Requests:
        @staticmethod
        def post(url: str, **kwargs: object) -> _OverpassResponse:
            attempts.append(url)
            if len(attempts) == 1:
                raise ConnectionError("connection reset")
            if len(attempts) == 2:
                return _OverpassResponse(status_code=504)
            return _OverpassResponse()

    monkeypatch.setattr(_overpass.time, "sleep", sleeps.append)
    monkeypatch.setattr(_overpass, "requests", _Requests())

    response = _overpass.post_with_retry(
        "https://overpass.test/api", data={}, headers={}, timeout=1
    )

    assert response.status_code == 200
    assert len(attempts) == 3
    assert sleeps == [2.0, 8.0]


def test_overpass_retry_exhaustion_names_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Requests:
        @staticmethod
        def post(url: str, **kwargs: object) -> _OverpassResponse:
            return _OverpassResponse(status_code=429)

    monkeypatch.setattr(_overpass.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(_overpass, "requests", _Requests())

    with pytest.raises(_overpass.OverpassError, match="3 attempts") as exc_info:
        _overpass.post_with_retry(
            "https://overpass.test/api", data={}, headers={}, timeout=1
        )

    assert "https://overpass.test/api" in str(exc_info.value)
    assert "HTTP 429" in str(exc_info.value)


def test_overpass_non_retryable_http_error_raises_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts: list[str] = []

    class _Requests:
        @staticmethod
        def post(url: str, **kwargs: object) -> _OverpassResponse:
            attempts.append(url)
            return _OverpassResponse(status_code=400)

    monkeypatch.setattr(_overpass.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(_overpass, "requests", _Requests())

    with pytest.raises(RuntimeError, match="HTTP 400"):
        _overpass.post_with_retry(
            "https://overpass.test/api", data={}, headers={}, timeout=1
        )

    assert len(attempts) == 1


@pytest.mark.parametrize(
    ("module", "query"),
    [
        (
            fetch_geofences,
            lambda: fetch_geofences._overpass_elements(0.0, 1.0, 0.0, 1.0),
        ),
        (
            fetch_landing_zones,
            lambda: fetch_landing_zones._query(0.0, 1.0, 0.0, 1.0),
        ),
        (
            fetch_obstacles,
            lambda: fetch_obstacles._query_overpass(
                lat_min=0.0, lat_max=1.0, lon_min=0.0, lon_max=1.0
            ),
        ),
    ],
)
def test_overpass_queries_use_shared_retry_helper(
    module: ModuleType,
    query: Callable[[], list[dict[str, object]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _post_with_retry(url: str, **kwargs: object) -> _OverpassResponse:
        captured["url"] = url
        return _OverpassResponse()

    monkeypatch.setattr(module, "requests", object())
    monkeypatch.setattr(_overpass, "post_with_retry", _post_with_retry)

    assert query() == []
    assert captured["url"] == module._OVERPASS_URL


def test_geofences_refuses_to_write_empty_airspace_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "geofences.geojson"
    monkeypatch.setattr(fetch_geofences, "requests", object())
    monkeypatch.setattr(fetch_geofences, "_overpass_elements", lambda *args: [])
    monkeypatch.setattr(
        sys, "argv", ["fetch-geofences", "0", "1", "0", "1", "--output", str(output)]
    )

    with pytest.raises(SystemExit) as exc_info:
        fetch_geofences.main()

    message = str(exc_info.value.code)
    assert "relation-based" in message
    assert "--source openaip" in message
    assert not output.exists()


def test_geofences_allow_empty_writes_empty_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    output = tmp_path / "geofences.geojson"
    monkeypatch.setattr(fetch_geofences, "requests", object())
    monkeypatch.setattr(fetch_geofences, "_overpass_elements", lambda *args: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fetch-geofences",
            "0",
            "1",
            "0",
            "1",
            "--allow-empty",
            "--output",
            str(output),
        ],
    )

    fetch_geofences.main()

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == {"type": "FeatureCollection", "features": []}


def test_obstacles_base_altitude_flag_is_required(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["fetch-obstacles", "0", "1", "0", "1"])

    with pytest.raises(SystemExit) as exc_info:
        fetch_obstacles.main()

    assert exc_info.value.code == 2
    assert "--base-altitude-amsl-m" in capsys.readouterr().err


def test_terrain_void_policy_interpolates_instead_of_aborting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single SRTM void aborted the whole fetch and left nothing behind."""

    class _Voids:
        def get_elevation(self, lat: float, lon: float):
            # One hole in the middle of otherwise good coverage.
            if abs(lat - 52.001) < 1e-9 and abs(lon - 4.001) < 1e-9:
                return None
            return 100.0

    monkeypatch.setattr(fetch_terrain, "srtm", SimpleNamespace(get_data=_Voids))

    with pytest.raises(ValueError, match="SRTM coverage missing"):
        fetch_terrain._sample_grid(52.0, 52.002, 4.0, 4.002, 0.001)

    _lats, _lons, rows = fetch_terrain._sample_grid(
        52.0, 52.002, 4.0, 4.002, 0.001, void_policy="interpolate"
    )

    values = [value for row in rows for value in row]
    assert all(value == 100.0 for value in values)
    # A void must never be written as sea level.
    assert 0.0 not in values
