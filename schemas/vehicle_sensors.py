"""Vehicle sensor model schema (sensors are optional; absent = perfect measurements)."""

from pydantic import BaseModel, ConfigDict, Field


class GpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizontal_accuracy_m: float = Field(
        default=2.5,
        gt=0,
        description="1-sigma CEP horizontal position noise in metres.",
    )
    vertical_accuracy_m: float = Field(default=4.0, gt=0)
    fix_rate_hz: float = Field(
        default=5.0,
        gt=0,
        description="Measurement arrival rate in Hz.",
    )
    availability: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of time a GPS fix is available.",
    )


class BatteryMeterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_sensor_noise_pct: float = Field(
        default=1.0,
        ge=0.0,
        description="1-sigma current measurement noise as % of reading.",
    )
    voltage_noise_mv: float = Field(default=10.0, ge=0.0)
    update_rate_hz: float = Field(default=10.0, gt=0)


class AirspeedModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bias_mps: float = Field(
        default=0.0,
        description="Systematic offset added to every measurement.",
    )
    noise_std_mps: float = Field(default=0.3, ge=0.0)
    update_rate_hz: float = Field(default=10.0, gt=0)


class SensorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gps: GpsModel | None = None
    battery_meter: BatteryMeterModel | None = None
    airspeed: AirspeedModel | None = None


__all__ = ["AirspeedModel", "BatteryMeterModel", "GpsModel", "SensorProfile"]
