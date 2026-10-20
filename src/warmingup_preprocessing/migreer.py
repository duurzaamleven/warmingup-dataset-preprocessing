# SPDX-License-Identifier: EUPL-1.2
"""Migreert een bestaande uitvoermap van contractversie ``"2026-09-23-eerste-opzet"`` naar de
huidige ``manifest.UITVOER_CONTRACT_VERSIE``, ZONDER de hele pijplijn opnieuw op de brondata te
draaien.

**Waarom dit bestaat.** Na de reparaties in deze sessie (dubbele-tijdstip-vlag, logger_id__str als
string, Europe/Amsterdam als weergavezone) is het uitvoercontract drie keer omhoog gegaan. Een
volledige herrun van de brondata kost circa drie kwartier tot een uur (zie VOORTGANG.md); voor een
bestaande, al correcte uitvoermap is dat overbodig: alle nieuwe informatie (de dedupvlag, de
tz-omzetting, de stringcast) is uit de AL GESCHREVEN Parquet-bestanden zelf af te leiden, zonder de
ruwe zip opnieuw te lezen.

**Wat er per onderdeel verandert.**

* ``boiler_temp/home_id=*.parquet`` en ``thermostat_temp/home_id=*.parquet``: ``tijdstip`` van UTC
  naar Europe/Amsterdam (``tijd.naar_weergave_tijdzone``, instant blijft gelijk), en een nieuwe
  kolom ``q_flag_tijdstip_dubbel__bool`` (``sentinels.flag_tijdstip_dubbel``, toegepast in de
  volgorde waarin de rijen al in het bestand staan -- dat IS de bronvolgorde, want zo heeft de
  pijplijn ze geschreven).
* ``resultaten.parquet``: ``logger_id__str`` naar tekst (``kolommen.naar_string_zonder_punt0``).
* ``mapping.parquet``: defensief dezelfde cast (normaal al een no-op, zie ``tabellen.bouw_mapping``).
* ``etmaal.parquet``/``info_metadata.parquet``: geen inhoudelijke wijziging; alleen de
  manifestregel krijgt de nieuwe contractversie.
* ``dekking.parquet`` en ``docs/data-quality.md``: opnieuw opgebouwd NADAT de twee grote tabellen
  gemigreerd zijn (ze lezen de al-gemigreerde per-woningbestanden terug).
* ``datapackage.json``: geschreven aan het eind (``datapackage.schrijf_datapackage_voor_run``).

**Hervatbaar en idempotent, via hetzelfde mechanisme als de hoofdpijplijn.** Elk onderdeel wordt via
``<pad>.tmp`` + atomische hernoeming herschreven en pas DAARNA met ``manifest.voeg_toe`` als voltooid
gemarkeerd (zelfde patroon als ``schrijvers.py``/``manifest.py``). Vóór elk onderdeel wordt
``manifest.is_voltooid(onderdeel, sleutel, uit_dir)`` gecontroleerd: dat is per definitie False zodra
de manifestregel nog de oude contractversie heeft (``Manifest.is_voltooid`` vergelijkt zelf al met
``UITVOER_CONTRACT_VERSIE``), dus een herstart hervat gewoon waar hij gebleven was, en een tweede
aanroep op een al gemigreerde map doet niets. Er is geen apart migratie-specifiek statusbestand
nodig: het bestaande manifest is de enige bron van waarheid, ook hiervoor.

**Geheugen: per woningbestand, nooit alles tegelijk.** Elk per-woningbestand wordt rijgroep voor
rijgroep gelezen (``pyarrow.parquet.ParquetFile.read_row_group``) en weggeschreven, net als de
hoofdpijplijn chunk voor chunk werkt.

Gebruik::

    python -m warmingup_preprocessing.migreer --uit data/processed
"""

from __future__ import annotations

import argparse
import gc
import logging
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import datapackage as datapackage_mod
from . import dekking as dekking_mod
from . import kolommen
from . import kwaliteitsrapport
from . import sentinels
from . import tijd
from .manifest import Manifest, UITVOER_CONTRACT_VERSIE, schrijf_parquet_atomisch
from .pijplijn import BOILER_TEMP_SCHEMA, THERMOSTAT_TEMP_SCHEMA
from .voortgang import VoortgangSchrijver

log = logging.getLogger(__name__)


def _migreer_groot_woningbestand(pad: Path, schema: pa.Schema) -> int:
    """Herschrijf één per-woningbestand (``boiler_temp`` of ``thermostat_temp``) rijgroep voor
    rijgroep: tz naar de weergavezone, en (als hij nog ontbreekt) de dedupvlag erbij. Retourneert
    het aantal rijen."""
    tmp = pad.with_suffix(pad.suffix + ".tmp")
    pf = pq.ParquetFile(pad)
    heeft_al_dubbel_vlag = "q_flag_tijdstip_dubbel__bool" in pf.schema_arrow.names
    gezien: set[int] = set()
    writer: pq.ParquetWriter | None = None
    rijen = 0
    try:
        for rg in range(pf.num_row_groups):
            tabel = pf.read_row_group(rg)
            df = tabel.to_pandas()
            if str(df["tijdstip"].dt.tz) != str(tijd.TIJDZONE_WEERGAVE):
                df["tijdstip"] = tijd.naar_weergave_tijdzone(df["tijdstip"])
            if not heeft_al_dubbel_vlag:
                df["q_flag_tijdstip_dubbel__bool"] = sentinels.flag_tijdstip_dubbel(
                    df["tijdstip"].astype("int64"), gezien
                )
            tabel_nieuw = pa.Table.from_pandas(df, preserve_index=False).select(schema.names).cast(schema)
            if writer is None:
                writer = pq.ParquetWriter(tmp, schema, compression="zstd")
            writer.write_table(tabel_nieuw)
            rijen += len(df)
    finally:
        if writer is not None:
            writer.close()
    # Expliciet de leeshandle op het OUDE bestand sluiten vóór de hernoeming: op Windows kan een
    # bestand niet overschreven worden zolang er nog een open handle op staat (geverifieerd tijdens
    # het bouwen van deze module).
    pf.close()
    del pf
    gc.collect()
    tmp.replace(pad)
    return rijen


def _migreer_groot_onderdeel(uit_dir: Path, onderdeel: str, schema: pa.Schema, manifest: Manifest) -> int:
    map_pad = uit_dir / onderdeel
    if not map_pad.is_dir():
        return 0
    totaal = 0
    for pad in sorted(map_pad.glob("home_id=*.parquet")):
        home_id = pad.stem.split("=", 1)[-1]
        if manifest.is_voltooid(onderdeel, home_id, uit_dir):
            continue
        rijen = _migreer_groot_woningbestand(pad, schema)
        manifest.voeg_toe(onderdeel, home_id, pad, uit_dir, rijen)
        log.info("%s: woning %s gemigreerd, %d rij(en)", onderdeel, home_id, rijen)
        totaal += rijen
    return totaal


def _migreer_resultaten(uit_dir: Path, manifest: Manifest) -> None:
    pad = uit_dir / "resultaten.parquet"
    if not pad.is_file() or manifest.is_voltooid("resultaten", "resultaten", uit_dir):
        return
    df = pd.read_parquet(pad)
    if "logger_id__str" in df.columns:
        df["logger_id__str"] = kolommen.naar_string_zonder_punt0(df["logger_id__str"])
    schrijf_parquet_atomisch(pad, df)
    manifest.voeg_toe("resultaten", "resultaten", pad, uit_dir, len(df))
    log.info("resultaten.parquet gemigreerd (%d rij(en))", len(df))


def _migreer_mapping(uit_dir: Path, manifest: Manifest) -> None:
    pad = uit_dir / "mapping.parquet"
    if not pad.is_file() or manifest.is_voltooid("mapping", "mapping", uit_dir):
        return
    df = pd.read_parquet(pad)
    if "logger_id__str" in df.columns:
        df["logger_id__str"] = kolommen.naar_string_zonder_punt0(df["logger_id__str"])
    schrijf_parquet_atomisch(pad, df)
    manifest.voeg_toe("mapping", "mapping", pad, uit_dir, len(df))
    log.info("mapping.parquet gemigreerd (%d rij(en), meestal een no-op)", len(df))


def _migreer_ongewijzigd(uit_dir: Path, onderdeel: str, bestandsnaam: str, manifest: Manifest) -> None:
    """Voor tabellen zonder inhoudelijke wijziging (etmaal, info_metadata): alleen de manifestregel
    krijgt de nieuwe contractversie, geen herschrijfactie nodig."""
    pad = uit_dir / bestandsnaam
    if not pad.is_file() or manifest.is_voltooid(onderdeel, onderdeel, uit_dir):
        return
    rijen = pq.ParquetFile(pad).metadata.num_rows
    manifest.voeg_toe(onderdeel, onderdeel, pad, uit_dir, rijen)
    log.info("%s: geen inhoudelijke wijziging, manifest bijgewerkt (%d rij(en))", bestandsnaam, rijen)


def migreer(uit_dir: Path, docs_dir: Path | None = "docs", is_steekproef: bool = False) -> dict:
    uit_dir = Path(uit_dir)
    if not uit_dir.is_dir():
        raise FileNotFoundError(f"Geen uitvoermap: {uit_dir}")
    manifest = Manifest(uit_dir)
    # Ook _voortgang.json hoort bij de uitvoer: na een migratie zegt hij de nieuwe contractversie en
    # fase "klaar", anders blijft de voortgang van de oorspronkelijke run staan met de oude versie.
    # Een migratie leest geen bronbestanden, dus "bronbestanden" blijft leeg; de fase laat zien
    # welk onderdeel bezig is.
    voortgang = VoortgangSchrijver(uit_dir, UITVOER_CONTRACT_VERSIE)

    voortgang.zet_fase("migratie_boiler_temp")
    resultaat = {"boiler_temp_rijen": _migreer_groot_onderdeel(uit_dir, "boiler_temp", BOILER_TEMP_SCHEMA, manifest)}
    voortgang.zet_fase("migratie_thermostat_temp")
    resultaat["thermostat_temp_rijen"] = _migreer_groot_onderdeel(
        uit_dir, "thermostat_temp", THERMOSTAT_TEMP_SCHEMA, manifest
    )
    voortgang.zet_fase("migratie_kleine_tabellen")
    _migreer_resultaten(uit_dir, manifest)
    _migreer_mapping(uit_dir, manifest)
    _migreer_ongewijzigd(uit_dir, "etmaal", "etmaal.parquet", manifest)
    _migreer_ongewijzigd(uit_dir, "info_metadata", "info_metadata.parquet", manifest)

    voortgang.zet_fase("dekking")
    # dekking.parquet altijd herbouwen (leest de al-gemigreerde per-woningbestanden terug; zelfde
    # aanpak als pijplijn.run, dat dit ook bij elke aanroep herdoet).
    dekking_df = dekking_mod.bouw_dekking(uit_dir)
    dekking_pad = uit_dir / "dekking.parquet"
    schrijf_parquet_atomisch(dekking_pad, dekking_df)
    manifest.voeg_toe("dekking", "dekking", dekking_pad, uit_dir, len(dekking_df))
    resultaat["dekking_rijen"] = len(dekking_df)

    if docs_dir is not None:
        kwaliteitsrapport.schrijf_rapport(uit_dir, Path(docs_dir) / "data-quality.md", is_steekproef)

    datapackage_pad = datapackage_mod.schrijf_datapackage_voor_run(uit_dir, UITVOER_CONTRACT_VERSIE)
    resultaat["datapackage"] = str(datapackage_pad)

    voortgang.klaar()
    log.info("Migratie klaar: %s", resultaat)
    return resultaat


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--uit", type=Path, required=True, help="Bestaande uitvoermap om te migreren")
    p.add_argument("--docs-dir", type=Path, default=Path("docs"))
    p.add_argument(
        "--steekproef", action="store_true",
        help="Zet de waarschuwing in het kwaliteitsrapport dat dit een steekproef is (net als "
        "pijplijn.py's --test); alleen relevant voor de tekst van docs/data-quality.md.",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    migreer(args.uit, docs_dir=args.docs_dir, is_steekproef=args.steekproef)


if __name__ == "__main__":
    main()
