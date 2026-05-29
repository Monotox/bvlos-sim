import pytest

from estimator.execution.air_risk import compute_air_risk, initial_air_risk_class
from schemas.mission import Airspace
from schemas.sora import AirRiskClass


def _airspace(**overrides) -> Airspace:
    payload = {"class": "G", "max_altitude_agl_m": 120.0}
    payload.update(overrides)
    return Airspace.model_validate(payload)


@pytest.mark.parametrize(
    ("airspace_class", "altitude_m", "expected"),
    [
        ("G", 120.0, AirRiskClass.B),
        ("F", 120.0, AirRiskClass.B),
        ("G", 200.0, AirRiskClass.C),
        ("F", 200.0, AirRiskClass.C),
        ("E", 120.0, AirRiskClass.C),
        ("D", 120.0, AirRiskClass.C),
        ("A", 120.0, AirRiskClass.C),
        ("E", 200.0, AirRiskClass.D),
        ("C", 200.0, AirRiskClass.D),
        ("B", 200.0, AirRiskClass.D),
    ],
)
def test_initial_arc_by_class_and_altitude(
    airspace_class: str, altitude_m: float, expected: AirRiskClass
) -> None:
    arc, _ = initial_air_risk_class(
        _airspace(**{"class": airspace_class}, max_altitude_agl_m=altitude_m)
    )
    assert arc == expected


def test_arc_500ft_boundary_is_low_altitude() -> None:
    # Exactly 500 ft AGL counts as the low-altitude band.
    at_ceiling, _ = initial_air_risk_class(_airspace(max_altitude_agl_m=152.4))
    above_ceiling, _ = initial_air_risk_class(_airspace(max_altitude_agl_m=152.5))
    assert at_ceiling == AirRiskClass.B
    assert above_ceiling == AirRiskClass.C


def test_near_aerodrome_raises_arc_to_d() -> None:
    arc, _ = initial_air_risk_class(_airspace(near_aerodrome=True))
    assert arc == AirRiskClass.D


def test_atypical_or_segregated_is_arc_a() -> None:
    arc, _ = initial_air_risk_class(_airspace(atypical_or_segregated=True))
    assert arc == AirRiskClass.A


def test_atypical_takes_precedence_over_near_aerodrome() -> None:
    arc, _ = initial_air_risk_class(
        _airspace(atypical_or_segregated=True, near_aerodrome=True)
    )
    assert arc == AirRiskClass.A


@pytest.mark.parametrize(
    ("overrides", "initial", "residual"),
    [
        ({"class": "C", "max_altitude_agl_m": 200.0}, AirRiskClass.D, AirRiskClass.C),
        ({"class": "G", "max_altitude_agl_m": 120.0}, AirRiskClass.B, AirRiskClass.A),
        ({"atypical_or_segregated": True}, AirRiskClass.A, AirRiskClass.A),
    ],
)
def test_strategic_mitigation_lowers_one_band_with_floor(
    overrides: dict, initial: AirRiskClass, residual: AirRiskClass
) -> None:
    assessment = compute_air_risk(_airspace(strategic_mitigation=True, **overrides))
    assert assessment.initial_arc == initial
    assert assessment.residual_arc == residual
    assert assessment.strategic_mitigation_applied == (initial != AirRiskClass.A)


def test_no_strategic_mitigation_keeps_initial_arc() -> None:
    assessment = compute_air_risk(_airspace(**{"class": "C"}, max_altitude_agl_m=200.0))
    assert assessment.initial_arc == AirRiskClass.D
    assert assessment.residual_arc == AirRiskClass.D
    assert assessment.strategic_mitigation_applied is False
