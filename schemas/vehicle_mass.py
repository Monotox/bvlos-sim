"""Vehicle mass schema models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MassProfile(BaseModel):
    """Mass properties normally sourced from manufacturer specs."""

    model_config = ConfigDict(extra="forbid")

    empty_kg: float = Field(
        gt=0,
        description="Vehicle mass without payload. Source: manufacturer/spec sheet.",
    )
    max_payload_kg: float = Field(
        ge=0,
        description="Maximum payload mass. Source: manufacturer/spec sheet.",
    )
    max_takeoff_kg: float = Field(
        gt=0,
        description="Maximum takeoff mass. Source: manufacturer/spec sheet.",
    )

    @model_validator(mode="after")
    def validate_takeoff_mass(self) -> "MassProfile":
        required_takeoff_mass = self.empty_kg + self.max_payload_kg
        if self.max_takeoff_kg < required_takeoff_mass:
            raise ValueError(
                "max_takeoff_kg must be greater than or equal to "
                "empty_kg + max_payload_kg"
            )
        return self


__all__ = ["MassProfile"]
