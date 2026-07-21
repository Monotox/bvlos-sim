"""Wind provider abstractions."""

import bisect
import math
from dataclasses import dataclass
from typing import Protocol

from estimator.core.results import WindVector


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _finite_float(value: object, *, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a finite number, not a boolean.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a finite number.") from exc
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite.")
    return result


def _validated_axis(
    values: list[float],
    *,
    name: str,
    lower_bound: float | None = None,
    upper_bound: float | None = None,
) -> tuple[float, ...]:
    axis = tuple(
        _finite_float(value, label=f"Wind grid axis '{name}'[{index}]")
        for index, value in enumerate(values)
    )
    if len(axis) < 2:
        raise ValueError(f"Wind grid axis '{name}' must contain at least 2 entries.")
    if any(left >= right for left, right in zip(axis, axis[1:])):
        raise ValueError(
            f"Wind grid axis '{name}' must be strictly monotonically increasing."
        )
    if lower_bound is not None and axis[0] < lower_bound:
        raise ValueError(f"Wind grid axis '{name}' must be >= {lower_bound}.")
    if upper_bound is not None and axis[-1] > upper_bound:
        raise ValueError(f"Wind grid axis '{name}' must be <= {upper_bound}.")
    return axis


def _grid_sequence(value: object, *, expected: int, label: str) -> list[object]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"Wind grid values{label} must be a sequence.")
    if len(value) != expected:
        raise ValueError(
            f"Wind grid values{label} must contain {expected} entries; got {len(value)}."
        )
    return list(value)


def _validated_grid_values(
    values: object,
    *,
    n_t: int,
    n_a: int,
    n_lat: int,
    n_lon: int,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    east: list[float] = []
    north: list[float] = []
    for it, time_block in enumerate(_grid_sequence(values, expected=n_t, label="")):
        for ia, altitude_block in enumerate(
            _grid_sequence(time_block, expected=n_a, label=f"[{it}]")
        ):
            for ilat, latitude_row in enumerate(
                _grid_sequence(
                    altitude_block,
                    expected=n_lat,
                    label=f"[{it}][{ia}]",
                )
            ):
                for ilon, pair in enumerate(
                    _grid_sequence(
                        latitude_row,
                        expected=n_lon,
                        label=f"[{it}][{ia}][{ilat}]",
                    )
                ):
                    pair_label = f"[{it}][{ia}][{ilat}][{ilon}]"
                    components = _grid_sequence(pair, expected=2, label=pair_label)
                    east.append(
                        _finite_float(
                            components[0], label=f"Wind grid values{pair_label}[0]"
                        )
                    )
                    north.append(
                        _finite_float(
                            components[1], label=f"Wind grid values{pair_label}[1]"
                        )
                    )
    return tuple(east), tuple(north)


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
        self.wind_east_mps = _finite_float(wind_east_mps, label="wind_east_mps")
        self.wind_north_mps = _finite_float(wind_north_mps, label="wind_north_mps")

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
        normalized = [
            WindLayer(
                altitude_m=_finite_float(
                    layer.altitude_m, label=f"layers[{index}].altitude_m"
                ),
                wind_east_mps=_finite_float(
                    layer.wind_east_mps, label=f"layers[{index}].wind_east_mps"
                ),
                wind_north_mps=_finite_float(
                    layer.wind_north_mps, label=f"layers[{index}].wind_north_mps"
                ),
            )
            for index, layer in enumerate(layers)
        ]
        if len({layer.altitude_m for layer in normalized}) != len(normalized):
            raise ValueError("LayeredWindProvider layer altitudes must be unique.")
        self._layers = tuple(
            sorted(normalized, key=lambda layer: layer.altitude_m, reverse=True)
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
        normalized_changes: list[TimedWindChange] = []
        for index, change in enumerate(changes):
            effective_time = _finite_float(
                change.effective_elapsed_time_s,
                label=f"changes[{index}].effective_elapsed_time_s",
            )
            if effective_time < 0.0:
                raise ValueError(
                    "Timed wind changes cannot take effect before mission time zero."
                )
            normalized_changes.append(
                TimedWindChange(
                    effective_elapsed_time_s=effective_time,
                    provider=change.provider,
                )
            )
        self._changes: tuple[TimedWindChange, ...] = tuple(
            sorted(normalized_changes, key=lambda c: c.effective_elapsed_time_s)
        )
        self._change_times: tuple[float, ...] = tuple(
            c.effective_elapsed_time_s for c in self._changes
        )

    def _provider_for_elapsed_time(self, elapsed_time_s: float) -> WindProvider:
        idx = bisect.bisect_right(self._change_times, elapsed_time_s) - 1
        if idx < 0:
            return self._base_provider
        return self._changes[idx].provider

    def provider_for_elapsed_time(self, elapsed_time_s: float) -> WindProvider:
        """Return the provider active at ``elapsed_time_s``.

        Transit integration uses this together with :meth:`next_change_after`
        to integrate each discontinuous wind regime separately.  Keeping the
        active provider explicit prevents a midpoint solve from sampling a
        future regime and applying it to distance flown before the change.
        """

        return self._provider_for_elapsed_time(elapsed_time_s)

    def next_change_after(self, elapsed_time_s: float) -> float | None:
        """Return the first scheduled change strictly after ``elapsed_time_s``."""

        idx = bisect.bisect_right(self._change_times, elapsed_time_s)
        if idx >= len(self._change_times):
            return None
        return self._change_times[idx]

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
    the 16 surrounding grid points. Queries outside any axis bound are
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
        self._time_s = _validated_axis(time_s, name="time_s")
        self._altitude_m = _validated_axis(altitude_m, name="altitude_m")
        self._lat = _validated_axis(
            lat, name="lat", lower_bound=-90.0, upper_bound=90.0
        )
        self._lon = _validated_axis(
            lon, name="lon", lower_bound=-180.0, upper_bound=180.0
        )
        self._n_t = len(self._time_s)
        self._n_a = len(self._altitude_m)
        self._n_lat = len(self._lat)
        self._n_lon = len(self._lon)
        self._east, self._north = _validated_grid_values(
            values,
            n_t=self._n_t,
            n_a=self._n_a,
            n_lat=self._n_lat,
            n_lon=self._n_lon,
        )

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
