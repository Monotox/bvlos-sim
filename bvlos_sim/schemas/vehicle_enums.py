"""Vehicle enums shared across schema modules."""

from enum import StrEnum


class VehicleClass(StrEnum):
    """High-level vehicle class used by route and energy models."""

    MULTIROTOR = "multirotor"
    FIXED_WING = "fixed_wing"
    VTOL = "vtol"


class AutopilotStack(StrEnum):
    """Autopilot family used for SITL and MAVLink behavior."""

    ARDUPILOT = "ardupilot"
    PX4 = "px4"
    GENERIC = "generic"


class CalibrationStatus(StrEnum):
    """Provenance of the vehicle's performance and energy coefficients."""

    MANUFACTURER_DERIVED = "manufacturer_derived"
    PLACEHOLDER_VALUES = "placeholder_values"
    LOG_CALIBRATED = "log_calibrated"


__all__ = [
    "AutopilotStack",
    "CalibrationStatus",
    "VehicleClass",
]
