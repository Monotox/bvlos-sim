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

# SORA methodology revision whose mitigation/credit tables are applied by
# default. Selecting a revision is a table lookup, not a logic change.
DEFAULT_SORA_VERSION = "2.0"

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


class MitigationRobustness(StrEnum):
    """Robustness rating declared for a SORA mitigation.

    ``NONE`` is the absence of a credited mitigation; the remaining levels map
    to the integrity/assurance robustness recognised by the SORA credit tables.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GroundRiskMitigation(BaseModel):
    """A single declared ground-risk mitigation (M1, M2, or M3)."""

    model_config = ConfigDict(extra="forbid")

    applied: bool = False
    robustness: MitigationRobustness = MitigationRobustness.NONE


class GroundRiskMitigations(BaseModel):
    """Operator-declared ground-risk mitigations applied to the final GRC."""

    model_config = ConfigDict(extra="forbid")

    m1_strategic: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M1 — strategic mitigations (e.g. controlled ground area, sheltering).",
    )
    m2_impact_reduction: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M2 — reduction of the effects of ground impact.",
    )
    m3_erp: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M3 — emergency response plan (ERP).",
    )


class AirRiskMitigations(BaseModel):
    """Operator-declared tactical air-risk mitigation applied to the residual ARC."""

    model_config = ConfigDict(extra="forbid")

    tactical_mitigation: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="Tactical air-risk reduction (e.g. DAA) rated by robustness.",
    )


class SoraMitigations(BaseModel):
    """Declared SORA mitigation inputs that step the intrinsic risk down.

    These are operator inputs to an explicit, auditable pre-assessment; they do
    not constitute a certified determination of compliance.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(
        default=DEFAULT_SORA_VERSION,
        description="SORA methodology revision selecting the mitigation credit tables.",
    )
    ground_risk_mitigations: GroundRiskMitigations = Field(
        default_factory=GroundRiskMitigations
    )
    air_risk: AirRiskMitigations = Field(default_factory=AirRiskMitigations)


class SoraAdvisoryCode(StrEnum):
    """Advisory codes explaining why part of the assessment was not computed."""

    AIRSPACE_DESCRIPTOR_MISSING = "AIRSPACE_DESCRIPTOR_MISSING"
    GROUND_RISK_NOT_COMPUTED = "GROUND_RISK_NOT_COMPUTED"
    OPERATION_OUTSIDE_SPECIFIC_CATEGORY = "OPERATION_OUTSIDE_SPECIFIC_CATEGORY"
    MITIGATION_VERSION_UNSUPPORTED = "MITIGATION_VERSION_UNSUPPORTED"


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


class GrcMitigationCredit(BaseModel):
    """One applied ground-risk mitigation and the GRC credit it contributes.

    ``grc_credit`` is signed: a negative value lowers the final GRC, a positive
    value (e.g. an insufficient ERP) raises it, per the SORA credit table.
    """

    model_config = ConfigDict(extra="forbid")

    mitigation_id: str
    title: str
    robustness: MitigationRobustness
    grc_credit: int


class TacticalAirRiskMitigation(BaseModel):
    """The applied tactical air-risk mitigation and the ARC bands it reduced."""

    model_config = ConfigDict(extra="forbid")

    robustness: MitigationRobustness
    arc_bands_reduced: int


class SoraAssessment(BaseModel):
    """Whole-mission SORA pre-assessment result."""

    model_config = ConfigDict(extra="forbid")

    mission_id: str
    sora_version: str = DEFAULT_SORA_VERSION
    characteristic_dimension_m: float | None = None
    intrinsic_grc: int | None = None
    final_grc: int | None = None
    ground_risk_mitigations: list[GrcMitigationCredit] = Field(default_factory=list)
    initial_air_risk_class: AirRiskClass | None = None
    air_risk_class: AirRiskClass | None = None
    strategic_mitigation_applied: bool = False
    tactical_air_risk_mitigation: TacticalAirRiskMitigation | None = None
    intrinsic_sail: Sail | None = None
    sail: Sail | None = None
    applicable_osos: list[OsoRequirement] = Field(default_factory=list)
    advisories: list[SoraAdvisory] = Field(default_factory=list)
    disclaimer: str = SORA_NON_CERTIFICATION_DISCLAIMER


__all__ = [
    "DEFAULT_SORA_VERSION",
    "SORA_ASSESSMENT_SCHEMA_VERSION",
    "SORA_NON_CERTIFICATION_DISCLAIMER",
    "AirRiskClass",
    "AirRiskMitigations",
    "GrcMitigationCredit",
    "GroundRiskMitigation",
    "GroundRiskMitigations",
    "MitigationRobustness",
    "OsoRequirement",
    "RobustnessLevel",
    "Sail",
    "SoraAdvisory",
    "SoraAdvisoryCode",
    "SoraAssessment",
    "SoraMitigations",
    "TacticalAirRiskMitigation",
]
