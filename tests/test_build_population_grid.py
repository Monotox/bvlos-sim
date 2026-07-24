"""build_population_grid.py must emit loader-accepted population-grid.v2."""

from pathlib import Path

import pytest
import yaml

from bvlos_sim.adapters.assets.population_grid import load_population_grid
from bvlos_sim.scripts import build_population_grid


_METADATA_ARGS = [
    "--source",
    "Authority-approved conservative population map",
    "--population-year",
    "2026",
    "--native-resolution-m",
    "100",
    "--authority-assessment-reference",
    "POP-2026-014",
    "--valid-from",
    "2026-01-01T00:00:00Z",
    "--valid-until",
    "2026-12-31T23:59:59Z",
    "--transient-population-assessment-reference",
    "EVENTS-2026-008",
    "--assemblies-present",
    "false",
]


def _run(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["build_population_grid.py", *argv])
    build_population_grid.main()


def _asc(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "ncols 4",
                "nrows 4",
                "xllcorner 4.0",
                "yllcorner 52.0",
                "cellsize 0.005",
                "NODATA_value -9999",
                "10 20 30 40",
                "50 900 70 80",
                "90 100 110 120",
                "130 140 150 160",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_asc_max_pooling_and_loader_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _asc(tmp_path / "population.asc")
    output = tmp_path / "grid.yaml"
    _run(
        [
            "52.0",
            "52.02",
            "4.0",
            "4.02",
            "--step-deg",
            "0.01",
            "--input",
            str(source),
            "--output",
            str(output),
            *_METADATA_ARGS,
        ],
        monkeypatch,
    )

    provider, document = load_population_grid(output)
    assert document.path == output
    # ESRI row 2 holds 900 at the grid's north-west quadrant; max pooling
    # must surface it in the corresponding output cell.
    text = output.read_text(encoding="utf-8")
    assert "900.0" in text
    assert "value_semantics: conservative_cell_maximum" in text
    assert provider is not None


def test_csv_input_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "population.csv"
    source.write_text(
        "lat,lon,density\n"
        "52.002,4.002,12\n52.002,4.007,44\n52.007,4.002,7\n52.007,4.007,3\n",
        encoding="utf-8",
    )
    output = tmp_path / "grid.yaml"
    _run(
        [
            "52.0",
            "52.01",
            "4.0",
            "4.01",
            "--step-deg",
            "0.005",
            "--input",
            str(source),
            "--output",
            str(output),
            *_METADATA_ARGS,
        ],
        monkeypatch,
    )
    load_population_grid(output)


def test_uncovered_cell_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "population.csv"
    source.write_text("52.002,4.002,12\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        _run(
            [
                "52.0",
                "52.01",
                "4.0",
                "4.01",
                "--step-deg",
                "0.005",
                "--input",
                str(source),
                "--output",
                str(tmp_path / "grid.yaml"),
                *_METADATA_ARGS,
            ],
            monkeypatch,
        )


def test_missing_metadata_flag_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _asc(tmp_path / "population.asc")
    with pytest.raises(SystemExit):
        _run(
            [
                "52.0",
                "52.02",
                "4.0",
                "4.02",
                "--step-deg",
                "0.01",
                "--input",
                str(source),
            ],
            monkeypatch,
        )


def test_metadata_with_quotes_survives_the_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence metadata was emitted with repr(), which is Python, not YAML."""

    source_csv = tmp_path / "pop.csv"
    rows = ["lat,lon,density_ppl_km2"]
    for i in range(5):
        for j in range(5):
            rows.append(f"{52.0 + 0.0005 * i},{4.0 + 0.0005 * j},{10.0 + i + j}")
    source_csv.write_text("\n".join(rows) + "\n", encoding="utf-8")
    out = tmp_path / "population.yaml"

    _run(
        [
            "52.0",
            "52.002",
            "4.0",
            "4.002",
            "--step-deg",
            "0.001",
            "--input",
            str(source_csv),
            "--output",
            str(out),
            "--source",
            'Agency "official" map, v2',
            "--population-year",
            "2026",
            "--native-resolution-m",
            "100",
            "--authority-assessment-reference",
            "REF-1: it's fine",
            "--valid-from",
            "2026-01-01T00:00:00Z",
            "--valid-until",
            "2026-12-31T23:59:59Z",
            "--transient-population-assessment-reference",
            "TR-1",
            "--assemblies-present",
            "false",
        ],
        monkeypatch,
    )

    document = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert document["metadata"]["source"] == 'Agency "official" map, v2'
    assert document["metadata"]["authority_assessment_reference"] == "REF-1: it's fine"
    # And the emitted evidence still loads through the real asset loader.
    load_population_grid(out)
