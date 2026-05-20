"""Vehicle profile schema.

The vehicle profile combines externally sourced aircraft specs with the
simulator-specific performance values needed for feasibility checks.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.resource_link import ResourceSystemConfig
from schemas.vehicle_capabilities import VehicleCapabilities
from schemas.vehicle_energy import EnergyModel, FailsafeProfile
from schemas.vehicle_enums import AutopilotStack, VehicleClass
from schemas.vehicle_mass import MassProfile
from schemas.vehicle_performance import PerformanceProfile
from schemas.vehicle_controller import ControllerProfile
from schemas.vehicle_sensors import SensorProfile
from schemas.vehicle_sitl import SitlProfile


@dataclass(frozen=True)
class _VehicleClassRequirement:
    vehicle_classes: frozenset[VehicleClass]
    owner_attr: str
    field_name: str
    message: str


_CLASS_REQUIREMENTS = (
    _VehicleClassRequirement(
        vehicle_classes=frozenset({VehicleClass.MULTIROTOR, VehicleClass.VTOL}),
        owner_attr="performance",
        field_name="hover_speed_mps",
        message="hover_speed_mps is required for multirotor and VTOL vehicles",
    ),
    _VehicleClassRequirement(
        vehicle_classes=frozenset({VehicleClass.MULTIROTOR, VehicleClass.VTOL}),
        owner_attr="energy",
        field_name="hover_power_w",
        message="hover_power_w is required for multirotor and VTOL vehicles",
    ),
    _VehicleClassRequirement(
        vehicle_classes=frozenset({VehicleClass.FIXED_WING, VehicleClass.VTOL}),
        owner_attr="performance",
        field_name="turn_radius_m",
        message="turn_radius_m is required for fixed-wing and VTOL vehicles",
    ),
)


class VehicleProfile(BaseModel):
    """Top-level vehicle profile used by mission validation and simulation."""

    model_config = ConfigDict(extra="forbid")

    vehicle_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable identifier referenced by mission files.",
    )
    display_name: str | None = Field(
        default=None,
        description="Human-readable vehicle name not used by estimator v1.",
    )
    vehicle_class: VehicleClass = Field(
        description="Vehicle class used to select route and energy assumptions.",
    )
    mav_type: str = Field(
        min_length=1,
        description=(
            "MAVLink MAV_TYPE name, for example MAV_TYPE_VTOL_QUADROTOR. "
            "Kept as a string to avoid coupling schemas to a MAVLink library. "
            "Accepted for interoperability, but not used by estimator v1."
        ),
    )
    autopilot: AutopilotStack = Field(
        default=AutopilotStack.GENERIC,
        description="Autopilot family reserved for SITL/integration work and not used by estimator v1.",
    )

    mass: MassProfile
    performance: PerformanceProfile
    energy: EnergyModel
    resource_systems: list[ResourceSystemConfig] = Field(
        default_factory=list,
        description=(
            "Optional generalized resource systems. When omitted, the estimator "
            "uses vehicle.energy as the legacy onboard battery resource."
        ),
    )
    failsafe: FailsafeProfile = Field(default_factory=FailsafeProfile)
    capabilities: VehicleCapabilities | None = Field(
        default=None,
        description=(
            "Optional explicit capabilities. Estimator derives defaults from "
            "vehicle_class when omitted."
        ),
    )
    sitl: SitlProfile | None = None
    sensors: SensorProfile | None = None
    controller: ControllerProfile | None = None
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form notes such as source links, version, or calibration status ignored by estimator v1.",
    )

    @model_validator(mode="after")
    def validate_class_requirements(self) -> "VehicleProfile":
        for requirement in _CLASS_REQUIREMENTS:
            if self.vehicle_class not in requirement.vehicle_classes:
                continue
            owner = getattr(self, requirement.owner_attr)
            if getattr(owner, requirement.field_name) is None:
                raise ValueError(requirement.message)

        return self


__all__ = [
    "AutopilotStack",
    "ControllerProfile",
    "EnergyModel",
    "FailsafeProfile",
    "MassProfile",
    "PerformanceProfile",
    "ResourceSystemConfig",
    "SensorProfile",
    "SitlProfile",
    "VehicleCapabilities",
    "VehicleClass",
    "VehicleProfile",
]
