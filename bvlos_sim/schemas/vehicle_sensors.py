"""Vehicle sensor model schema (sensors are optional; absent = perfect measurements).

Non-operative fields are accepted and validated but not consumed by the current
EKF implementation. They are reserved for future sensor model extensions and
must not be treated as enforced behavior.
"""

from pydantic import BaseModel, ConfigDict, Field

from bvlos_sim.schemas.numeric import FiniteFloat


class GpsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    horizontal_accuracy_m: FiniteFloat = Field(
        default=2.5,
        gt=0,
        description="1-sigma CEP horizontal position noise in metres. Used by the EKF.",
    )
    vertical_accuracy_m: FiniteFloat = Field(
        default=4.0,
        gt=0,
        description=(
            "1-sigma vertical position noise in metres. "
            "Non-operative in current EKF (horizontal-only); reserved for 3D observation modeling."
        ),
    )
    fix_rate_hz: FiniteFloat = Field(
        default=5.0,
        gt=0,
        description="Measurement arrival rate in Hz. Used by the EKF.",
    )
    availability: FiniteFloat = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Fraction of time a GPS fix is available. Used by the EKF.",
    )


class BatteryMeterModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_sensor_noise_pct: FiniteFloat = Field(
        default=1.0,
        ge=0.0,
        description="1-sigma current measurement noise as % of reading. Used by the EKF.",
    )
    voltage_noise_mv: FiniteFloat = Field(
        default=10.0,
        ge=0.0,
        description=(
            "1-sigma voltage measurement noise in millivolts. "
            "Non-operative in current EKF (current-sensor path only); reserved for voltage-noise modeling."
        ),
    )
    update_rate_hz: FiniteFloat = Field(default=10.0, gt=0)


class AirspeedModel(BaseModel):
    """Airspeed sensor noise model.

    Non-operative in the current EKF implementation: no airspeed observation
    step is present. Fields are validated and stored but produce no effect on
    propagation output. Reserved for a future airspeed observation extension.
    """

    model_config = ConfigDict(extra="forbid")

    bias_mps: FiniteFloat = Field(
        default=0.0,
        description="Systematic offset added to every measurement. Non-operative in current EKF.",
    )
    noise_std_mps: FiniteFloat = Field(
        default=0.3,
        ge=0.0,
        description="1-sigma measurement noise. Non-operative in current EKF.",
    )
    update_rate_hz: FiniteFloat = Field(
        default=10.0,
        gt=0,
        description="Measurement arrival rate in Hz. Non-operative in current EKF.",
    )


class SensorProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gps: GpsModel | None = None
    battery_meter: BatteryMeterModel | None = None
    airspeed: AirspeedModel | None = None


__all__ = ["AirspeedModel", "BatteryMeterModel", "GpsModel", "SensorProfile"]
