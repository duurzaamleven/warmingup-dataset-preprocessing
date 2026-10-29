# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pandas as pd
import pytest

from warmingup_preprocessing import pijplijn


def test_run_volledig_op_kleine_synthetische_zip(test_zip_gesorteerd: Path, tmp_path: Path):
    uit_dir = tmp_path / "processed"
    docs_dir = tmp_path / "docs"
    resultaat = pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=docs_dir)

    assert (uit_dir / "boiler_temp" / "home_id=WU0.parquet").is_file()
    assert (uit_dir / "thermostat_temp" / "home_id=WU0.parquet").is_file()
    assert (uit_dir / "etmaal.parquet").is_file()
    assert not (uit_dir / "mapping.parquet").exists()
    assert (uit_dir / "resultaten.parquet").is_file()
    assert (uit_dir / "info_metadata.parquet").is_file()
    assert (uit_dir / "dekking.parquet").is_file()
    assert (uit_dir / "_manifest.jsonl").is_file()
    assert (uit_dir / "_voortgang.json").is_file()
    assert (uit_dir / "datapackage.json").is_file()
    assert (docs_dir / "data-quality.md").is_file()

    resultaten_df = pd.read_parquet(uit_dir / "resultaten.parquet")
    assert len(resultaten_df) == 3
    assert not {"logger_id__str", "serial_no__str", "heater_id__str"} & set(resultaten_df.columns)
    assert resultaat["duur__s"] > 0


def test_run_hervat_voegt_niets_dubbel_toe(test_zip_gesorteerd: Path, tmp_path: Path):
    uit_dir = tmp_path / "processed"
    pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None)

    manifest_pad = uit_dir / "_manifest.jsonl"
    regels_voor = manifest_pad.read_text(encoding="utf-8").splitlines()

    pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None)
    regels_na = manifest_pad.read_text(encoding="utf-8").splitlines()

    # boiler_temp/thermostat_temp/etmaal/resultaten/info_metadata staan al: alleen
    # "dekking" wordt bij elke run herbouwd (zie pijplijn.run), dus er komt hoogstens één regel bij.
    assert len(regels_na) <= len(regels_voor) + 1


def test_run_opnieuw_bouwt_alles_opnieuw(test_zip_gesorteerd: Path, tmp_path: Path):
    uit_dir = tmp_path / "processed"
    pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None)
    pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None, opnieuw=True)
    assert (uit_dir / "boiler_temp" / "home_id=WU0.parquet").is_file()


def test_run_test_mb_beperkt_het_gelezen_volume(test_zip_gesorteerd: Path, tmp_path: Path):
    uit_dir = tmp_path / "processed"
    resultaat = pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None, test_mb=1)
    assert (uit_dir / "boiler_temp").is_dir()


def test_schijfruimtefout_bij_te_weinig_ruimte(test_zip_gesorteerd: Path, tmp_path: Path, monkeypatch):
    import shutil as shutil_mod

    class _Nep:
        free = 1  # 1 byte vrij: altijd te weinig

    monkeypatch.setattr(shutil_mod, "disk_usage", lambda _pad: _Nep())
    uit_dir = tmp_path / "processed"
    with pytest.raises(pijplijn.SchijfruimteFout):
        pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None)


def test_droogloop_schrijft_niets(test_zip_gesorteerd: Path, tmp_path: Path, capsys):
    uit_dir = tmp_path / "processed"
    resultaat = pijplijn.run(test_zip_gesorteerd.parent, uit_dir, docs_dir=None, droogloop=True)
    assert resultaat == {"droogloop": True}
    assert not uit_dir.exists()
    uitvoer = capsys.readouterr().out
    assert "Droogloop" in uitvoer
