# SPDX-License-Identifier: EUPL-1.2
"""Gelijkheidstoets tussen de twee lezers (``schrijvers.py``/``snelle_lezer.py``): de pandas-route
(oorspronkelijk) en de pyarrow-route (nieuw, sneller) moeten voor de twee grote minuutbestanden
BIT-VOOR-BIT dezelfde Parquet-uitvoer geven, per woning (ontwerp-preprocessing.md §8).

Deze synthetische fixture bevat bewust de lastige gevallen die op de echte bron zijn aangetroffen of
door het ontwerp worden vereist:

* de tekstsentinel ``"x"`` in de aanvoertemperatuur (``sentinels.TEMP_AANVOER_TEKST_SENTINEL``);
* een leeg veld (retourtemperatuur, debiet) -- de gewone "ontbrekende meting";
* de debiet-sentinel ``2**32 - 1`` (``sentinels.FLOW_SENTINEL__l_h``);
* een minuutreeks die de Nederlandse zomertijdovergang van 28 maart 2021 in UTC kruist (lokaal
  02:00 -> 03:00 CEST, dus 01:00 UTC): de ``Time``-kolom zelf draagt geen tijdzone-sprong (het is en
  blijft UTC), maar dit is wel de dag waarop ``tijd.etmaalgrens_utc`` een 23-uursvenster teruggeeft,
  en de twee lezers moeten ook hier exact dezelfde ``timestamp``-waarden produceren.

De vergelijking gebruikt ``pyarrow.parquet.read_table(...).equals(...)``: gelijke schema's EN gelijke
waarden, kolom voor kolom, rij voor rij.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from tests.conftest import bouw_test_zip
from warmingup_preprocessing import kolommen, schrijvers, sentinels, tijd
from warmingup_preprocessing import zipbron as zipbron_mod
from warmingup_preprocessing.manifest import Manifest
from warmingup_preprocessing.pijplijn import (
    BOILER_TEMP_KOLOM_TYPES_PYARROW,
    BOILER_TEMP_SCHEMA,
    THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW,
    THERMOSTAT_TEMP_SCHEMA,
)

BOILER_TEMP_KOP = "House,Time,Boiler Water Supply Temperature (°C),Boiler Water Return Temperature (°C),Flow (l/h)"
THERMOSTAT_TEMP_KOP = "House,Time,Thermostat Desired Temperature (°C),Thermostat Measured Temperature (°C)"

#: Vlak vóór/rond/ná de Nederlandse zomertijdovergang van 28 maart 2021 (lokaal 02:00 -> 03:00 CEST,
#: dus 01:00 UTC): dit is de dag waarop ``tijd.etmaalgrens_utc`` een 23-uursvenster teruggeeft.
_DST_MINUTEN = ["2021-03-28T00:58:00Z", "2021-03-28T00:59:00Z", "2021-03-28T01:00:00Z", "2021-03-28T01:01:00Z", "2021-03-28T01:02:00Z"]


def _boiler_temp_vuile_regels(home: str) -> list[str]:
    regels = [
        f"{home},2021-01-01T00:00:00Z,40.00,30.00,300",
        f"{home},2021-01-01T00:01:00Z,x,30.10,300",  # tekstsentinel "x"
        f"{home},2021-01-01T00:02:00Z,40.20,,300",  # leeg veld (retourtemperatuur)
        f"{home},2021-01-01T00:03:00Z,40.30,30.30,",  # leeg veld (debiet)
        f"{home},2021-01-01T00:04:00Z,40.40,30.40,{sentinels.FLOW_SENTINEL__l_h}",  # debiet-sentinel
        f"{home},2021-01-01T00:05:00Z,40.50,30.50,300",
        f"{home},2021-01-01T00:06:00Z,x,x,300",  # "x" in twee kolommen tegelijk
    ]
    for i, t in enumerate(_DST_MINUTEN):
        regels.append(f"{home},{t},{41.0 + i:.2f},{31.0 + i:.2f},300")
    return regels


def _thermostat_temp_vuile_regels(home: str) -> list[str]:
    regels = [
        f"{home},2021-01-01T00:00:00Z,19.0,19.5",
        f"{home},2021-01-01T00:07:00Z,,19.7",  # leeg veld (setpoint)
        f"{home},2021-01-01T00:14:00Z,20.0,",  # leeg veld (binnentemperatuur)
    ]
    for i, t in enumerate(_DST_MINUTEN):
        regels.append(f"{home},{t},{19.0 + i * 0.1:.2f},{19.5 + i * 0.1:.2f}")
    return regels


@pytest.fixture
def vuile_test_zip(tmp_path: Path) -> Path:
    """Bouw eerst een schone testzip (``conftest.bouw_test_zip``, voor de vier kleine leden en een
    geldige structuur), en vervang dan de twee grote minuutbestanden door de "vuile" varianten
    hierboven."""
    homes = ["WU0", "WU1"]
    basis = bouw_test_zip(tmp_path / "basis.zip", homes, rijen_per_woning=5)

    with zipfile.ZipFile(basis) as z:
        leden = {naam: z.read(naam) for naam in z.namelist()}

    boiler_inhoud = BOILER_TEMP_KOP + "\n" + "\n".join(r for home in homes for r in _boiler_temp_vuile_regels(home)) + "\n"
    thermo_inhoud = THERMOSTAT_TEMP_KOP + "\n" + "\n".join(r for home in homes for r in _thermostat_temp_vuile_regels(home)) + "\n"
    leden["boiler-temp.csv"] = boiler_inhoud.encode("utf-8")
    leden["thermostat-temp.csv"] = thermo_inhoud.encode("utf-8")

    pad = tmp_path / "vuil.zip"
    with zipfile.ZipFile(pad, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for naam, inhoud in leden.items():
            z.writestr(naam, inhoud)
    return pad


def _schrijf_beide_lezers(bron_pad: Path, bestandsnaam: str, kolommen_map, flag_fn, schema, kolom_types_pyarrow, onderdeel: str, tmp_path: Path):
    uit_pandas = tmp_path / "uit-pandas"
    uit_pyarrow = tmp_path / "uit-pyarrow"
    with zipbron_mod.ZipBron(bron_pad) as bron:
        schrijvers.schrijf_per_woning_gesorteerd(
            bron=bron,
            bestandsnaam=bestandsnaam,
            kolommen_map=kolommen_map,
            tijdstip_naar_utc=tijd.naar_utc_tijdstip,
            flag_fn=flag_fn,
            schema=schema,
            uit_dir=uit_pandas,
            onderdeel=onderdeel,
            manifest=Manifest(uit_pandas),
            chunksize=3,  # klein, om chunkgrenzen midden in een woning te forceren
            dtype_ruw={"House": str},
            na_values=sentinels.BOILER_TEMP_NA_VALUES if onderdeel == "boiler_temp" else None,
            lezer="pandas",
        )
    with zipbron_mod.ZipBron(bron_pad) as bron:
        schrijvers.schrijf_per_woning_gesorteerd(
            bron=bron,
            bestandsnaam=bestandsnaam,
            kolommen_map=kolommen_map,
            tijdstip_naar_utc=tijd.naar_utc_tijdstip,
            flag_fn=flag_fn,
            schema=schema,
            uit_dir=uit_pyarrow,
            onderdeel=onderdeel,
            manifest=Manifest(uit_pyarrow),
            dtype_ruw={"House": str},
            na_values=sentinels.BOILER_TEMP_NA_VALUES if onderdeel == "boiler_temp" else None,
            lezer="pyarrow",
            kolom_types_pyarrow=kolom_types_pyarrow,
            block_size=200,  # klein: forceert meerdere Arrow-batches, net als chunksize=3 hierboven
        )
    return uit_pandas, uit_pyarrow


def _vergelijk_per_woning(uit_pandas: Path, uit_pyarrow: Path, onderdeel: str, homes: list[str]) -> None:
    for home in homes:
        pad_pandas = uit_pandas / onderdeel / f"home_id={home}.parquet"
        pad_pyarrow = uit_pyarrow / onderdeel / f"home_id={home}.parquet"
        assert pad_pandas.is_file(), pad_pandas
        assert pad_pyarrow.is_file(), pad_pyarrow
        tabel_pandas = pq.read_table(pad_pandas)
        tabel_pyarrow = pq.read_table(pad_pyarrow)
        assert tabel_pandas.equals(tabel_pyarrow), (
            f"{onderdeel}/{home}: pandas- en pyarrow-route geven verschillende uitvoer.\n"
            f"pandas:\n{tabel_pandas.to_pandas()}\n\npyarrow:\n{tabel_pyarrow.to_pandas()}"
        )


def test_boiler_temp_gelijk_ondanks_x_lege_velden_sentinel_en_dst(vuile_test_zip: Path, tmp_path: Path):
    uit_pandas, uit_pyarrow = _schrijf_beide_lezers(
        vuile_test_zip, zipbron_mod.BOILER_TEMP, kolommen.BOILER_TEMP_KOLOMMEN, sentinels.flag_boiler_temp,
        BOILER_TEMP_SCHEMA, BOILER_TEMP_KOLOM_TYPES_PYARROW, "boiler_temp", tmp_path,
    )
    _vergelijk_per_woning(uit_pandas, uit_pyarrow, "boiler_temp", ["WU0", "WU1"])

    # Expliciet: de "x"-rijen en de sentinelrij moeten ook echt als zodanig zijn opgeslagen (anders
    # zou de gelijkheidstoets hierboven twee routes kunnen vergelijken die BEIDE hetzelfde verkeerd
    # doen, en dat zou onopgemerkt blijven).
    import pandas as pd

    df = pd.read_parquet(uit_pyarrow / "boiler_temp" / "home_id=WU0.parquet")
    assert df["q_flag_temp_aanvoer_ontbrekend__bool"].sum() == 2  # de twee "x"-rijen
    assert df["q_flag_debiet_sentinel__bool"].sum() == 1
    assert df["temp_aanvoer__degC"].isna().sum() == 2
    assert df["temp_retour__degC"].isna().sum() == 2  # de lege-veld-rij + de dubbele "x"-rij


def test_thermostat_temp_gelijk_ondanks_lege_velden_en_dst(vuile_test_zip: Path, tmp_path: Path):
    uit_pandas, uit_pyarrow = _schrijf_beide_lezers(
        vuile_test_zip, zipbron_mod.THERMOSTAT_TEMP, kolommen.THERMOSTAT_TEMP_KOLOMMEN, sentinels.flag_thermostat_temp,
        THERMOSTAT_TEMP_SCHEMA, THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW, "thermostat_temp", tmp_path,
    )
    _vergelijk_per_woning(uit_pandas, uit_pyarrow, "thermostat_temp", ["WU0", "WU1"])


def test_controleer_aaneengesloten_beide_lezers_eens(vuile_test_zip: Path):
    with zipbron_mod.ZipBron(vuile_test_zip) as bron:
        pandas_uitkomst = schrijvers.controleer_aaneengesloten(bron, zipbron_mod.BOILER_TEMP, lezer="pandas")
    with zipbron_mod.ZipBron(vuile_test_zip) as bron:
        pyarrow_uitkomst = schrijvers.controleer_aaneengesloten(bron, zipbron_mod.BOILER_TEMP, lezer="pyarrow")
    assert pandas_uitkomst is pyarrow_uitkomst is True
