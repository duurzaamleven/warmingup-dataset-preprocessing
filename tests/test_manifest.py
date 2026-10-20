# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pandas as pd

from warmingup_preprocessing.manifest import Manifest, sha256_van_bestand, schrijf_parquet_atomisch


def test_manifest_voeg_toe_en_is_voltooid(tmp_path: Path):
    uit_dir = tmp_path
    df = pd.DataFrame({"a": [1, 2, 3]})
    pad = uit_dir / "iets.parquet"
    schrijf_parquet_atomisch(pad, df)

    manifest = Manifest(uit_dir)
    assert not manifest.is_voltooid("test", "sleutel1", uit_dir)
    manifest.voeg_toe("test", "sleutel1", pad, uit_dir, rijen=len(df))
    assert manifest.is_voltooid("test", "sleutel1", uit_dir)


def test_manifest_persisteert_over_herladen(tmp_path: Path):
    uit_dir = tmp_path
    df = pd.DataFrame({"a": [1, 2, 3]})
    pad = uit_dir / "iets.parquet"
    schrijf_parquet_atomisch(pad, df)

    manifest1 = Manifest(uit_dir)
    manifest1.voeg_toe("test", "sleutel1", pad, uit_dir, rijen=len(df))

    manifest2 = Manifest(uit_dir)
    assert manifest2.is_voltooid("test", "sleutel1", uit_dir)
    assert manifest2.totaal_rijen("test") == 3


def test_manifest_niet_voltooid_als_bestand_ontbreekt(tmp_path: Path):
    uit_dir = tmp_path
    df = pd.DataFrame({"a": [1]})
    pad = uit_dir / "iets.parquet"
    schrijf_parquet_atomisch(pad, df)
    manifest = Manifest(uit_dir)
    manifest.voeg_toe("test", "sleutel1", pad, uit_dir, rijen=1)
    pad.unlink()
    manifest2 = Manifest(uit_dir)
    assert not manifest2.is_voltooid("test", "sleutel1", uit_dir)


def test_schrijf_parquet_atomisch_laat_geen_tmp_achter(tmp_path: Path):
    pad = tmp_path / "iets.parquet"
    schrijf_parquet_atomisch(pad, pd.DataFrame({"a": [1]}))
    assert pad.is_file()
    assert not pad.with_suffix(pad.suffix + ".tmp").exists()


def test_sha256_is_deterministisch(tmp_path: Path):
    pad = tmp_path / "bestand.txt"
    pad.write_text("hallo")
    assert sha256_van_bestand(pad) == sha256_van_bestand(pad)
