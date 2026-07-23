"""SORA pre-assessment output schema (``sora-assessment.v3``).

This module is the data contract for the ``sora`` command. It is intentionally
self-contained (no estimator imports) so that the schema layer stays free of a
dependency on the execution layer; the ARC rule set and SAIL/OSO tables in
``estimator.execution`` import the enums defined here.

The values produced against this schema are a planning aid. They do not
constitute a certified SORA determination by a competent authority.
"""

from enum import StrEnum
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)

from schemas.numeric import FiniteFloat

SORA_ASSESSMENT_SCHEMA_VERSION = "sora-assessment.v3"

# The estimator implements one internally coherent methodology revision.  A
# different revision must be rejected rather than silently mixing its labels
# with the SORA 2.5 population/speed and mitigation tables.
DEFAULT_SORA_VERSION = "2.5"
SupportedSoraVersion = Literal["2.5"]

SORA_NON_CERTIFICATION_DISCLAIMER = (
    "This SORA pre-assessment is an engineering planning aid, not a certified "
    "determination. It identifies planning requirements; it does not assess "
    "compliance with Annex E containment requirements or the applicable OSOs, "
    "and it does not replace a competent authority review of a complete "
    "Operational Safety Risk Assessment."
)


class AirRiskClass(StrEnum):
    """SORA Air Risk Class (collision-risk likelihood category)."""

    A = "a"
    B = "b"
    C = "c"
    D = "d"


class Sail(StrEnum):
    """Specific Assurance and Integrity Level for a specific-category operation."""

    I = "I"  # noqa: E741 - SAIL level name, not an ambiguous identifier
    II = "II"
    III = "III"
    IV = "IV"
    V = "V"
    VI = "VI"


class RobustnessLevel(StrEnum):
    """OSO robustness level required at a given SAIL."""

    NOT_REQUIRED = "NR"
    LOW = "L"
    MEDIUM = "M"
    HIGH = "H"


class MitigationRobustness(StrEnum):
    """Reserved robustness rating for a SORA mitigation declaration.

    ``NONE`` is the absence of a claimed mitigation. Other labels do not earn
    credit without an Annex B criteria evaluation.
    """

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class OutdoorAssemblyCategory(StrEnum):
    """Largest outdoor assembly identified within the assessed one-kilometre area."""

    ABOVE_400000 = "above_400000"
    BETWEEN_40000_AND_400000 = "40000_to_400000"
    BELOW_40000 = "below_40000"
    NOT_APPLICABLE = "not_applicable"


class ContainmentRobustness(StrEnum):
    """Containment result from SORA 2.5 Tables 8-13."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    OUT_OF_SCOPE = "out_of_scope"


class PopulationDensityOperationalLimit(StrEnum):
    """Selected adjacent-area average-population operational limit."""

    NOT_REQUIRED = "not_required"
    NO_UPPER_LIMIT = "no_upper_limit"
    BELOW_50000 = "below_50000_ppl_km2"
    BELOW_5000 = "below_5000_ppl_km2"
    BELOW_500 = "below_500_ppl_km2"
    BELOW_50 = "below_50_ppl_km2"


class OutdoorAssemblyOperationalLimit(StrEnum):
    """Selected operational limit for outdoor assemblies near the volume."""

    NOT_REQUIRED = "not_required"
    NOT_APPLICABLE = "not_applicable"
    NO_UPPER_LIMIT = "no_upper_limit"
    MAXIMUM_400000 = "maximum_400000"
    BELOW_40000 = "below_40000"


class ContainmentMethod(StrEnum):
    """Step 8 branch used to derive the containment outcome."""

    SUB_250G = "sub_250g"
    GRB_COVERS_ADJACENT_AREA = "grb_covers_adjacent_area"
    TABLES_8_TO_13 = "tables_8_to_13"
    OUTSIDE_SPECIFIC_CATEGORY = "outside_specific_category"


class GroundRiskMitigation(BaseModel):
    """A single declared SORA 2.5 ground-risk mitigation."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    applied: StrictBool = False
    robustness: MitigationRobustness = MitigationRobustness.NONE
    evidence: str | None = Field(
        default=None,
        description="Auditable integrity/assurance evidence reference.",
    )
    footprint_revalidated: StrictBool = Field(
        default=False,
        description=(
            "For M2, confirms that the descent-dependent ground-risk footprint "
            "and GRB were reassessed after the mitigation."
        ),
    )

    @model_validator(mode="after")
    def validate_declaration(self) -> "GroundRiskMitigation":
        if self.applied and self.robustness == MitigationRobustness.NONE:
            raise ValueError("an applied mitigation requires a robustness level")
        if self.applied and (self.evidence is None or not self.evidence.strip()):
            raise ValueError(
                "an applied mitigation requires a nonblank evidence reference"
            )
        if not self.applied and self.robustness != MitigationRobustness.NONE:
            raise ValueError("robustness must be 'none' when mitigation is not applied")
        return self


class GroundRiskMitigations(BaseModel):
    """Reserved ground-risk mitigation declarations.

    The operational evaluator credits no applied declaration until Annex B
    integrity and assurance criteria can be evaluated: the assessment proceeds
    with the intrinsic GRC and records each declaration as
    ``credit_rejected_pending_annex_b``.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    m1a_sheltering: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M1(A) — strategic mitigation by sheltering.",
    )
    m1b_operational_restrictions: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M1(B) — strategic mitigation by operational restrictions.",
    )
    m1c_ground_observation: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M1(C) — tactical ground observation.",
    )
    m2_impact_reduction: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description="M2 — reduction of the effects of ground impact.",
    )


class GroundRiskFootprint(BaseModel):
    """Operator-derived SORA 2.5 ground-risk assessment footprint.

    The two distances form a conservative uniform corridor around the modeled
    route: the margin to the outer contingency volume, followed by the Ground
    Risk Buffer (GRB). The derivation remains operator evidence and is recorded
    in the assessment output.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    operational_volume_margin_m: FiniteFloat = Field(
        gt=0,
        description=(
            "Lateral distance from the nominal modeled route to the outer edge "
            "of the assessed operational/contingency volume."
        ),
    )
    ground_risk_buffer_m: FiniteFloat = Field(
        gt=0,
        description="Ground Risk Buffer outside the contingency volume, in metres.",
    )
    vertical_contingency_margin_m: FiniteFloat = Field(
        gt=0,
        description=(
            "Positive vertical contingency/error margin above the resolved route, "
            "in metres."
        ),
    )
    maximum_height_agl_m: FiniteFloat = Field(
        gt=0,
        description=(
            "Operator-verified maximum height AGL of the assessed operational "
            "and contingency volume, including vertical_contingency_margin_m."
        ),
    )
    buffer_method: Literal["initial_1_to_1"] = "initial_1_to_1"
    derivation: str = Field(
        min_length=1,
        description=(
            "Auditable operator reference explaining how the footprint and GRB "
            "were derived."
        ),
    )

    @model_validator(mode="after")
    def reject_blank_derivation(self) -> "GroundRiskFootprint":
        if not self.derivation.strip():
            raise ValueError("ground-risk footprint derivation must not be blank")
        if self.maximum_height_agl_m < self.vertical_contingency_margin_m:
            raise ValueError(
                "maximum_height_agl_m must include the vertical contingency margin"
            )
        return self

    @property
    def total_buffer_m(self) -> float:
        return self.operational_volume_margin_m + self.ground_risk_buffer_m


class AirRiskMitigations(BaseModel):
    """Air-risk declarations supported by this pre-assessment.

    Tactical mitigations satisfy the TMPR derived from the residual ARC; they
    do not lower that ARC.  The current input contract lacks the evidence needed
    to assess TMPR compliance, so a claimed tactical mitigation is rejected.
    """

    model_config = ConfigDict(extra="forbid")

    tactical_mitigation: GroundRiskMitigation = Field(
        default_factory=GroundRiskMitigation,
        description=(
            "Reserved for future TMPR compliance evidence. Applied declarations "
            "are currently unsupported."
        ),
    )

    @model_validator(mode="after")
    def reject_unverifiable_tactical_credit(self) -> "AirRiskMitigations":
        if self.tactical_mitigation.applied:
            raise ValueError(
                "tactical air-risk mitigation cannot reduce ARC; provide TMPR "
                "compliance evidence through a supported assessment workflow"
            )
        return self


class AdjacentAreaContainmentEvidence(BaseModel):
    """Auditable inputs used to derive SORA 2.5 Step 8 requirements.

    The average population density covers the area between the outer Ground Risk
    Buffer and the calculated outer adjacent-area limit. The assembly category
    covers the area within one kilometre of the operational-volume boundary.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    assessment_reference: str = Field(
        min_length=1,
        description="Auditable reference for the adjacent-area assessment.",
    )
    average_population_density_ppl_km2: FiniteFloat = Field(ge=0)
    largest_outdoor_assembly: OutdoorAssemblyCategory
    sheltering_applicable: StrictBool = Field(
        description=(
            "Whether sheltering can be applied for a Table 9 3 m-class UA. "
            "Larger-UA sheltering requires the unsupported Annex F evaluator."
        )
    )
    ground_risk_buffer_revalidation_reference: str | None = Field(
        default=None,
        description=(
            "Required when medium or high containment is derived; references the "
            "Step 2 GRC re-evaluation using the containment-informed GRB."
        ),
    )

    @model_validator(mode="after")
    def reject_blank_references(self) -> "AdjacentAreaContainmentEvidence":
        if not self.assessment_reference.strip():
            raise ValueError("containment assessment_reference must not be blank")
        reference = self.ground_risk_buffer_revalidation_reference
        if reference is not None and not reference.strip():
            raise ValueError(
                "ground_risk_buffer_revalidation_reference must not be blank"
            )
        return self


class SoraMitigations(BaseModel):
    """SORA footprint plus reserved mitigation declarations.

    Applied ground-risk declarations earn no credit until Annex B criteria
    evaluation exists; the assessment still runs without credit and reports
    each rejected declaration.
    """

    model_config = ConfigDict(extra="forbid")

    version: SupportedSoraVersion = Field(
        default=DEFAULT_SORA_VERSION,
        description="SORA methodology revision selecting the risk and OSO tables.",
    )
    ground_risk_footprint: GroundRiskFootprint | None = Field(
        default=None,
        description=(
            "Assessed operational-volume footprint plus Ground Risk Buffer. "
            "Required by the operational SORA command."
        ),
    )
    containment_evidence: AdjacentAreaContainmentEvidence | None = Field(
        default=None,
        description=(
            "Adjacent-area evidence required for aircraft of at least 250 g when "
            "the Ground Risk Buffer is smaller than the adjacent-area limit."
        ),
    )
    ground_risk_mitigations: GroundRiskMitigations = Field(
        default_factory=GroundRiskMitigations
    )
    air_risk: AirRiskMitigations = Field(default_factory=AirRiskMitigations)


class SoraAdvisoryCode(StrEnum):
    """Advisory codes explaining why part of the assessment was not computed."""

    AIRSPACE_DESCRIPTOR_MISSING = "AIRSPACE_DESCRIPTOR_MISSING"
    GROUND_MITIGATION_CREDIT_REJECTED = "GROUND_MITIGATION_CREDIT_REJECTED"
    GROUND_RISK_NOT_COMPUTED = "GROUND_RISK_NOT_COMPUTED"
    OPERATION_OUTSIDE_SPECIFIC_CATEGORY = "OPERATION_OUTSIDE_SPECIFIC_CATEGORY"
    MITIGATION_VERSION_UNSUPPORTED = "MITIGATION_VERSION_UNSUPPORTED"
    CONTAINMENT_COMPLIANCE_NOT_ASSESSED = "CONTAINMENT_COMPLIANCE_NOT_ASSESSED"
    CONTAINMENT_OUT_OF_SCOPE = "CONTAINMENT_OUT_OF_SCOPE"
    OSO_COMPLIANCE_NOT_ASSESSED = "OSO_COMPLIANCE_NOT_ASSESSED"


class SoraAdvisory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SoraAdvisoryCode
    message: str


class OsoPartyDependency(BaseModel):
    """Table 14 dependency on one responsible party.

    An empty ``criterion_refs`` list means that Table 14 marks the party with a
    plain ``X``. A non-empty list preserves the numbered criteria referenced by
    the table instead of flattening them into an unauditable title string.
    """

    model_config = ConfigDict(extra="forbid")

    applicable: bool
    criterion_refs: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_criterion_refs(self) -> "OsoPartyDependency":
        if self.criterion_refs and not self.applicable:
            raise ValueError("criterion_refs require an applicable party dependency")
        if any(reference < 1 for reference in self.criterion_refs):
            raise ValueError("criterion_refs must contain positive integers")
        if len(set(self.criterion_refs)) != len(self.criterion_refs):
            raise ValueError("criterion_refs must not contain duplicates")
        return self


class OsoPartyDependencies(BaseModel):
    """Table 14 dependencies for the operator, training entity, and designer."""

    model_config = ConfigDict(extra="forbid")

    operator: OsoPartyDependency
    training_organisation: OsoPartyDependency
    designer: OsoPartyDependency


class OsoRequirement(BaseModel):
    """One Table 14 OSO row for the selected SAIL."""

    model_config = ConfigDict(extra="forbid")

    oso_id: str
    title: str
    robustness: RobustnessLevel
    required: bool
    note_refs: list[str] = Field(default_factory=list)
    party_dependencies: OsoPartyDependencies

    @model_validator(mode="after")
    def validate_required_flag(self) -> "OsoRequirement":
        expected = self.robustness != RobustnessLevel.NOT_REQUIRED
        if self.required != expected:
            raise ValueError("required must be true exactly when robustness is not NR")
        return self


class GrcMitigationCreditStatus(StrEnum):
    """Outcome of the credit evaluation for one declared mitigation."""

    CREDIT_REJECTED_PENDING_ANNEX_B = "credit_rejected_pending_annex_b"


class GrcMitigationCredit(BaseModel):
    """Credit-evaluation record for one declared ground-risk mitigation.

    ``nominal_grc_credit`` is the table value. ``grc_credit`` is the effective
    value after the controlled-ground-area floor is applied to M1 credits. A
    ``credit_status`` of ``credit_rejected_pending_annex_b`` records an applied
    declaration that earned no credit because the Annex B integrity and
    assurance criteria could not be evaluated; the field is omitted from
    serialized output for an evaluated credit.
    """

    model_config = ConfigDict(extra="forbid")

    mitigation_id: str
    title: str
    robustness: MitigationRobustness
    evidence: str
    nominal_grc_credit: int
    grc_credit: int
    credit_status: GrcMitigationCreditStatus | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
        description=(
            "Set when the declaration earned no credit; absent for an "
            "evaluated credit."
        ),
    )

    @model_validator(mode="after")
    def reject_credit_on_rejected_status(self) -> "GrcMitigationCredit":
        if self.credit_status is not None and (
            self.nominal_grc_credit != 0 or self.grc_credit != 0
        ):
            raise ValueError(
                "a rejected mitigation declaration cannot carry GRC credit"
            )
        return self


class TacticalMitigationRequirement(BaseModel):
    """TMPR robustness required by the residual Air Risk Class."""

    model_config = ConfigDict(extra="forbid")

    required_robustness: MitigationRobustness


class PopulationEvidenceSummary(BaseModel):
    """SORA population-map provenance carried into the result artifact."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    schema_version: Literal["population-grid.v2"] = "population-grid.v2"
    source: str = Field(min_length=1)
    population_year: StrictInt = Field(ge=1900)
    native_resolution_m: FiniteFloat = Field(gt=0)
    effective_resolution_m: FiniteFloat = Field(gt=0)
    value_semantics: Literal["conservative_cell_maximum"]
    authority_assessment_reference: str = Field(min_length=1)
    valid_from: datetime
    valid_until: datetime
    transient_population_assessment_reference: str = Field(min_length=1)
    operational_footprint_assemblies_present: StrictBool

    @model_validator(mode="after")
    def validate_interval(self) -> "PopulationEvidenceSummary":
        if self.valid_until <= self.valid_from:
            raise ValueError("population evidence validity interval is empty")
        return self


class ContainmentRequirement(BaseModel):
    """Step 8 operational limits and required robustness, not compliance evidence."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    method: ContainmentMethod
    adjacent_area_outer_limit_m: FiniteFloat = Field(ge=0)
    adjacent_area_assessment_required: StrictBool
    selected_table: int | None = Field(default=None, ge=8, le=13)
    assessment_reference: str | None = None
    average_population_density_ppl_km2: FiniteFloat | None = Field(default=None, ge=0)
    largest_outdoor_assembly: OutdoorAssemblyCategory | None = None
    sheltering_assumed: StrictBool | None = None
    population_density_operational_limit: PopulationDensityOperationalLimit
    outdoor_assembly_operational_limit: OutdoorAssemblyOperationalLimit
    required_robustness: ContainmentRobustness
    ground_risk_buffer_revalidation_reference: str | None = None
    within_specific_category_method_scope: StrictBool
    annex_e_compliance_status: Literal["not_assessed"] = "not_assessed"

    @model_validator(mode="after")
    def validate_consistency(self) -> "ContainmentRequirement":
        evidence_values = (
            self.assessment_reference,
            self.average_population_density_ppl_km2,
            self.largest_outdoor_assembly,
            self.sheltering_assumed,
        )
        if self.adjacent_area_assessment_required:
            if any(value is None for value in evidence_values):
                raise ValueError(
                    "a required adjacent-area assessment needs complete evidence"
                )
        elif self.selected_table is not None or any(
            value is not None for value in evidence_values
        ):
            raise ValueError(
                "an assessment that is not required must not claim a table or evidence"
            )
        if (
            self.selected_table is not None
            and self.method != ContainmentMethod.TABLES_8_TO_13
        ):
            raise ValueError("selected_table requires the tables_8_to_13 method")
        if self.within_specific_category_method_scope != (
            self.required_robustness != ContainmentRobustness.OUT_OF_SCOPE
        ):
            raise ValueError(
                "method-scope flag must be false exactly for out-of-scope containment"
            )
        if (
            self.required_robustness
            in {
                ContainmentRobustness.MEDIUM,
                ContainmentRobustness.HIGH,
            }
            and not self.ground_risk_buffer_revalidation_reference
        ):
            raise ValueError(
                "medium/high containment requires a GRB revalidation reference"
            )
        return self


class SoraAssessment(BaseModel):
    """Whole-mission SORA pre-assessment result."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    mission_id: str
    assessment_scope: Literal["requirements_identification_only"] = (
        "requirements_identification_only"
    )
    sora_version: SupportedSoraVersion = DEFAULT_SORA_VERSION
    characteristic_dimension_m: FiniteFloat | None = None
    max_speed_mps: FiniteFloat | None = None
    aircraft_mass_kg: FiniteFloat | None = Field(default=None, gt=0)
    ground_risk_footprint: GroundRiskFootprint
    population_evidence: PopulationEvidenceSummary
    population_numerical_dilation_m: FiniteFloat = Field(ge=0)
    intrinsic_grc: int | None = None
    final_grc: int | None = None
    ground_risk_mitigations: list[GrcMitigationCredit] = Field(default_factory=list)
    operational_and_contingency_volume_assessment_reference: str = Field(min_length=1)
    worst_case_arc_declared: Literal[True]
    initial_air_risk_class: AirRiskClass | None = None
    air_risk_class: AirRiskClass | None = None
    air_risk_rationale: str | None = None
    strategic_mitigation_applied: bool = False
    tactical_mitigation_requirement: TacticalMitigationRequirement | None = None
    intrinsic_sail: Sail | None = None
    sail: Sail | None = None
    category_outcome: Literal[
        "specific",
        "specific_method_out_of_scope",
        "certified",
    ]
    containment_requirement: ContainmentRequirement
    applicable_osos: list[OsoRequirement] = Field(default_factory=list)
    oso_compliance_status: Literal["not_assessed"] = "not_assessed"
    complete_sora_assessment: Literal[False] = False
    within_specific_category_method_scope: StrictBool
    advisories: list[SoraAdvisory] = Field(default_factory=list)
    disclaimer: str = SORA_NON_CERTIFICATION_DISCLAIMER

    @model_validator(mode="after")
    def validate_outcome_consistency(self) -> "SoraAssessment":
        certified = self.category_outcome == "certified"
        if certified != (self.sail is None):
            raise ValueError("certified category outcome must have no SAIL")
        if certified and (self.final_grc is None or self.final_grc <= 7):
            raise ValueError("certified category outcome requires final GRC above 7")
        expected_scope = (
            self.sail is not None
            and self.containment_requirement.within_specific_category_method_scope
        )
        if self.within_specific_category_method_scope != expected_scope:
            raise ValueError(
                "assessment method scope must agree with SAIL and containment"
            )
        expected_category = (
            "certified"
            if self.sail is None
            else ("specific" if expected_scope else "specific_method_out_of_scope")
        )
        if self.category_outcome != expected_category:
            raise ValueError("category outcome contradicts the method-scope result")
        if self.sail is None and self.applicable_osos:
            raise ValueError("an operation without a SAIL cannot have applicable OSOs")
        return self


__all__ = [
    "DEFAULT_SORA_VERSION",
    "SORA_ASSESSMENT_SCHEMA_VERSION",
    "SORA_NON_CERTIFICATION_DISCLAIMER",
    "AirRiskClass",
    "AirRiskMitigations",
    "AdjacentAreaContainmentEvidence",
    "ContainmentRequirement",
    "ContainmentMethod",
    "ContainmentRobustness",
    "GrcMitigationCredit",
    "GrcMitigationCreditStatus",
    "GroundRiskFootprint",
    "GroundRiskMitigation",
    "GroundRiskMitigations",
    "MitigationRobustness",
    "OsoPartyDependencies",
    "OsoPartyDependency",
    "OsoRequirement",
    "OutdoorAssemblyCategory",
    "OutdoorAssemblyOperationalLimit",
    "PopulationDensityOperationalLimit",
    "PopulationEvidenceSummary",
    "RobustnessLevel",
    "Sail",
    "SoraAdvisory",
    "SoraAdvisoryCode",
    "SoraAssessment",
    "SoraMitigations",
    "SupportedSoraVersion",
    "TacticalMitigationRequirement",
]
