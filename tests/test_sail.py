import pytest

from bvlos_sim.estimator.execution.sail import applicable_osos, determine_sail
from bvlos_sim.schemas.sora import AirRiskClass, RobustnessLevel, Sail

# Independent transcription of the SORA SAIL determination table, rows = final
# GRC, columns = residual ARC (a, b, c, d). Every cell is asserted below.
_EXPECTED_SAIL = {
    1: (Sail.I, Sail.II, Sail.IV, Sail.VI),
    2: (Sail.I, Sail.II, Sail.IV, Sail.VI),
    3: (Sail.II, Sail.II, Sail.IV, Sail.VI),
    4: (Sail.III, Sail.III, Sail.IV, Sail.VI),
    5: (Sail.IV, Sail.IV, Sail.IV, Sail.VI),
    6: (Sail.V, Sail.V, Sail.V, Sail.VI),
    7: (Sail.VI, Sail.VI, Sail.VI, Sail.VI),
}

_ARC_COLUMNS = (AirRiskClass.A, AirRiskClass.B, AirRiskClass.C, AirRiskClass.D)


@pytest.mark.parametrize("grc", sorted(_EXPECTED_SAIL))
@pytest.mark.parametrize("column", range(4))
def test_determine_sail_every_cell(grc: int, column: int) -> None:
    arc = _ARC_COLUMNS[column]
    assert determine_sail(grc, arc) == _EXPECTED_SAIL[grc][column]


@pytest.mark.parametrize("grc", [8, 9, 20])
@pytest.mark.parametrize("arc", _ARC_COLUMNS)
def test_grc_above_seven_is_certified_category(grc: int, arc: AirRiskClass) -> None:
    assert determine_sail(grc, arc) is None


@pytest.mark.parametrize("grc", [0, -1, -100])
def test_grc_below_one_is_rejected(grc: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        determine_sail(grc, AirRiskClass.A)


@pytest.mark.parametrize("grc", [True, False, 1.0, "1", None])
def test_determine_sail_rejects_bool_and_non_integer_grc(grc: object) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        determine_sail(grc, AirRiskClass.A)  # type: ignore[arg-type]


def test_table_14_emits_all_rows_including_not_required() -> None:
    osos = applicable_osos(Sail.II)
    assert len(osos) == 17
    oso04 = next(oso for oso in osos if oso.oso_id == "OSO#04")
    assert oso04.robustness == RobustnessLevel.NOT_REQUIRED
    assert oso04.required is False
    assert all(
        oso.required == (oso.robustness != RobustnessLevel.NOT_REQUIRED) for oso in osos
    )


def test_applicable_osos_grows_with_sail() -> None:
    counts = [len(applicable_osos(s)) for s in (Sail.I, Sail.III, Sail.VI)]
    assert counts == [17, 17, 17]


def test_sora_25_table_14_has_consolidated_oso_set() -> None:
    assert {oso.oso_id for oso in applicable_osos(Sail.VI)} == {
        "OSO#01",
        "OSO#02",
        "OSO#03",
        "OSO#04",
        "OSO#05",
        "OSO#06",
        "OSO#07",
        "OSO#08",
        "OSO#09",
        "OSO#13",
        "OSO#16",
        "OSO#17",
        "OSO#18",
        "OSO#19",
        "OSO#20",
        "OSO#23",
        "OSO#24",
    }


def test_sora_25_table_14_corrected_cells() -> None:
    sail_ii = {oso.oso_id: oso.robustness for oso in applicable_osos(Sail.II)}
    sail_iv = {oso.oso_id: oso.robustness for oso in applicable_osos(Sail.IV)}

    assert sail_ii["OSO#06"] == RobustnessLevel.LOW
    assert sail_iv["OSO#04"] == RobustnessLevel.LOW


def test_sora_25_table_14_exact_robustness_rows() -> None:
    expected = {
        "OSO#01": "NRLMHHH",
        "OSO#02": "NRNRLMHH",
        "OSO#03": "LLMMHH",
        "OSO#04": "NRNRNRLMH",
        "OSO#05": "NRNRLMHH",
        "OSO#06": "NRLLMHH",
        "OSO#07": "LLMMHH",
        "OSO#08": "LMHHHH",
        "OSO#09": "LLMMHH",
        "OSO#13": "LLMHHH",
        "OSO#16": "LLMMHH",
        "OSO#17": "LLMMHH",
        "OSO#18": "NRNRLMHH",
        "OSO#19": "NRNRLMMH",
        "OSO#20": "NRLLMMH",
        "OSO#23": "LLMMHH",
        "OSO#24": "NRNRMHHH",
    }
    sails = (Sail.I, Sail.II, Sail.III, Sail.IV, Sail.V, Sail.VI)

    actual = {
        oso_id: "".join(
            next(
                oso for oso in applicable_osos(sail) if oso.oso_id == oso_id
            ).robustness.value
            for sail in sails
        )
        for oso_id in expected
    }
    assert actual == expected


def _dependency_signature(oso_id: str) -> tuple[object, object, object]:
    oso = next(oso for oso in applicable_osos(Sail.I) if oso.oso_id == oso_id)

    def value(dependency) -> object:
        if not dependency.applicable:
            return None
        return tuple(dependency.criterion_refs)

    dependencies = oso.party_dependencies
    return (
        value(dependencies.operator),
        value(dependencies.training_organisation),
        value(dependencies.designer),
    )


def test_sora_25_table_14_exact_party_dependencies() -> None:
    # Empty tuple is Table 14's plain X; None is a dash; integers are criterion refs.
    assert {
        oso.oso_id: _dependency_signature(oso.oso_id) for oso in applicable_osos(Sail.I)
    } == {
        "OSO#01": ((), None, None),
        "OSO#02": (None, None, ()),
        "OSO#03": ((1, 2), None, (1,)),
        "OSO#04": (None, None, ()),
        "OSO#05": (None, None, ()),
        "OSO#06": ((), None, ()),
        "OSO#07": ((1, 2), None, (1,)),
        "OSO#08": ((), None, (1,)),
        "OSO#09": ((), (), None),
        "OSO#13": ((), None, None),
        "OSO#16": ((1, 3), (2,), None),
        "OSO#17": ((), None, None),
        "OSO#18": (None, None, ()),
        "OSO#19": (None, None, ()),
        "OSO#20": ((), None, ()),
        "OSO#23": ((), None, ()),
        "OSO#24": (None, None, ()),
    }


def test_sora_25_table_14_preserves_oso05_sail_ii_note() -> None:
    for sail in (Sail.I, Sail.III, Sail.IV, Sail.V, Sail.VI):
        oso05 = next(oso for oso in applicable_osos(sail) if oso.oso_id == "OSO#05")
        assert oso05.note_refs == []
    oso05_sail_ii = next(
        oso for oso in applicable_osos(Sail.II) if oso.oso_id == "OSO#05"
    )
    assert oso05_sail_ii.note_refs == ["4.9.3(c)"]


def test_certified_category_is_not_a_sail_for_oso_lookup() -> None:
    with pytest.raises(TypeError, match="SAIL I-VI"):
        applicable_osos(None)  # type: ignore[arg-type]
