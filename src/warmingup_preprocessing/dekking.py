# SPDX-License-Identifier: EUPL-1.2
"""Dekkingsartefact per woning (ontwerp-preprocessing.md §6): hoeveel van het eigen tijdvenster van een woning werkelijk gevuld is, en met welke
bijzonderheden (dubbele tijdstempels bij ``boiler_temp``, het gemiddelde meetinterval bij
``thermostat_temp``, dat per ontwerp gebeurtenisgestuurd is en dus per definitie gaten heeft die geen
gaten zijn).

Elke uitspraak over deze dataset hoort een dekkingsgewicht te dragen; dit bestand is dat gewicht, per woning en per
bronbestand.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import tijd

DEKKING_SCHEMA_KOLOMMEN = [
    "home_id__str",
    "bron__cat",
    "rijen__int",
    "eerste_tijdstip",
    "laatste_tijdstip",
    "dubbele_tijdstippen__int",
    "dekking_fractie__frac",
    "gemiddeld_interval__s",
]

#: Referentieschema voor ``datapackage.py`` (zie de toelichting bij ``tabellen.MAPPING_SCHEMA``: dit
#: is niet wat het schrijfpad zelf gebruikt om te casten, maar wat de echte uitvoer daadwerkelijk
#: heeft, geverifieerd op de volledige-run-uitvoer, 23-09-2026).
DEKKING_SCHEMA = pa.schema(
    [
        ("home_id__str", pa.string()),
        ("bron__cat", pa.string()),
        ("rijen__int", pa.int64()),
        # eerste_tijdstip/laatste_tijdstip komen rechtstreeks uit de al geschreven per-woningbestanden
        # (boiler_temp/thermostat_temp), die zelf al in TIJDZONE_WEERGAVE staan (schrijvers.py); geen
        # eigen omzetting hier nodig, alleen dit referentieschema meelaten kloppen.
        ("eerste_tijdstip", pa.timestamp("ns", tz=tijd.TIJDZONE_WEERGAVE)),
        ("laatste_tijdstip", pa.timestamp("ns", tz=tijd.TIJDZONE_WEERGAVE)),
        ("dubbele_tijdstippen__int", pa.int64()),
        ("dekking_fractie__frac", pa.float64()),
        ("gemiddeld_interval__s", pa.float64()),
    ]
)


#: Kolomnaam van de per-rij dubbele-tijdstip-vlag (``sentinels.flag_tijdstip_dubbel``, sinds
#: UITVOER_CONTRACT_VERSIE "2026-09-23-tweede-opzet"). Als deze kolom aanwezig is, is hij de bron
#: van waarheid voor ``dubbele_tijdstippen__int`` (zie hieronder); zonder deze kolom (oudere
#: uitvoer) valt dit bestand terug op de eerdere, gelijkwaardige berekening
#: (``tijdstip.sort_values().duplicated().sum()``): wiskundig dezelfde telling, alleen niet meer
#: zichtbaar op rijniveau. De twee methoden zijn op een steekproef van 6 woningen uit de eerste
#: volledige run tegen elkaar geverifieerd en gaven exact hetzelfde aantal (VOORTGANG.md).
_DUBBEL_VLAG_KOLOM = "q_flag_tijdstip_dubbel__bool"


def _dubbele_tijdstippen(df: pd.DataFrame) -> int:
    if _DUBBEL_VLAG_KOLOM in df.columns:
        return int(df[_DUBBEL_VLAG_KOLOM].sum())
    return int(df["tijdstip"].sort_values().duplicated().sum())


def _dekking_boiler_temp(home_id: str, pad: Path) -> dict:
    kolommen = ["tijdstip"] + [c for c in (_DUBBEL_VLAG_KOLOM,) if c in pq.ParquetFile(pad).schema_arrow.names]
    df = pd.read_parquet(pad, columns=kolommen)
    n = len(df)
    if n == 0:
        return {
            "home_id__str": home_id, "bron__cat": "boiler_temp", "rijen__int": 0,
            "eerste_tijdstip": pd.NaT, "laatste_tijdstip": pd.NaT,
            "dubbele_tijdstippen__int": 0, "dekking_fractie__frac": float("nan"),
            "gemiddeld_interval__s": float("nan"),
        }
    dubbel = _dubbele_tijdstippen(df)
    tijden = df["tijdstip"].sort_values()
    eerste, laatste = tijden.iloc[0], tijden.iloc[-1]
    venster_minuten = (laatste - eerste).total_seconds() / 60.0 + 1.0
    dekking = n / venster_minuten if venster_minuten > 0 else float("nan")
    return {
        "home_id__str": home_id, "bron__cat": "boiler_temp", "rijen__int": n,
        "eerste_tijdstip": eerste, "laatste_tijdstip": laatste,
        "dubbele_tijdstippen__int": dubbel, "dekking_fractie__frac": dekking,
        "gemiddeld_interval__s": float("nan"),
    }


def _dekking_thermostat_temp(home_id: str, pad: Path) -> dict:
    """Voor ``thermostat_temp`` is er GEEN dekkingsfractie tegen een minuutraster: de metingen zijn
    gebeurtenisgestuurd (ontwerp-preprocessing.md §6), dus een "gat" hier betekent "niets veranderd",
    niet "geen meting". Het gemiddelde interval tussen twee opeenvolgende metingen is hier het
    zinvolle dekkingsgewicht."""
    kolommen = ["tijdstip"] + [c for c in (_DUBBEL_VLAG_KOLOM,) if c in pq.ParquetFile(pad).schema_arrow.names]
    df = pd.read_parquet(pad, columns=kolommen)
    n = len(df)
    if n < 2:
        return {
            "home_id__str": home_id, "bron__cat": "thermostat_temp", "rijen__int": n,
            "eerste_tijdstip": df["tijdstip"].iloc[0] if n else pd.NaT,
            "laatste_tijdstip": df["tijdstip"].iloc[-1] if n else pd.NaT,
            "dubbele_tijdstippen__int": 0, "dekking_fractie__frac": float("nan"),
            "gemiddeld_interval__s": float("nan"),
        }
    dubbel = _dubbele_tijdstippen(df)
    tijden = df["tijdstip"].sort_values()
    eerste, laatste = tijden.iloc[0], tijden.iloc[-1]
    gem_interval = (laatste - eerste).total_seconds() / (n - 1)
    return {
        "home_id__str": home_id, "bron__cat": "thermostat_temp", "rijen__int": n,
        "eerste_tijdstip": eerste, "laatste_tijdstip": laatste,
        "dubbele_tijdstippen__int": dubbel, "dekking_fractie__frac": float("nan"),
        "gemiddeld_interval__s": gem_interval,
    }


def bouw_dekking(uit_dir: Path) -> pd.DataFrame:
    """Loop over alle per-woningbestanden onder ``<uit_dir>/boiler_temp`` en
    ``<uit_dir>/thermostat_temp`` en bereken per woning per bron de dekkingsstatistieken."""
    rijen = []
    boiler_map = uit_dir / "boiler_temp"
    if boiler_map.is_dir():
        for pad in sorted(boiler_map.glob("home_id=*.parquet")):
            home_id = pad.stem.split("=", 1)[-1]
            rijen.append(_dekking_boiler_temp(home_id, pad))
    thermo_map = uit_dir / "thermostat_temp"
    if thermo_map.is_dir():
        for pad in sorted(thermo_map.glob("home_id=*.parquet")):
            home_id = pad.stem.split("=", 1)[-1]
            rijen.append(_dekking_thermostat_temp(home_id, pad))
    return pd.DataFrame(rijen, columns=DEKKING_SCHEMA_KOLOMMEN)
