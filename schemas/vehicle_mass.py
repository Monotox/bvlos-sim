"""Vehicle mass schema models."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas.numeric import FiniteFloat


class MassProfile(BaseModel):
    """Mass properties normally sourced from manufacturer specs."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    empty_kg: FiniteFloat = Field(
        gt=0,
        description="Vehicle mass without payload. Source: manufacturer/spec sheet.",
    )
    max_payload_kg: FiniteFloat = Field(
        ge=0,
        description="Maximum payload mass. Source: manufacturer/spec sheet.",
    )
    max_takeoff_kg: FiniteFloat = Field(
        gt=0,
        description="Maximum takeoff mass. Source: manufacturer/spec sheet.",
    )
    operating_mass_kg: FiniteFloat | None = Field(
        default=None,
        gt=0,
        description="All-up mission mass including payload and battery.",
    )

    @model_validator(mode="after")
    def validate_takeoff_mass(self) -> "MassProfile":
        required_takeoff_mass = self.empty_kg + self.max_payload_kg
        if self.max_takeoff_kg < required_takeoff_mass:
            raise ValueError(
                "max_takeoff_kg must be greater than or equal to "
                "empty_kg + max_payload_kg"
            )
        if self.operating_mass_kg is not None:
            if self.operating_mass_kg < self.empty_kg:
                raise ValueError(
                    "operating_mass_kg must be greater than or equal to empty_kg"
                )
            if self.operating_mass_kg > self.max_takeoff_kg:
                raise ValueError(
                    "operating_mass_kg must be less than or equal to max_takeoff_kg"
                )
        return self


__all__ = ["MassProfile"]
