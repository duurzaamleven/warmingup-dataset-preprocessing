# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de migratie van een bestaande uitvoermap (oude contractversie) naar de huidige, zonder
de ruwe brondata opnieuw te lezen. Zie migreer.py voor de motivatie en het mechanisme (hergebruikt
Manifest.is_voltooid voor hervatbaarheid/idempotentie).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from warmingup_preprocessing import migreer
from warmingup_preprocessing.manifest import UITVOER_CONTRACT_VERSIE, Manifest, sha256_van_bestand

OUDE_CONTRACT = "2026-09-23-eerste-opzet"

#: Zelfde schema als de oude contractversie: GEEN q_flag_tijdstip_dubbel__bool, tijdstip in UTC.
_OUDE_BOILER_TEMP_SCHEMA = pa.schema(
    [
        ("home_id__str", pa.string()),
        ("tijdstip", pa.timestamp("ns", tz="UTC")),
        ("temp_aanvoer__degC", pa.float32()),
        ("temp_retour__degC", pa.float32()),
        ("debiet_ruw__l_h", pa.float64()),
        ("debiet__dm3_s_1", pa.float32()),
        ("q_afgifte__W", pa.float32()),
        ("q_flag_debiet_sentinel__bool", pa.bool_()),
        ("q_flag_debiet_bovengrens__bool", pa.bool_()),
        ("q_flag_temp_aanvoer_ontbrekend__bool", pa.bool_()),
        ("q_flag_temp_retour_ontbrekend__bool", pa.bool_()),
        ("q_flag_temp_aanvoer_bereik__bool", pa.bool_()),
        ("q_flag_temp_retour_bereik__bool", pa.bool_()),
    ]
)


def _schrijf_oud_boiler_temp(pad: Path, home: str, tijden: list[str], met_dubbel: bool = False) -> int:
    n = len(tijden)
    df = pd.DataFrame(
        {
            "home_id__str": [home] * n,
            "tijdstip": pd.to_datetime(tijden, utc=True),
            "temp_aanvoer__degC": [40.0 + i % 5 for i in range(n)],
            "temp_retour__degC": [30.0] * n,
            "debiet_ruw__l_h": [300.0] * n,
            "debiet__dm3_s_1": [300.0 / 3600.0] * n,
            "q_afgifte__W": [100.0] * n,
            "q_flag_debiet_sentinel__bool": [False] * n,
            "q_flag_debiet_bovengrens__bool": [False] * n,
            "q_flag_temp_aanvoer_ontbrekend__bool": [False] * n,
            "q_flag_temp_retour_ontbrekend__bool": [False] * n,
            "q_flag_temp_aanvoer_bereik__bool": [False] * n,
            "q_flag_temp_retour_bereik__bool": [False] * n,
        }
    )
    tabel = pa.Table.from_pandas(df, preserve_index=False).select(_OUDE_BOILER_TEMP_SCHEMA.names).cast(_OUDE_BOILER_TEMP_SCHEMA)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabel, pad, compression="zstd")
    return n


def _schrijf_oude_manifestregel(uit_dir: Path, onderdeel: str, sleutel: str, relpad: str) -> None:
    pad = uit_dir / relpad
    regel = {
        "onderdeel": onderdeel,
        "sleutel": sleutel,
        "pad": relpad,
        "sha256": sha256_van_bestand(pad),
        "rijen": pq.ParquetFile(pad).metadata.num_rows,
        "contract": OUDE_CONTRACT,
        "voltooid_op": "2026-09-23T10:00:00+00:00",
    }
    with (uit_dir / "_manifest.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(regel, ensure_ascii=False) + "\n")


@pytest.fixture
def oude_uitvoermap(tmp_path: Path) -> Path:
    uit_dir = tmp_path / "oud"
    # WU0: twee identieke tijdstempels (moet na migratie één keer True krijgen op de dedupvlag).
    tijden_wu0 = ["2021-01-01T00:00:00Z", "2021-01-01T00:01:00Z", "2021-01-01T00:00:00Z"]
    _schrijf_oud_boiler_temp(uit_dir / "boiler_temp" / "home_id=WU0.parquet", "WU0", tijden_wu0)
    _schrijf_oude_manifestregel(uit_dir, "boiler_temp", "WU0", "boiler_temp/home_id=WU0.parquet")

    tijden_wu1 = ["2021-01-01T00:00:00Z", "2021-01-01T00:01:00Z"]
    _schrijf_oud_boiler_temp(uit_dir / "boiler_temp" / "home_id=WU1.parquet", "WU1", tijden_wu1)
    _schrijf_oude_manifestregel(uit_dir, "boiler_temp", "WU1", "boiler_temp/home_id=WU1.parquet")

    # resultaten.parquet met int64 logger_id__str (het oude gedrag).
    resultaten = pd.DataFrame({"home_id__str": ["WU0", "WU1"], "logger_id__str": [20000001, 20000002]})
    resultaten_pad = uit_dir / "resultaten.parquet"
    resultaten_pad.parent.mkdir(parents=True, exist_ok=True)
    resultaten.to_parquet(resultaten_pad, index=False)
    _schrijf_oude_manifestregel(uit_dir, "resultaten", "resultaten", "resultaten.parquet")

    return uit_dir


def test_migratie_zet_tijdzone_om_en_voegt_dedupvlag_toe(oude_uitvoermap: Path):
    migreer.migreer(oude_uitvoermap, docs_dir=None)

    df0 = pd.read_parquet(oude_uitvoermap / "boiler_temp" / "home_id=WU0.parquet")
    assert str(df0["tijdstip"].dt.tz) == "Europe/Amsterdam"
    assert df0["q_flag_tijdstip_dubbel__bool"].tolist() == [False, False, True]
    # Instant onveranderd: eerste tijdstip is 2021-01-01T00:00:00Z, in de winter UTC+1.
    assert df0["tijdstip"].iloc[0].hour == 1

    df1 = pd.read_parquet(oude_uitvoermap / "boiler_temp" / "home_id=WU1.parquet")
    assert df1["q_flag_tijdstip_dubbel__bool"].tolist() == [False, False]


def test_migratie_cast_logger_id_naar_string(oude_uitvoermap: Path):
    migreer.migreer(oude_uitvoermap, docs_dir=None)
    resultaten = pd.read_parquet(oude_uitvoermap / "resultaten.parquet")
    assert resultaten["logger_id__str"].tolist() == ["20000001", "20000002"]


def test_migratie_werkt_manifest_bij_naar_nieuwe_contractversie(oude_uitvoermap: Path):
    migreer.migreer(oude_uitvoermap, docs_dir=None)
    manifest = Manifest(oude_uitvoermap)
    assert manifest.is_voltooid("boiler_temp", "WU0", oude_uitvoermap)
    assert manifest.is_voltooid("boiler_temp", "WU1", oude_uitvoermap)
    assert manifest.is_voltooid("resultaten", "resultaten", oude_uitvoermap)


def test_migratie_schrijft_dekking_en_datapackage(oude_uitvoermap: Path):
    resultaat = migreer.migreer(oude_uitvoermap, docs_dir=None)
    assert (oude_uitvoermap / "dekking.parquet").is_file()
    assert (oude_uitvoermap / "datapackage.json").is_file()
    dekking = pd.read_parquet(oude_uitvoermap / "dekking.parquet")
    wu0 = dekking.loc[dekking["home_id__str"] == "WU0"].iloc[0]
    assert wu0["dubbele_tijdstippen__int"] == 1  # zelfde telling als de nieuwe vlagkolom


def test_migratie_is_idempotent(oude_uitvoermap: Path):
    eerste = migreer.migreer(oude_uitvoermap, docs_dir=None)
    sha_na_eerste = sha256_van_bestand(oude_uitvoermap / "boiler_temp" / "home_id=WU0.parquet")

    tweede = migreer.migreer(oude_uitvoermap, docs_dir=None)
    sha_na_tweede = sha256_van_bestand(oude_uitvoermap / "boiler_temp" / "home_id=WU0.parquet")

    assert tweede["boiler_temp_rijen"] == 0  # niets opnieuw gemigreerd
    assert sha_na_eerste == sha_na_tweede  # bestand is niet opnieuw geschreven


def test_migratie_is_hervatbaar_na_gedeeltelijke_voortgang(oude_uitvoermap: Path):
    """Simuleert een afgebroken migratie: WU0 is al op de nieuwe contractversie (zoals na een
    geslaagde eerdere migratie-aanroep voor die woning), WU1 nog niet. Een volgende aanroep moet
    alleen WU1 nog migreren en WU0 met rust laten."""
    manifest = Manifest(oude_uitvoermap)
    pad_wu0 = oude_uitvoermap / "boiler_temp" / "home_id=WU0.parquet"
    manifest.voeg_toe("boiler_temp", "WU0", pad_wu0, oude_uitvoermap, rijen=3)  # nu nieuwe contractversie
    sha_voor = sha256_van_bestand(pad_wu0)

    resultaat = migreer.migreer(oude_uitvoermap, docs_dir=None)

    sha_na = sha256_van_bestand(pad_wu0)
    assert sha_voor == sha_na  # WU0 is NIET aangeraakt (was al "voltooid" voor de nieuwe versie)
    # WU1 is wel gemigreerd: heeft nu de dedupvlag.
    df1 = pd.read_parquet(oude_uitvoermap / "boiler_temp" / "home_id=WU1.parquet")
    assert "q_flag_tijdstip_dubbel__bool" in df1.columns


def test_migratie_werkt_voortgang_bij_naar_nieuwe_contractversie(oude_uitvoermap: Path):
    oud = {"uitvoer_contract_versie": "2026-09-23-eerste-opzet", "fase": "klaar", "bronbestanden": {}}
    (oude_uitvoermap / "_voortgang.json").write_text(json.dumps(oud), encoding="utf-8")
    migreer.migreer(oude_uitvoermap, docs_dir=None)
    nieuw = json.loads((oude_uitvoermap / "_voortgang.json").read_text(encoding="utf-8"))
    assert nieuw["uitvoer_contract_versie"] == UITVOER_CONTRACT_VERSIE
    assert nieuw["fase"] == "klaar"
