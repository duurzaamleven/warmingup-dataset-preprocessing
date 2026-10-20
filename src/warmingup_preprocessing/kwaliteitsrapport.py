# SPDX-License-Identifier: EUPL-1.2
"""Schrijft ``docs/data-quality.md``: het kwaliteitsrapport dat de pijplijn zelf genereert
(ontwerp-preprocessing.md §6). Telt hoe vaak elke plausibiliteitsvlag (``sentinels.py``) voorkomt en
vat de dekking (``dekking.py``) samen, per bron en (waar zinvol) over alle woningen heen.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from .manifest import UITVOER_CONTRACT_VERSIE

#: Lokale kalenderdag van de Nederlandse oktober-zomertijdwissel (wintertijd begint), voor de
#: zomertijdgaten-telling hieronder. Bevinding van de opdrachtgever (23-09-2026, zie
#: docs/datacatalogus.md §4): in `boiler_temp` ontbreekt bij een deel van de woningen precies het
#: TWEEDE uur van dit lokale tijdvenster (02:00-02:59 CET, dus 01:00-01:59 UTC); dit rapport telt
#: hoeveel woningen dat treft, als vinding, geen correctie (het ontbrekende uur wordt niet
#: teruggezet).
DST_OKTOBER_DATUMS = ("2021-10-31", "2022-10-30")

#: Drempel voor "een gat": ontwerp-preprocessing.md/datacatalogus.md noemen "een gat van >= 50
#: minuten rond elke oktoberwissel" als de gevraagde telling.
DST_GAT_DREMPEL__min = 50.0


def _vlagtelling(uit_dir: Path, onderdeel: str, vlagkolommen: list[str]) -> tuple[int, dict[str, int]]:
    """Tel per vlag hoe vaak hij True is, gestreamd over alle per-woningbestanden (of het ene
    tabelbestand) van ``onderdeel``, zonder alles tegelijk in geheugen te laden."""
    totaal_rijen = 0
    tellingen = {v: 0 for v in vlagkolommen}
    map_of_bestand = uit_dir / onderdeel
    if map_of_bestand.is_dir():
        bestanden = sorted(map_of_bestand.glob("home_id=*.parquet"))
    else:
        pad = uit_dir / f"{onderdeel}.parquet"
        bestanden = [pad] if pad.is_file() else []
    for pad in bestanden:
        parquet_file = pq.ParquetFile(pad)
        aanwezig = [v for v in vlagkolommen if v in parquet_file.schema_arrow.names]
        if not aanwezig:
            totaal_rijen += parquet_file.metadata.num_rows
            continue
        for rg in range(parquet_file.num_row_groups):
            tabel = parquet_file.read_row_group(rg, columns=aanwezig)
            totaal_rijen += tabel.num_rows
            for v in aanwezig:
                tellingen[v] += tabel.column(v).cast("int64").to_pandas().sum() if tabel.num_rows else 0
    return totaal_rijen, tellingen


BOILER_TEMP_VLAGGEN = [
    "q_flag_debiet_sentinel__bool",
    "q_flag_debiet_bovengrens__bool",
    "q_flag_temp_aanvoer_ontbrekend__bool",
    "q_flag_temp_retour_ontbrekend__bool",
    "q_flag_temp_aanvoer_bereik__bool",
    "q_flag_temp_retour_bereik__bool",
    "q_flag_tijdstip_dubbel__bool",
]
THERMOSTAT_TEMP_VLAGGEN = [
    "q_flag_temp_setpoint_bereik__bool",
    "q_flag_temp_binnen_bereik__bool",
    "q_flag_tijdstip_dubbel__bool",
]
ETMAAL_VLAGGEN = [
    "q_flag_gas_ruimteverwarming_bereik__bool",
    "q_flag_gas_tapwater_bereik__bool",
    "q_flag_brander_verwarming_bereik__bool",
    "q_flag_brander_tapwater_bereik__bool",
    "q_flag_druk_min_onbekend__bool",
    "q_flag_druk_gem_onbekend__bool",
    "q_flag_druk_max_onbekend__bool",
]


def _tel_dst_oktobergaten(uit_dir: Path) -> dict[str, dict[str, int]]:
    """Voor elke datum in ``DST_OKTOBER_DATUMS``: hoeveel woningen in ``boiler_temp`` hebben data
    rond die datum, en hoeveel daarvan een gat van minstens ``DST_GAT_DREMPEL__min`` minuten binnen
    een venster van 03:00 uur rond de wisseling? ``tijdstip`` staat in de weergavezone (Europe/
    Amsterdam); de vensters hieronder zijn in UTC, maar tz-aware vergelijking in pandas gaat altijd
    via het instant, dus dat maakt voor de vergelijking zelf niets uit."""
    boiler_map = uit_dir / "boiler_temp"
    resultaat: dict[str, dict[str, int]] = {}
    if not boiler_map.is_dir():
        return resultaat
    bestanden = sorted(boiler_map.glob("home_id=*.parquet"))
    for datum in DST_OKTOBER_DATUMS:
        venster_begin = pd.Timestamp(f"{datum}T00:30:00", tz="UTC")
        venster_eind = pd.Timestamp(f"{datum}T03:30:00", tz="UTC")
        woningen_met_data = 0
        woningen_met_gat = 0
        for pad in bestanden:
            tijden = pd.read_parquet(pad, columns=["tijdstip"])["tijdstip"]
            venster = tijden.loc[(tijden >= venster_begin) & (tijden < venster_eind)].sort_values()
            if venster.empty:
                continue
            woningen_met_data += 1
            grootste_gat__min = venster.diff().dt.total_seconds().max() / 60.0
            if pd.notna(grootste_gat__min) and grootste_gat__min >= DST_GAT_DREMPEL__min:
                woningen_met_gat += 1
        resultaat[datum] = {"woningen_met_data": woningen_met_data, "woningen_met_gat": woningen_met_gat}
    return resultaat


def schrijf_rapport(uit_dir: Path, docs_pad: Path, is_steekproef: bool) -> None:
    uit_dir = Path(uit_dir)
    docs_pad = Path(docs_pad)
    regels: list[str] = []
    regels.append("# Datakwaliteit")
    regels.append("")
    regels.append(
        "Dit bestand wordt door de pijplijn zelf geschreven (`warmingup_preprocessing.kwaliteitsrapport`), "
        "niet met de hand bijgehouden. Het telt per plausibiliteitsvlag hoe vaak hij True is "
        "(`sentinels.py`); geen enkele gevlagde rij is verwijderd, zie ontwerp-preprocessing.md §6."
    )
    regels.append("")
    regels.append(f"Uitvoercontractversie: `{UITVOER_CONTRACT_VERSIE}`.")
    regels.append("")
    if is_steekproef:
        regels.append(
            "**Let op: dit rapport gaat over een steekproef** (`--test`/`--n-woningen`), niet over de "
            "volledige dataset. De percentages hieronder zijn dus niet representatief voor de hele set."
        )
        regels.append("")

    for onderdeel, vlaggen, titel in (
        ("boiler_temp", BOILER_TEMP_VLAGGEN, "`boiler_temp` (minuutdata aanvoer/retour/debiet)"),
        ("thermostat_temp", THERMOSTAT_TEMP_VLAGGEN, "`thermostat_temp` (setpoint/binnentemperatuur)"),
        ("etmaal", ETMAAL_VLAGGEN, "`etmaal` (boiler-24h-stats)"),
    ):
        regels.append(f"## {titel}")
        regels.append("")
        totaal, tellingen = _vlagtelling(uit_dir, onderdeel, vlaggen)
        if totaal == 0:
            regels.append("Geen uitvoer gevonden voor dit onderdeel.")
            regels.append("")
            continue
        regels.append(f"Totaal aantal rijen: {totaal:,}".replace(",", "."))
        regels.append("")
        regels.append("| vlag | aantal | aandeel |")
        regels.append("|---|---:|---:|")
        for v, n in tellingen.items():
            aandeel = 100.0 * n / totaal if totaal else float("nan")
            regels.append(f"| `{v}` | {int(n):,} | {aandeel:.3f}% |".replace(",", "."))
        regels.append("")

    dekking_pad = uit_dir / "dekking.parquet"
    if dekking_pad.is_file():
        dekking = pd.read_parquet(dekking_pad)
        regels.append("## Dekking per woning")
        regels.append("")
        for bron_naam in ("boiler_temp", "thermostat_temp"):
            deel = dekking.loc[dekking["bron__cat"] == bron_naam]
            if deel.empty:
                continue
            regels.append(f"### {bron_naam}")
            regels.append("")
            regels.append(f"Aantal woningen met uitvoer: {len(deel)}.")
            if bron_naam == "boiler_temp":
                mediaan = deel["dekking_fractie__frac"].median()
                p10 = deel["dekking_fractie__frac"].quantile(0.10)
                dubbel = int(deel["dubbele_tijdstippen__int"].sum())
                regels.append(
                    f"Dekkingsfractie (rijen / minuten in eigen venster): mediaan {mediaan:.3f}, "
                    f"p10 {p10:.3f}. Totaal aantal dubbele tijdstempels: {dubbel:,}.".replace(",", ".")
                )
            else:
                gem = deel["gemiddeld_interval__s"].median()
                regels.append(f"Mediaan van het gemiddelde meetinterval per woning: {gem:.0f} s.")
            regels.append("")

    dst_gaten = _tel_dst_oktobergaten(uit_dir)
    if dst_gaten:
        regels.append("## Zomertijdgaten rond de oktoberwissel (boiler_temp)")
        regels.append("")
        regels.append(
            "Bevinding van de opdrachtgever (23-09-2026, zie docs/datacatalogus.md §4 voor de "
            "methode): bij een deel van de woningen ontbreekt rond de overgang naar wintertijd "
            "precies het TWEEDE uur van het dubbelzinnige lokale tijdvenster. Dit telt alleen; er is "
            "GEEN correctie in de data, het ontbrekende uur is echt weg."
        )
        regels.append("")
        regels.append("| datum (lokale wisseling) | woningen met data in het venster | woningen met een gat >= 50 min |")
        regels.append("|---|---:|---:|")
        for datum, telling in dst_gaten.items():
            regels.append(f"| {datum} | {telling['woningen_met_data']} | {telling['woningen_met_gat']} |")
        regels.append("")

    docs_pad.parent.mkdir(parents=True, exist_ok=True)
    tmp = docs_pad.with_suffix(docs_pad.suffix + ".tmp")
    tmp.write_text("\n".join(regels) + "\n", encoding="utf-8")
    tmp.replace(docs_pad)
