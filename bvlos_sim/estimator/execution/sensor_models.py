"""Synthetic sensor measurement draw functions for the EKF twin-state propagator."""

import math
import random

from bvlos_sim.schemas.vehicle_sensors import BatteryMeterModel, GpsModel

_DEG_PER_METRE = 1.0 / 111_111.0


def gps_fires_at_step(step_index: int, *, fix_rate_hz: float, dt_s: float) -> bool:
    """Return True when a GPS measurement is expected at this step index."""
    if dt_s <= 0.0:
        return True
    steps_per_fix = max(1, round(1.0 / (fix_rate_hz * dt_s)))
    return step_index % steps_per_fix == 0


def draw_gps_measurement(
    *,
    true_lat: float,
    true_lon: float,
    gps: GpsModel,
    rng: random.Random,
) -> tuple[float, float] | None:
    """Return (measured_lat, measured_lon) or None when GPS is unavailable."""
    if rng.random() > gps.availability:
        return None
    sigma_lat = gps.horizontal_accuracy_m * _DEG_PER_METRE
    cos_lat = math.cos(math.radians(true_lat))
    sigma_lon = gps.horizontal_accuracy_m * _DEG_PER_METRE / max(1e-6, cos_lat)
    return (
        true_lat + rng.gauss(0.0, sigma_lat),
        true_lon + rng.gauss(0.0, sigma_lon),
    )


def draw_battery_consumed(
    *,
    true_energy_consumed_wh: float,
    meter: BatteryMeterModel,
    rng: random.Random,
) -> float:
    """Return noisy energy-consumed measurement in Wh (coulomb-counting step)."""
    if true_energy_consumed_wh <= 0.0:
        return 0.0
    noise_std = true_energy_consumed_wh * meter.current_sensor_noise_pct / 100.0
    return true_energy_consumed_wh + rng.gauss(0.0, noise_std)


def battery_fires_at_step(
    step_index: int, *, update_rate_hz: float, dt_s: float
) -> bool:
    if dt_s <= 0.0:
        return True
    steps_per_update = max(1, round(1.0 / (update_rate_hz * dt_s)))
    return step_index % steps_per_update == 0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in metres between two lat/lon points (small angles)."""
    dlat_m = (lat2 - lat1) * 111_111.0
    mid_lat = (lat1 + lat2) * 0.5
    dlon_m = (lon2 - lon1) * 111_111.0 * math.cos(math.radians(mid_lat))
    return math.sqrt(dlat_m**2 + dlon_m**2)
