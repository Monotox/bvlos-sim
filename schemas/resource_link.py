"""Resource and communication-link feasibility schema models."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.numeric import FiniteFloat


class ResourceSystemKind(StrEnum):
    """Supported deterministic resource-system families."""

    ONBOARD_BATTERY = "onboard_battery"
    EXTERNAL_POWER = "external_power"
    HYBRID = "hybrid"
    FUEL = "fuel"
    HYDROGEN = "hydrogen"
    OTHER = "other"


class ExternalPowerDelivery(StrEnum):
    """External power delivery mechanisms accepted by the schema."""

    GENERIC = "generic"
    TETHERED = "tethered"
    OPTICAL_FIBER = "optical_fiber"


class LinkSystemKind(StrEnum):
    """Supported deterministic communication-link families."""

    DIRECT_RADIO = "direct_radio"
    MESH_NETWORK = "mesh_network"
    CELLULAR = "cellular_lte_5g"
    SATELLITE = "satellite"
    STARLINK = "starlink"
    HYBRID = "hybrid"


class LinkAvailability(StrEnum):
    """Static deterministic link availability state."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ResourceSystemConfig(BaseModel):
    """Vehicle resource system used by deterministic feasibility checks.

    Resource systems are evaluated after route expansion in all fidelity modes.
    When omitted, the estimator preserves legacy battery-only behavior from
    ``vehicle.energy``.
    """

    model_config = ConfigDict(extra="forbid")

    resource_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable resource-system identifier used in diagnostics.",
    )
    kind: ResourceSystemKind = Field(
        description="Resource-system family used for deterministic feasibility.",
    )
    priority: int = Field(
        default=0,
        ge=0,
        description="Lower values are preferred when multiple resource systems are feasible.",
    )
    battery_capacity_wh: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Onboard or hybrid battery capacity in Wh. Used by onboard_battery "
            "and hybrid resource systems; when omitted, vehicle.energy.battery_capacity_wh "
            "is used."
        ),
    )
    reserve_percent: FiniteFloat | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Resource-specific reserve percentage. Used by onboard_battery and "
            "hybrid systems; when omitted, the mission or vehicle reserve policy is used."
        ),
    )
    continuous_power_w: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Continuous supplied power in W. Used by external_power and hybrid "
            "systems in all fidelity modes."
        ),
    )
    delivery: ExternalPowerDelivery | None = Field(
        default=None,
        description=(
            "External delivery mechanism for documentation. Always ignored by "
            "deterministic feasibility."
        ),
    )
    max_route_distance_m: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description="Optional maximum total route path distance in metres.",
    )
    max_route_time_s: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description="Optional maximum total route time in seconds.",
    )
    max_tether_length_m: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional maximum horizontal distance from planned home in metres. "
            "Used to model tethered or optical-fiber reach limits."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form resource-system notes ignored by deterministic checks.",
    )

    @model_validator(mode="after")
    def validate_power_fields(self) -> "ResourceSystemConfig":
        if self.kind in {ResourceSystemKind.EXTERNAL_POWER, ResourceSystemKind.HYBRID}:
            if self.continuous_power_w is None:
                raise ValueError(
                    "continuous_power_w is required for external_power and hybrid resource systems"
                )
        return self


class LinkSystemConfig(BaseModel):
    """Mission or scenario communication-link system for deterministic checks.

    Link systems are evaluated after route expansion in all fidelity modes.
    No live network calls are made by the estimator.
    """

    model_config = ConfigDict(extra="forbid")

    link_id: str = Field(
        min_length=1,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
        description="Stable link-system identifier used in diagnostics.",
    )
    kind: LinkSystemKind = Field(
        description="Communication-link family used for deterministic feasibility.",
    )
    required: bool = Field(
        default=True,
        description=(
            "When true, this link participates in command-and-control feasibility. "
            "At least one required link must be feasible when required links exist."
        ),
    )
    priority: int = Field(
        default=0,
        ge=0,
        description="Lower values are preferred when multiple required links are feasible.",
    )
    availability: LinkAvailability = Field(
        default=LinkAvailability.AVAILABLE,
        description="Static deterministic availability used by estimate and scenario runs.",
    )
    max_range_m: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional maximum horizontal distance from planned home in metres. "
            "Used by estimate and scenario runs when set."
        ),
    )
    coverage_asset_ref: str | None = Field(
        default=None,
        min_length=1,
        description=(
            "Reference to a future coverage asset. Accepted for schema stability "
            "but always ignored by the estimator."
        ),
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Free-form link-system notes ignored by deterministic checks.",
    )


__all__ = [
    "ExternalPowerDelivery",
    "LinkAvailability",
    "LinkSystemConfig",
    "LinkSystemKind",
    "ResourceSystemConfig",
    "ResourceSystemKind",
]
