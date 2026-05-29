"""SORA pre-assessment output schema (``sora-assessment.v1``).

This module is the data contract for the ``sora`` command. It is intentionally
self-contained (no estimator imports) so that the schema layer stays free of a
dependency on the execution layer; the ARC rule set and SAIL/OSO tables in
``estimator.execution`` import the enums defined here.

The values produced against this schema are a planning aid. They do not
constitute a certified SORA determination by a competent authority.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

SORA_ASSESSMENT_SCHEMA_VERSION = "sora-assessment.v1"

SORA_NON_CERTIFICATION_DISCLAIMER = (
    "This SORA pre-assessment is an engineering planning aid, not a certified "
    "determination. The Ground Risk Class, Air Risk Class, SAIL, and OSO list "
    "are computed from simplified table-driven rules and do not replace a "
    "competent authority review of a full Operational Safety Risk Assessment."
)


class AirRiskClass(StrEnum):
    """SORA Air Risk Class (collision-risk likelihood category)."""

    A = "a"
    B = "b"
    C = "c"
    D = "d"


class Sail(StrEnum):
    """Specific Assurance and Integrity Level.

    ``CERTIFIED`` is a sentinel for operations whose final GRC falls outside the
    specific-category envelope (GRC > 7); such operations require the certified
    category and have no SAIL.
    """

    I = "I"  # noqa: E741 - SAIL level name, not an ambiguous identifier
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"
    VI = "VI"
    CERTIFIED = "certified"


class RobustnessLevel(StrEnum):
    """OSO robustness level required at a given SAIL."""

    OPTIONAL = "O"
    LOW = "L"
    MEDIUM = "M"
    HIGH = "H"


class SoraAdvisoryCode(StrEnum):
    """Advisory codes explaining why part of the assessment was not computed."""

    AIRSPACE_DESCRIPTOR_MISSING = "AIRSPACE_DESCRIPTOR_MISSING"
    GROUND_RISK_NOT_COMPUTED = "GROUND_RISK_NOT_COMPUTED"
    OPERATION_OUTSIDE_SPECIFIC_CATEGORY = "OPERATION_OUTSIDE_SPECIFIC_CATEGORY"


class SoraAdvisory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SoraAdvisoryCode
    message: str


class OsoRequirement(BaseModel):
    """A single Operational Safety Objective and its required robustness."""

    model_config = ConfigDict(extra="forbid")

    oso_id: str
    title: str
    robustness: RobustnessLevel


class SoraAssessment(BaseModel):
    """Whole-mission SORA pre-assessment result."""

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    characteristic_dimension_m: float | None = None
    intrinsic_grc: int | None = None
    final_grc: int | None = None
    initial_air_risk_class: AirRiskClass | None = None
    air_risk_class: AirRiskClass | None = None
    strategic_mitigation_applied: bool = False
    sail: Sail | None = None
    applicable_osos: list[OsoRequirement] = Field(default_factory=list)
    advisories: list[SoraAdvisory] = Field(default_factory=list)
    disclaimer: str = SORA_NON_CERTIFICATION_DISCLAIMER


__all__ = [
    "SORA_ASSESSMENT_SCHEMA_VERSION",
    "SORA_NON_CERTIFICATION_DISCLAIMER",
    "AirRiskClass",
    "OsoRequirement",
    "RobustnessLevel",
    "Sail",
    "SoraAdvisory",
    "SoraAdvisoryCode",
    "SoraAssessment",
]
