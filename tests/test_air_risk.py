import pytest
from pydantic import ValidationError

from estimator.execution.air_risk import compute_air_risk, initial_air_risk_class
from schemas.mission import Airspace
from schemas.sora import AirRiskClass, GroundRiskMitigation, MitigationRobustness


def _airspace(**overrides) -> Airspace:
    payload = {
        "class": "G",
        "max_altitude_agl_m": 120.0,
        "over_urban_area": False,
        "operational_and_contingency_volume_assessment_reference": (
            "Test whole-volume airspace assessment"
        ),
        "worst_case_arc_declared": True,
        "aerodrome_environment": False,
        "transponder_mandatory_zone": False,
    }
    payload.update(overrides)
    return Airspace.model_validate(payload)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"class": "G", "over_urban_area": False}, AirRiskClass.B),
        ({"class": "F", "over_urban_area": False}, AirRiskClass.B),
        ({"class": "G", "over_urban_area": True}, AirRiskClass.C),
        ({"class": "E"}, AirRiskClass.C),
        ({"class": "G", "max_altitude_agl_m": 200.0}, AirRiskClass.C),
        ({"class": "E", "max_altitude_agl_m": 200.0}, AirRiskClass.D),
        ({"transponder_mandatory_zone": True}, AirRiskClass.C),
        (
            {"transponder_mandatory_zone": True, "max_altitude_agl_m": 200.0},
            AirRiskClass.D,
        ),
    ],
)
def test_initial_arc_matches_sora_25_aec_table(
    payload: dict[str, object], expected: AirRiskClass
) -> None:
    arc, _ = initial_air_risk_class(_airspace(**payload))
    assert arc == expected


def test_arc_500ft_boundary_is_conservatively_high_altitude() -> None:
    at_ceiling, _ = initial_air_risk_class(_airspace(max_altitude_agl_m=152.4))
    above_ceiling, _ = initial_air_risk_class(_airspace(max_altitude_agl_m=152.5))
    assert at_ceiling == AirRiskClass.C
    assert above_ceiling == AirRiskClass.C


@pytest.mark.parametrize(
    ("airspace_class", "expected"),
    [
        ("A", AirRiskClass.C),
        ("B", AirRiskClass.D),
        ("C", AirRiskClass.D),
        ("D", AirRiskClass.D),
        ("E", AirRiskClass.C),
        ("F", AirRiskClass.C),
        ("G", AirRiskClass.C),
    ],
)
def test_aerodrome_arc_depends_on_airspace_class(
    airspace_class: str, expected: AirRiskClass
) -> None:
    arc, _ = initial_air_risk_class(
        _airspace(**{"class": airspace_class}, aerodrome_environment=True)
    )
    assert arc == expected


def test_atypical_or_segregated_arc_a_claim_is_rejected() -> None:
    with pytest.raises(ValidationError, match="authority-backed"):
        _airspace(atypical_or_segregated=True, aerodrome_environment=True)


def test_entirely_above_flight_level_600_claim_is_rejected() -> None:
    with pytest.raises(ValidationError, match="pressure-altitude"):
        _airspace(
            **{"class": "A"},
            max_altitude_agl_m=19_000.0,
            entirely_above_flight_level_600=True,
        )


def test_ambiguous_old_above_flight_level_600_flag_is_rejected() -> None:
    with pytest.raises(ValidationError, match="above_flight_level_600"):
        _airspace(above_flight_level_600=True)


def test_uncontrolled_low_altitude_requires_urban_rural_descriptor() -> None:
    with pytest.raises(ValidationError, match="over_urban_area is required"):
        _airspace(over_urban_area=None)


@pytest.mark.parametrize(
    "missing_field",
    [
        "operational_and_contingency_volume_assessment_reference",
        "worst_case_arc_declared",
    ],
)
def test_airspace_requires_whole_volume_evidence(missing_field: str) -> None:
    payload = {
        "class": "G",
        "max_altitude_agl_m": 120.0,
        "over_urban_area": False,
        "operational_and_contingency_volume_assessment_reference": (
            "Test whole-volume airspace assessment"
        ),
        "worst_case_arc_declared": True,
        "aerodrome_environment": False,
        "transponder_mandatory_zone": False,
    }
    del payload[missing_field]
    with pytest.raises(ValidationError, match=missing_field):
        Airspace.model_validate(payload)


def test_airspace_assessment_reference_must_not_be_blank() -> None:
    with pytest.raises(ValidationError, match="must not be blank"):
        _airspace(operational_and_contingency_volume_assessment_reference="   ")


def test_airspace_worst_case_declaration_must_be_true() -> None:
    with pytest.raises(ValidationError, match="worst_case_arc_declared"):
        _airspace(worst_case_arc_declared=False)


@pytest.mark.parametrize(
    "missing_field", ["aerodrome_environment", "transponder_mandatory_zone"]
)
def test_airspace_requires_risk_increasing_descriptors(missing_field: str) -> None:
    payload = _airspace().model_dump(by_alias=True)
    del payload[missing_field]

    with pytest.raises(ValidationError, match=missing_field):
        Airspace.model_validate(payload)


@pytest.mark.parametrize(
    "field", ["aerodrome_environment", "transponder_mandatory_zone"]
)
def test_airspace_rejects_coerced_boolean_descriptors(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        _airspace(**{field: "false"})


def test_boolean_strategic_credit_is_rejected() -> None:
    with pytest.raises(ValidationError, match="evidence-backed"):
        _airspace(strategic_mitigation=True)


@pytest.mark.parametrize(
    ("airspace", "expected_arc", "expected_tmpr"),
    [
        ({}, AirRiskClass.B, MitigationRobustness.LOW),
        ({"over_urban_area": True}, AirRiskClass.C, MitigationRobustness.MEDIUM),
        (
            {"class": "C", "max_altitude_agl_m": 300.0},
            AirRiskClass.D,
            MitigationRobustness.HIGH,
        ),
    ],
)
def test_residual_arc_drives_tmpr_without_tactical_arc_credit(
    airspace: dict[str, object],
    expected_arc: AirRiskClass,
    expected_tmpr: MitigationRobustness,
) -> None:
    assessment = compute_air_risk(_airspace(**airspace))
    assert assessment.initial_arc == expected_arc
    assert assessment.residual_arc == expected_arc
    assert assessment.tmpr_required_robustness == expected_tmpr


def test_tactical_mitigation_cannot_lower_arc() -> None:
    tactical = GroundRiskMitigation(
        applied=True,
        robustness=MitigationRobustness.HIGH,
        evidence="Test DAA dossier",
    )
    with pytest.raises(ValueError, match="cannot be used to lower"):
        compute_air_risk(_airspace(), tactical=tactical)


def test_unsupported_methodology_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported SORA version"):
        compute_air_risk(_airspace(), sora_version="2.0")


def test_tmz_rationale_uses_mode_c_wording() -> None:
    _, rationale = initial_air_risk_class(_airspace(transponder_mandatory_zone=True))
    assert "Mode-C" in rationale
    assert "Mode-S" not in rationale


def test_controlled_tmz_must_be_declared_aerodrome_environment() -> None:
    with pytest.raises(ValidationError, match="aerodrome_environment"):
        _airspace(
            **{"class": "C"},
            transponder_mandatory_zone=True,
            aerodrome_environment=False,
        )

    arc, _ = initial_air_risk_class(
        _airspace(
            **{"class": "C"},
            transponder_mandatory_zone=True,
            aerodrome_environment=True,
        )
    )
    assert arc == AirRiskClass.D
