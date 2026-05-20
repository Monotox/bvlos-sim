"""Scalar EKF estimated-state tracker for the twin-state propagator."""

import math
import random
from dataclasses import dataclass

from estimator.execution.sensor_models import (
    battery_fires_at_step,
    draw_battery_consumed,
    draw_gps_measurement,
    gps_fires_at_step,
    haversine_m,
)
from schemas.vehicle_sensors import SensorProfile

_LARGE_VARIANCE = 1e8  # initial covariance meaning "unknown"


@dataclass(slots=True)
class _EstimatedPositionState:
    lat: float
    lon: float
    P_lat: float  # variance in degrees^2
    P_lon: float


@dataclass(slots=True)
class EstimatedStateTracker:
    """Tracks the autopilot's estimated state for one particle."""

    est_lat: float
    est_lon: float
    est_energy_remaining_wh: float
    P_lat: float
    P_lon: float
    sensors: SensorProfile
    last_true_lat: float
    last_true_lon: float

    @classmethod
    def initial(
        cls,
        *,
        true_lat: float,
        true_lon: float,
        battery_cap_wh: float,
        sensors: SensorProfile,
    ) -> "EstimatedStateTracker":
        gps_sigma_deg = (
            sensors.gps.horizontal_accuracy_m / 111_111.0 if sensors.gps else 0.0
        )
        initial_P = gps_sigma_deg**2 if gps_sigma_deg > 0 else 0.0
        return cls(
            est_lat=true_lat,
            est_lon=true_lon,
            est_energy_remaining_wh=battery_cap_wh,
            P_lat=initial_P,
            P_lon=initial_P,
            sensors=sensors,
            last_true_lat=true_lat,
            last_true_lon=true_lon,
        )

    def step(
        self,
        *,
        step_index: int,
        dt_s: float,
        true_lat: float,
        true_lon: float,
        true_energy_consumed_since_last_wh: float,
        rng: random.Random,
    ) -> None:
        """Apply prediction + sensor updates for one time step."""
        self._predict_position(
            dt_s=dt_s, true_lat=true_lat, true_lon=true_lon, rng=rng
        )
        self._update_gps(
            step_index=step_index,
            dt_s=dt_s,
            true_lat=true_lat,
            true_lon=true_lon,
            rng=rng,
        )
        self._update_battery(
            step_index=step_index,
            dt_s=dt_s,
            true_energy_consumed_wh=true_energy_consumed_since_last_wh,
            rng=rng,
        )

    def _predict_position(
        self,
        *,
        dt_s: float,
        true_lat: float,
        true_lon: float,
        rng: random.Random,
    ) -> None:
        gps = self.sensors.gps
        if gps is None:
            return

        self.est_lat += true_lat - self.last_true_lat
        self.est_lon += true_lon - self.last_true_lon
        self.last_true_lat = true_lat
        self.last_true_lon = true_lon

        drift_var_per_s = (gps.horizontal_accuracy_m / 111_111.0) ** 2
        self.P_lat += drift_var_per_s * dt_s
        self.P_lon += drift_var_per_s * dt_s
        if dt_s <= 0.0:
            return

        drift_sigma_lat = math.sqrt(drift_var_per_s * dt_s)
        cos_lat = math.cos(math.radians(self.est_lat))
        drift_sigma_lon = drift_sigma_lat / max(1e-6, cos_lat)
        self.est_lat += rng.gauss(0.0, drift_sigma_lat)
        self.est_lon += rng.gauss(0.0, drift_sigma_lon)

    def _update_gps(
        self,
        *,
        step_index: int,
        dt_s: float,
        true_lat: float,
        true_lon: float,
        rng: random.Random,
    ) -> None:
        gps = self.sensors.gps
        if gps is None:
            return
        if not gps_fires_at_step(step_index, fix_rate_hz=gps.fix_rate_hz, dt_s=dt_s):
            return
        measurement = draw_gps_measurement(
            true_lat=true_lat, true_lon=true_lon, gps=gps, rng=rng
        )
        if measurement is None:
            return
        z_lat, z_lon = measurement
        sigma_deg = gps.horizontal_accuracy_m / 111_111.0
        R_lat = sigma_deg**2
        cos_lat = math.cos(math.radians(self.est_lat))
        R_lon = (sigma_deg / max(1e-6, cos_lat)) ** 2
        self.est_lat, self.P_lat = _kalman_scalar_update(
            x=self.est_lat, P=self.P_lat, z=z_lat, R=R_lat
        )
        self.est_lon, self.P_lon = _kalman_scalar_update(
            x=self.est_lon, P=self.P_lon, z=z_lon, R=R_lon
        )

    def _update_battery(
        self,
        *,
        step_index: int,
        dt_s: float,
        true_energy_consumed_wh: float,
        rng: random.Random,
    ) -> None:
        meter = self.sensors.battery_meter
        if meter is None:
            self.est_energy_remaining_wh = max(
                0.0, self.est_energy_remaining_wh - true_energy_consumed_wh
            )
            return
        if not battery_fires_at_step(
            step_index, update_rate_hz=meter.update_rate_hz, dt_s=dt_s
        ):
            self.est_energy_remaining_wh = max(
                0.0, self.est_energy_remaining_wh - true_energy_consumed_wh
            )
            return
        measured_consumed = draw_battery_consumed(
            true_energy_consumed_wh=true_energy_consumed_wh,
            meter=meter,
            rng=rng,
        )
        self.est_energy_remaining_wh = max(
            0.0, self.est_energy_remaining_wh - measured_consumed
        )

    def position_error_m(self, true_lat: float, true_lon: float) -> float:
        return haversine_m(true_lat, true_lon, self.est_lat, self.est_lon)

    def energy_error_wh(self, true_energy_remaining_wh: float) -> float:
        return abs(true_energy_remaining_wh - self.est_energy_remaining_wh)


def _kalman_scalar_update(
    *, x: float, P: float, z: float, R: float
) -> tuple[float, float]:
    """Return updated (estimate, variance) from a scalar Kalman measurement update."""
    if R <= 0.0:
        return z, 0.0
    total = P + R
    if total <= 0.0:
        return x, P
    K = P / total
    x_new = x + K * (z - x)
    P_new = (1.0 - K) * P
    return x_new, P_new
