"""Vehicle profile schema.

The vehicle profile combines externally sourced aircraft specs with the
simulator-specific performance values needed for feasibility checks.
"""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bvlos_sim.schemas.resource_link import ResourceSystemConfig
from bvlos_sim.schemas.numeric import FiniteFloat
from bvlos_sim.schemas.vehicle_capabilities import VehicleCapabilities
from bvlos_sim.schemas.vehicle_energy import EnergyModel, FailsafeProfile
from bvlos_sim.schemas.vehicle_enums import (
    AutopilotStack,
    CalibrationStatus,
    VehicleClass,
)
from bvlos_sim.schemas.vehicle_mass import MassProfile
from bvlos_sim.schemas.vehicle_performance import PerformanceProfile
from bvlos_sim.schemas.vehicle_controller import ControllerProfile
from bvlos_sim.schemas.vehicle_sensors import SensorProfile
from bvlos_sim.schemas.vehicle_sitl import SitlProfile


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

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

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
    characteristic_dimension_m: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Maximum characteristic dimension in metres: wingspan for fixed-wing, "
            "blade diameter for a rotorcraft, or maximum distance between blade "
            "tips for a multicopter. Required for SORA Ground Risk Class."
        ),
    )
    mav_type: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Optional MAVLink MAV_TYPE name, for example MAV_TYPE_VTOL_QUADROTOR. "
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
    calibration_status: CalibrationStatus | None = Field(
        default=None,
        description=(
            "Provenance of the performance and energy coefficients. Anything "
            "other than manufacturer_derived or log_calibrated — including "
            "omitting the field — raises ENERGY_MODEL_UNCALIBRATED, which "
            "blocks the operational GO verdict until the operator supplies a "
            "calibration profile or acknowledges the code."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form notes such as source links or version, ignored by estimator v1. Calibration provenance belongs in the typed calibration_status field.",
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
