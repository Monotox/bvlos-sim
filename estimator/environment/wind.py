"""Wind provider abstractions."""

import bisect
from dataclasses import dataclass
from typing import Protocol

from estimator.core.results import WindVector


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _interp_index(axis: tuple[float, ...], value: float) -> tuple[int, float]:
    """Return (lower_index, fraction) for linear interpolation along a sorted axis.

    Clamps: lower_index stays in [0, len-2] and fraction stays in [0.0, 1.0]
    so out-of-bounds queries extrapolate from the nearest edge cell.
    """
    i = bisect.bisect_right(axis, value) - 1
    i0 = max(0, min(i, len(axis) - 2))
    t = (value - axis[i0]) / (axis[i0 + 1] - axis[i0])
    return i0, max(0.0, min(1.0, t))


class WindProvider(Protocol):
    provider_id: str

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        """Return wind vector at a spatiotemporal point."""


class ConstantWindProvider:
    """Provider returning a fixed EN wind vector."""

    provider_id = "constant"

    def __init__(self, wind_east_mps: float, wind_north_mps: float) -> None:
        self.wind_east_mps = float(wind_east_mps)
        self.wind_north_mps = float(wind_north_mps)

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        return WindVector(
            wind_east_mps=self.wind_east_mps,
            wind_north_mps=self.wind_north_mps,
        )


@dataclass(frozen=True)
class WindLayer:
    """A constant wind layer active from `altitude_m` upward."""

    altitude_m: float
    wind_east_mps: float
    wind_north_mps: float


class LayeredWindProvider:
    """Provider returning wind from stacked altitude layers.

    Each layer is active from its `altitude_m` upward to the next layer.
    Queries below the lowest layer's altitude return the lowest layer's wind.
    """

    provider_id = "layered"

    def __init__(self, layers: list[WindLayer]) -> None:
        if not layers:
            raise ValueError("LayeredWindProvider requires at least one layer.")
        self._layers: tuple[WindLayer, ...] = tuple(
            sorted(layers, key=lambda la: la.altitude_m, reverse=True)
        )

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        for layer in self._layers:
            if altitude_amsl_m >= layer.altitude_m:
                return WindVector(
                    wind_east_mps=layer.wind_east_mps,
                    wind_north_mps=layer.wind_north_mps,
                )
        lowest = self._layers[-1]
        return WindVector(
            wind_east_mps=lowest.wind_east_mps,
            wind_north_mps=lowest.wind_north_mps,
        )


@dataclass(frozen=True)
class TimedWindChange:
    """Wind provider replacement effective from an elapsed mission time onward."""

    effective_elapsed_time_s: float
    provider: WindProvider


class TimeVaryingWindProvider:
    """Provider that switches wind models at deterministic elapsed times."""

    provider_id = "time-varying"

    def __init__(
        self,
        base_provider: WindProvider,
        changes: list[TimedWindChange],
    ) -> None:
        self._base_provider = base_provider
        self._changes: tuple[TimedWindChange, ...] = tuple(
            sorted(changes, key=lambda c: c.effective_elapsed_time_s)
        )
        self._change_times: tuple[float, ...] = tuple(
            c.effective_elapsed_time_s for c in self._changes
        )

    def _provider_for_elapsed_time(self, elapsed_time_s: float) -> WindProvider:
        idx = bisect.bisect_right(self._change_times, elapsed_time_s) - 1
        if idx < 0:
            return self._base_provider
        return self._changes[idx].provider

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        provider = self._provider_for_elapsed_time(elapsed_time_s)
        return provider.wind_at(
            lat=lat,
            lon=lon,
            altitude_amsl_m=altitude_amsl_m,
            elapsed_time_s=elapsed_time_s,
        )


class SpatiotemporalWindProvider:
    """Provider backed by a 4D (time × altitude × lat × lon) wind grid.

    All four axes must be strictly monotonically increasing and contain at
    least two entries each. Wind vectors are quadrilinearly interpolated from
    the eight surrounding grid points. Queries outside any axis bound are
    clamped to the nearest edge (no out-of-bounds error at query time).
    """

    provider_id = "spatiotemporal_grid"

    def __init__(
        self,
        *,
        time_s: list[float],
        altitude_m: list[float],
        lat: list[float],
        lon: list[float],
        # values[t_idx][alt_idx][lat_idx][lon_idx] = [east_mps, north_mps]
        values: list[list[list[list[list[float]]]]],
    ) -> None:
        self._time_s = tuple(time_s)
        self._altitude_m = tuple(altitude_m)
        self._lat = tuple(lat)
        self._lon = tuple(lon)
        self._n_t = len(self._time_s)
        self._n_a = len(self._altitude_m)
        self._n_lat = len(self._lat)
        self._n_lon = len(self._lon)
        self._east = tuple(float(en[0]) for t in values for a in t for lat_row in a for en in lat_row)
        self._north = tuple(float(en[1]) for t in values for a in t for lat_row in a for en in lat_row)

    def _idx(self, it: int, ia: int, ilat: int, ilon: int) -> int:
        return (
            it * (self._n_a * self._n_lat * self._n_lon)
            + ia * (self._n_lat * self._n_lon)
            + ilat * self._n_lon
            + ilon
        )

    def wind_at(
        self,
        lat: float,
        lon: float,
        altitude_amsl_m: float,
        elapsed_time_s: float,
    ) -> WindVector:
        it0, tt = _interp_index(self._time_s, elapsed_time_s)
        ia0, ta = _interp_index(self._altitude_m, altitude_amsl_m)
        ilat0, tlat = _interp_index(self._lat, lat)
        ilon0, tlon = _interp_index(self._lon, lon)

        def _get(dt: int, da: int, dlat: int, dlon: int) -> tuple[float, float]:
            idx = self._idx(it0 + dt, ia0 + da, ilat0 + dlat, ilon0 + dlon)
            return self._east[idx], self._north[idx]

        def _lon_interp(dt: int, da: int, dlat: int) -> tuple[float, float]:
            e0, n0 = _get(dt, da, dlat, 0)
            e1, n1 = _get(dt, da, dlat, 1)
            return _lerp(e0, e1, tlon), _lerp(n0, n1, tlon)

        def _lat_interp(dt: int, da: int) -> tuple[float, float]:
            e0, n0 = _lon_interp(dt, da, 0)
            e1, n1 = _lon_interp(dt, da, 1)
            return _lerp(e0, e1, tlat), _lerp(n0, n1, tlat)

        def _alt_interp(dt: int) -> tuple[float, float]:
            e0, n0 = _lat_interp(dt, 0)
            e1, n1 = _lat_interp(dt, 1)
            return _lerp(e0, e1, ta), _lerp(n0, n1, ta)

        e0, n0 = _alt_interp(0)
        e1, n1 = _alt_interp(1)
        return WindVector(
            wind_east_mps=_lerp(e0, e1, tt),
            wind_north_mps=_lerp(n0, n1, tt),
        )


def wind_provider_id(provider: WindProvider) -> str:
    provider_id = getattr(provider, "provider_id", None)
    if isinstance(provider_id, str) and provider_id:
        return provider_id
    return "custom"
