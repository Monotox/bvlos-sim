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


__all__ = [
    "AutopilotStack",
    "VehicleClass",
]
