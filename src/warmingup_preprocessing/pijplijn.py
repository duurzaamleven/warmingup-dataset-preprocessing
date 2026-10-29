# SPDX-License-Identifier: EUPL-1.2
"""Orchestratie en CLI: bouwt alle uitvoer uit ``data-en-resultaten.zip``
(ontwerp-preprocessing.md §2 t/m §9).

Gebruik: ``python -m warmingup_preprocessing --raw-dir data/raw --uit data/processed``.

* ``--droogloop``: laat zien wat er zou gebeuren (schijfruimte, sortering, welke onderdelen al af
  zijn) zonder iets te schrijven.
* ``--test``: verwerk alleen de eerste ``--test-mb`` megabyte (ontcomprimeerd) van elk groot
  bronbestand, zodat een testrun in minuten klaar is in plaats van in het kwartier dat de volledige
  bestanden vragen.
* ``--opnieuw``: gooi een eerdere (gedeeltelijke) run weg en begin schoon.

Zonder deze vlaggen verwerkt de pijplijn de VOLLEDIGE dataset en hervat hij een eerder afgebroken run
(zie ``manifest.py``): elk onderdeel dat al een geldige manifestregel heeft, wordt overgeslagen.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa

from . import datapackage as datapackage_mod
from . import dekking as dekking_mod
from . import kolommen
from . import kwaliteitsrapport
from . import schrijvers
from . import sentinels
from . import snelle_lezer as snelle_lezer_mod
from . import tabellen
from . import tijd
from . import zipbron as zipbron_mod
from .manifest import Manifest, UITVOER_CONTRACT_VERSIE, schrijf_parquet_atomisch
from .voortgang import VoortgangSchrijver

log = logging.getLogger(__name__)

#: Standaard ondergrens voor vrije schijfruimte op het uitvoerpad (ontwerp-eis: minstens 10 GB).
#: GB hier decimaal (1e9 bytes), zoals bij een schijf-vrije-ruimtemelding gebruikelijk is.
MIN_VRIJE_SCHIJFRUIMTE__GB = 10.0

SORTERING_CACHE_BESTANDSNAAM = "_sortering.json"

GROTE_BRONBESTANDEN = (zipbron_mod.BOILER_TEMP, zipbron_mod.THERMOSTAT_TEMP)


class SchijfruimteFout(RuntimeError):
    """Er is minder dan de vereiste vrije schijfruimte op het uitvoerpad; nette fout in plaats van
    een pijplijn die halverwege vastloopt met een volle schijf."""


def controleer_schijfruimte(uit_dir: Path, minimum__GB: float = MIN_VRIJE_SCHIJFRUIMTE__GB) -> None:
    bestaand_pad = uit_dir if uit_dir.exists() else uit_dir.parent
    bestaand_pad.mkdir(parents=True, exist_ok=True) if not bestaand_pad.exists() else None
    vrij__B = shutil.disk_usage(bestaand_pad).free
    vrij__GB = vrij__B / 1e9
    if vrij__GB < minimum__GB:
        raise SchijfruimteFout(
            f"Slechts {vrij__GB:.1f} GB vrij op {bestaand_pad}, minimaal {minimum__GB:.1f} GB "
            "vereist. Kies een ander uitvoerpad (--uit) of maak ruimte vrij."
        )
    log.info("Schijfruimtecontrole: %.1f GB vrij op %s (minimum %.1f GB)", vrij__GB, bestaand_pad, minimum__GB)


def _sortering_cache_pad(uit_dir: Path) -> Path:
    return uit_dir / SORTERING_CACHE_BESTANDSNAAM


def _lees_sortering_cache(uit_dir: Path) -> dict:
    pad = _sortering_cache_pad(uit_dir)
    if not pad.is_file():
        return {}
    try:
        return json.loads(pad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _schrijf_sortering_cache(uit_dir: Path, cache: dict) -> None:
    pad = _sortering_cache_pad(uit_dir)
    pad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pad.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(pad)


def bepaal_sortering(bron, bestandsnaam: str, uit_dir: Path, max_bytes: int | None, lezer: str = "pyarrow") -> bool:
    """Aaneengesloten-check met caching in ``_sortering.json``, per (bestandsnaam, max_bytes)
    (ontwerp §2: "controleer eerst"). Een ``--test``-run met een kleine ``max_bytes`` cachet apart
    van een volledige run: het is een ander venster op het bestand en de uitkomst hoort niet
    doorgezet te worden naar de volledige run of andersom.

    De uitkomst is een feit over de brondata, niet over de lezer die hem vaststelt; de cachesleutel
    bevat ``lezer`` dus bewust NIET, en beide lezers moeten hetzelfde antwoord geven (bewaakt door de
    gelijkheidstests)."""
    cache = _lees_sortering_cache(uit_dir)
    cache_sleutel = f"{bestandsnaam}::{max_bytes if max_bytes is not None else 'volledig'}"
    bestaand = cache.get(cache_sleutel)
    if bestaand is not None:
        log.info("%s: sorteringscontrole uit cache: aaneengesloten=%s", bestandsnaam, bestaand["aaneengesloten"])
        return bestaand["aaneengesloten"]

    t0 = time.monotonic()
    if max_bytes is not None:
        aaneengesloten = _controleer_aaneengesloten_begrensd(bron, bestandsnaam, max_bytes, lezer)
    else:
        aaneengesloten = schrijvers.controleer_aaneengesloten(bron, bestandsnaam, lezer=lezer)
    log.info(
        "%s: sorteringscontrole klaar in %.1f s: aaneengesloten=%s", bestandsnaam, time.monotonic() - t0, aaneengesloten
    )
    cache[cache_sleutel] = {
        "aaneengesloten": aaneengesloten,
        "gecontroleerd_op": datetime.now(timezone.utc).isoformat(),
    }
    _schrijf_sortering_cache(uit_dir, cache)
    return aaneengesloten


def _controleer_aaneengesloten_begrensd(bron, bestandsnaam: str, max_bytes: int, lezer: str = "pyarrow") -> bool:
    if lezer == "pyarrow":
        return snelle_lezer_mod.controleer_aaneengesloten_snel(bron, bestandsnaam, max_bytes=max_bytes)

    gezien: set[str] = set()
    laatste = None
    with bron.open_bron(bestandsnaam, max_bytes=max_bytes) as stream:
        for chunk in zipbron_mod.lees_csv_in_chunks(
            stream, chunksize=200_000, dtype={"House": str}, usecols=["House"]
        ):
            for waarde in chunk["House"].to_numpy():
                if waarde != laatste:
                    if waarde in gezien:
                        return False
                    gezien.add(waarde)
                    laatste = waarde
    return True


BOILER_TEMP_SCHEMA = pa.schema(
    [
        ("home_id__str", pa.string()),
        ("tijdstip", pa.timestamp("ns", tz=tijd.TIJDZONE_WEERGAVE)),
        ("temp_aanvoer__degC", pa.float32()),
        ("temp_retour__degC", pa.float32()),
        # float64, niet int64: het debiet kan (zeldzaam) de tekstsentinel "x" bevatten (zie
        # sentinels.py) en wordt dan NaN; float64 representeert elke waarde tot 2^32-1 nog exact,
        # dus dit kost geen precisie voor de sentinelvergelijking, en int64 kan geen NaN dragen.
        ("debiet_ruw__l_h", pa.float64()),
        ("debiet__dm3_s_1", pa.float32()),
        ("q_afgifte__W", pa.float32()),
        ("q_flag_debiet_sentinel__bool", pa.bool_()),
        ("q_flag_debiet_bovengrens__bool", pa.bool_()),
        ("q_flag_temp_aanvoer_ontbrekend__bool", pa.bool_()),
        ("q_flag_temp_retour_ontbrekend__bool", pa.bool_()),
        ("q_flag_temp_aanvoer_bereik__bool", pa.bool_()),
        ("q_flag_temp_retour_bereik__bool", pa.bool_()),
        # Zie sentinels.flag_tijdstip_dubbel: True vanaf de TWEEDE keer dat (home_id, tijdstip)
        # voorkomt; de eerste keer blijft False. Vlaggen, niet verwijderen (CLAUDE.md-regel 5).
        ("q_flag_tijdstip_dubbel__bool", pa.bool_()),
    ]
)

THERMOSTAT_TEMP_SCHEMA = pa.schema(
    [
        ("home_id__str", pa.string()),
        ("tijdstip", pa.timestamp("ns", tz=tijd.TIJDZONE_WEERGAVE)),
        ("temp_setpoint__degC", pa.float32()),
        ("temp_binnen__degC", pa.float32()),
        ("q_flag_temp_setpoint_bereik__bool", pa.bool_()),
        ("q_flag_temp_binnen_bereik__bool", pa.bool_()),
        ("q_flag_tijdstip_dubbel__bool", pa.bool_()),
    ]
)

#: Vaste Arrow-kolomtypen voor de snelle lezer (``snelle_lezer.py``), één per RUWE kolomnaam (dus
#: vóór ``kolommen_map``-vertaling). ``Time`` gaat rechtstreeks naar ``timestamp(ns, UTC)``: pyarrow
#: herkent het ISO-8601-``Z``-formaat zonder een apart patroon (geverifieerd tegen de echte data en
#: tegen ``tijd.naar_utc_tijdstip``, zie ``tests/test_snelle_lezer_gelijkheid.py``). De temperatuur-
#: en debietkolommen worden float64 (zoals `pandas.read_csv` ze bij afwezigheid van een expliciet
#: `dtype` ook zou inferen zodra er ontbrekende waarden in zitten), zodat het cast-naar-schema-punt
#: in ``schrijvers.py`` (dat nog steeds de waarheid is) ongewijzigd blijft werken.
BOILER_TEMP_KOLOM_TYPES_PYARROW = {
    "House": pa.string(),
    "Time": pa.timestamp("ns", tz="UTC"),
    "Boiler Water Supply Temperature (°C)": pa.float64(),
    "Boiler Water Return Temperature (°C)": pa.float64(),
    "Flow (l/h)": pa.float64(),
}

THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW = {
    "House": pa.string(),
    "Time": pa.timestamp("ns", tz="UTC"),
    "Thermostat Desired Temperature (°C)": pa.float64(),
    "Thermostat Measured Temperature (°C)": pa.float64(),
}


def _verwerk_groot_bestand(
    bron,
    bestandsnaam: str,
    onderdeel: str,
    kolommen_map: dict[str, str],
    flag_fn,
    schema,
    uit_dir: Path,
    manifest: Manifest,
    voortgang: VoortgangSchrijver,
    max_bytes: int | None,
    dtype_ruw: dict,
    na_values: list | None = None,
    lezer: str = "pyarrow",
    kolom_types_pyarrow: dict | None = None,
    block_size: int | None = None,
) -> dict[str, int]:
    voortgang.zet_fase(onderdeel)
    voortgang.zet_totaal(bestandsnaam, bron.ongecomprimeerde_omvang(bestandsnaam))
    aaneengesloten = bepaal_sortering(bron, bestandsnaam, uit_dir, max_bytes, lezer=lezer)

    def _op_voortgang(bytes_gelezen: int, rijen_gelezen: int) -> None:
        if bytes_gelezen >= 0:
            voortgang.update(bestandsnaam, bytes_gelezen__B=bytes_gelezen, rijen_gelezen=rijen_gelezen)
        else:
            voortgang.update(bestandsnaam, rijen_gelezen=rijen_gelezen)

    kwargs = dict(
        bron=bron,
        bestandsnaam=bestandsnaam,
        kolommen_map=kolommen_map,
        tijdstip_naar_utc=tijd.naar_utc_tijdstip,
        flag_fn=flag_fn,
        schema=schema,
        uit_dir=uit_dir,
        onderdeel=onderdeel,
        manifest=manifest,
        max_bytes=max_bytes,
        dtype_ruw=dtype_ruw,
        na_values=na_values,
        op_voortgang=_op_voortgang,
    )
    # De ongesorteerde-route (scatter/compacteer) blijft pandas-only: de echte data raakt hem niet
    # (zie schrijvers.py-moduledocstring), dus de snelheidswinst van pyarrow is daar niet nodig, en
    # de fallback moet zo min mogelijk nieuwe code raken.
    kwargs_gesorteerd = dict(kwargs, lezer=lezer, kolom_types_pyarrow=kolom_types_pyarrow)
    if block_size is not None:
        kwargs_gesorteerd["block_size"] = block_size
    if aaneengesloten:
        try:
            resultaat = schrijvers.schrijf_per_woning_gesorteerd(**kwargs_gesorteerd)
        except schrijvers.SorteerFout as fout:
            log.error(
                "%s: de sorteringscontrole zei aaneengesloten, maar het schrijven zelf detecteerde "
                "toch een schending (%s). Val terug op de ongesorteerde route.", bestandsnaam, fout
            )
            resultaat = schrijvers.schrijf_per_woning_ongesorteerd(**kwargs)
    else:
        resultaat = schrijvers.schrijf_per_woning_ongesorteerd(**kwargs)

    voortgang.zet_voltooid(bestandsnaam)
    return resultaat


def run(
    raw_dir: str | Path,
    uit_dir: str | Path,
    docs_dir: str | Path | None = "docs",
    test_mb: int | None = None,
    opnieuw: bool = False,
    min_vrije_schijfruimte__GB: float = MIN_VRIJE_SCHIJFRUIMTE__GB,
    droogloop: bool = False,
    lezer: str = "pyarrow",
    block_size_mb: float | None = None,
) -> dict:
    raw_dir = Path(raw_dir)
    uit_dir = Path(uit_dir)
    bron = zipbron_mod.maak_bron(raw_dir)

    if droogloop:
        return _droogloop(bron, uit_dir, test_mb, min_vrije_schijfruimte__GB)

    if opnieuw and uit_dir.exists():
        log.info("--opnieuw: %s wordt gewist", uit_dir)
        shutil.rmtree(uit_dir)
    uit_dir.mkdir(parents=True, exist_ok=True)

    controleer_schijfruimte(uit_dir, min_vrije_schijfruimte__GB)

    max_bytes = test_mb * 1_000_000 if test_mb is not None else None
    manifest = Manifest(uit_dir)
    voortgang = VoortgangSchrijver(uit_dir, UITVOER_CONTRACT_VERSIE)
    start = time.monotonic()

    resultaten: dict[str, object] = {}
    block_size = int(block_size_mb * (1 << 20)) if block_size_mb is not None else None

    resultaten["boiler_temp"] = _verwerk_groot_bestand(
        bron, zipbron_mod.BOILER_TEMP, "boiler_temp", kolommen.BOILER_TEMP_KOLOMMEN, sentinels.flag_boiler_temp,
        BOILER_TEMP_SCHEMA, uit_dir, manifest, voortgang, max_bytes,
        dtype_ruw={"House": str}, na_values=sentinels.BOILER_TEMP_NA_VALUES,
        lezer=lezer, kolom_types_pyarrow=BOILER_TEMP_KOLOM_TYPES_PYARROW, block_size=block_size,
    )
    resultaten["thermostat_temp"] = _verwerk_groot_bestand(
        bron, zipbron_mod.THERMOSTAT_TEMP, "thermostat_temp", kolommen.THERMOSTAT_TEMP_KOLOMMEN,
        sentinels.flag_thermostat_temp, THERMOSTAT_TEMP_SCHEMA, uit_dir, manifest, voortgang, max_bytes,
        dtype_ruw={"House": str},
        lezer=lezer, kolom_types_pyarrow=THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW, block_size=block_size,
    )

    voortgang.zet_fase("etmaal")
    etmaal_pad = uit_dir / "etmaal.parquet"
    if not manifest.is_voltooid("etmaal", "etmaal", uit_dir):
        voortgang.zet_totaal(zipbron_mod.BOILER_24H_STATS, bron.ongecomprimeerde_omvang(zipbron_mod.BOILER_24H_STATS))

        def _op_voortgang_etmaal(n: int) -> None:
            voortgang.update(zipbron_mod.BOILER_24H_STATS, bytes_gelezen__B=n)

        rijen = tabellen.bouw_etmaal(bron, etmaal_pad, max_bytes=max_bytes, op_voortgang=_op_voortgang_etmaal)
        manifest.voeg_toe("etmaal", "etmaal", etmaal_pad, uit_dir, rijen)
        voortgang.zet_voltooid(zipbron_mod.BOILER_24H_STATS)
    resultaten["etmaal_rijen"] = manifest.totaal_rijen("etmaal")

    voortgang.zet_fase("kleine_tabellen")
    for onderdeel, bouwer, bestandsnaam in (
        ("resultaten", tabellen.bouw_resultaten, "resultaten.parquet"),
        ("info_metadata", tabellen.bouw_info_metadata, "info_metadata.parquet"),
    ):
        pad = uit_dir / bestandsnaam
        if not manifest.is_voltooid(onderdeel, onderdeel, uit_dir):
            df = bouwer(bron)
            schrijf_parquet_atomisch(pad, df)
            manifest.voeg_toe(onderdeel, onderdeel, pad, uit_dir, len(df))
        resultaten[onderdeel + "_rijen"] = manifest.totaal_rijen(onderdeel)

    bron.sluit()

    voortgang.zet_fase("dekking")
    dekking_df = dekking_mod.bouw_dekking(uit_dir)
    dekking_pad = uit_dir / "dekking.parquet"
    schrijf_parquet_atomisch(dekking_pad, dekking_df)
    manifest.voeg_toe("dekking", "dekking", dekking_pad, uit_dir, len(dekking_df))
    resultaten["dekking_rijen"] = len(dekking_df)

    if docs_dir is not None:
        voortgang.zet_fase("kwaliteitsrapport")
        is_steekproef = test_mb is not None
        kwaliteitsrapport.schrijf_rapport(uit_dir, Path(docs_dir) / "data-quality.md", is_steekproef)

    voortgang.zet_fase("datapackage")
    datapackage_pad = datapackage_mod.schrijf_datapackage_voor_run(uit_dir, UITVOER_CONTRACT_VERSIE)
    resultaten["datapackage"] = str(datapackage_pad)

    voortgang.klaar()
    resultaten["duur__s"] = time.monotonic() - start
    log.info("Klaar in %.1f s", resultaten["duur__s"])
    return resultaten


def _droogloop(bron, uit_dir: Path, test_mb: int | None, min_vrije_schijfruimte__GB: float) -> dict:
    print(f"\nDroogloop: er wordt niets geschreven.\n")
    print(f"Bron: {bron.zip_pad}")
    for naam in zipbron_mod.VERPLICHTE_LEDEN:
        info = bron.info(naam)
        print(f"  {naam}: {info.file_size:,} bytes ontcomprimeerd, compress_type={info.compress_type}".replace(",", "."))

    bestaand_pad = uit_dir if uit_dir.exists() else uit_dir.parent
    if bestaand_pad.exists():
        vrij__GB = shutil.disk_usage(bestaand_pad).free / 1e9
        status = "OK" if vrij__GB >= min_vrije_schijfruimte__GB else "TE WEINIG"
        print(f"\nVrije schijfruimte op {bestaand_pad}: {vrij__GB:.1f} GB (minimum {min_vrije_schijfruimte__GB:.1f} GB) [{status}]")
    else:
        print(f"\nUitvoerpad {uit_dir} bestaat nog niet.")

    if uit_dir.exists():
        manifest = Manifest(uit_dir)
        for onderdeel in ("boiler_temp", "thermostat_temp", "etmaal", "resultaten", "info_metadata", "dekking"):
            n = len(manifest.voltooide_sleutels(onderdeel))
            if n:
                print(f"  {onderdeel}: {n} onderdeel/onderdelen al voltooid volgens het manifest")
    else:
        print("\nGeen eerdere uitvoer gevonden; een echte run zou vanaf nul beginnen.")

    print(f"\nmax_bytes per groot bronbestand: {test_mb * 1_000_000 if test_mb else 'onbegrensd (volledige run)'}")
    bron.sluit()
    return {"droogloop": True}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"), help="Pad naar het zip-bestand, of een map waarin het staat")
    p.add_argument("--uit", "--out-dir", dest="uit", type=Path, default=Path("data/processed"))
    p.add_argument("--docs-dir", type=Path, default=Path("docs"))
    p.add_argument("--test", action="store_true", help="Verwerk alleen de eerste --test-mb megabyte per groot bronbestand")
    p.add_argument("--test-mb", type=int, default=50, help="Aantal MB (ontcomprimeerd) per groot bronbestand bij --test (standaard 50)")
    p.add_argument("--opnieuw", action="store_true", help="Gooi een eerdere (gedeeltelijke) run weg en begin schoon")
    p.add_argument("--droogloop", action="store_true", help="Toon wat er zou gebeuren; schrijf niets")
    p.add_argument("--min-vrije-schijfruimte-gb", type=float, default=MIN_VRIJE_SCHIJFRUIMTE__GB)
    p.add_argument(
        "--lezer", choices=("pandas", "pyarrow"), default="pyarrow",
        help="Leesroute voor de twee grote minuutbestanden: 'pyarrow' (standaard, snel) of 'pandas' "
        "(oorspronkelijk, langzamer; voor de gelijkheidstoets)",
    )
    p.add_argument(
        "--block-size-mb", type=float, default=None,
        help="Blokgrootte (MB) voor de pyarrow-lezer (standaard: snelle_lezer.BLOCK_SIZE_STANDAARD, "
        "zie daar voor de meting waarop die standaard is gekozen). Alleen van invloed bij --lezer "
        "pyarrow.",
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
    run(
        args.raw_dir,
        args.uit,
        docs_dir=args.docs_dir,
        test_mb=args.test_mb if args.test else None,
        opnieuw=args.opnieuw,
        min_vrije_schijfruimte__GB=args.min_vrije_schijfruimte_gb,
        droogloop=args.droogloop,
        lezer=args.lezer,
        block_size_mb=args.block_size_mb,
    )


if __name__ == "__main__":
    main()
