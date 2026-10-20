# SPDX-License-Identifier: EUPL-1.2
"""Per-woning Parquet wegschrijven uit een gestreamde CSV-lezing (ontwerp-preprocessing.md §2 en §8).

**Twee schrijfstrategieën, gekozen op basis van een geverifieerde eigenschap van de bron in plaats
van aangenomen.** :func:`controleer_aaneengesloten` doet één streamende pas over alleen de
``House``-kolom en stelt vast of de rijen van elke woning aaneengesloten staan (niet noodzakelijk
alfabetisch gesorteerd, wel: als woning X eenmaal "voorbij" is, komt hij niet nog eens terug). Is dat
zo, dan is :func:`schrijf_per_woning_gesorteerd` toereikend: één streamende pas, op elk moment
hoogstens één ``ParquetWriter`` open, geheugengebruik onafhankelijk van de bestandsgrootte. Is dat
niet zo, dan is :func:`schrijf_per_woning_ongesorteerd` nodig: elke chunk wordt over deelbestanden
per woning per chunk verdeeld, en na de volledige pas per woning gecompacteerd met een
rijtellingcontrole (patroon van ``compacteer_per_minuut.py`` uit de extractie-zusterrepo).

**Geverifieerd tegen de echte bron (23-09-2026):** zowel ``boiler-temp.csv`` (243.041.542 rijen, 220
woningen) als ``thermostat-temp.csv`` (69.166.957 rijen, 223 woningen) zijn over hun VOLLEDIGE lengte
aaneengesloten per woning; geen enkele woning komt op twee plekken voor. De gesorteerde route is dus
de route die de volledige run werkelijk neemt; de ongesorteerde route bestaat voor de algemeenheid
van de pijplijn (een toekomstige KITE-update van de dataset hoeft niet dezelfde eigenschap te
behouden) en wordt getest met een synthetische, bewust ongesorteerde fixture.

**Hervatten bespaart transformatie- en schrijftijd, niet decompressietijd.** Geen van beide
compressievormen (Deflate, Deflate64) ondersteunt seeken naar een woning; een herstart leest het
bronbestand dus opnieuw vanaf het begin. Wat een herstart wél bespaart: voor elke woning die het
manifest al als voltooid kent, worden de kolomvertaling, de plausibiliteitsvlaggen en de
Parquet-schrijfactie overgeslagen (alleen de CSV-chunk zelf wordt nog geparsed, om door te kunnen
lezen naar de volgende woning). Dat is een bewuste, gedocumenteerde keuze: seeken zou een eigen
indexbestand vergen dat bij elke codewijziging opnieuw valide moet zijn, en de winst zit toch al
vooral in het overslaan van het dure werk (temperatuur-/debietvlaggen, floats naar Parquet), niet in
het overslaan van I/O.
"""

from __future__ import annotations

import logging
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterator

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import sentinels
from . import snelle_lezer
from . import tijd as tijd_mod
from . import zipbron as zipbron_mod
from .manifest import Manifest

log = logging.getLogger(__name__)

#: Standaardlezer voor de twee grote minuutbestanden (ontwerp-preprocessing.md §8, prestatieparagraaf):
#: ``pyarrow`` is de snelle route (zie ``snelle_lezer.py``), ``pandas`` is de oorspronkelijke route
#: en blijft bestaan als ``--lezer pandas`` zodat de gelijkheidstoets beide kan draaien.
LEZER_STANDAARD = "pyarrow"
LEZERS = ("pandas", "pyarrow")


class SorteerFout(ValueError):
    """De bron bleek tijdens het schrijven toch niet aaneengesloten per woning te zijn, terwijl de
    gesorteerde route al was gekozen. Dit hoort niet te gebeuren ná :func:`controleer_aaneengesloten`
    en is een harde fout: verdergaan zou rijen van dezelfde woning over twee bestanden verspreiden."""


class RijenverschilFout(ValueError):
    """Na het compacteren van de deelbestanden van een woning klopt het rijaantal niet met wat er
    tijdens de scatter-pas is weggeschreven."""


def controleer_aaneengesloten(
    bron,
    bestandsnaam: str,
    huiskolom_ruw: str = "House",
    chunksize: int = 2_000_000,
    lezer: str = LEZER_STANDAARD,
) -> bool:
    """Eén streamende pas over alleen ``huiskolom_ruw``: True als elke waarde aaneengesloten staat.

    Dit leest het VOLLEDIGE bronbestand (wel met ``usecols``/``include_columns``, dus zonder de
    andere kolommen te parsen). De uitkomst wordt door de pijplijn gecachet in ``_sortering.json``
    (zie ``pijplijn.py``), zodat een hervatte run dit niet herhaalt.

    ``lezer="pyarrow"`` (standaard) gebruikt ``snelle_lezer.controleer_aaneengesloten_snel``, dat
    dezelfde uitkomst geeft maar sneller is (ontwerp-preprocessing.md §8); ``lezer="pandas"``
    behoudt de oorspronkelijke, langzamere route, nodig voor de gelijkheidstoets.
    """
    if lezer == "pyarrow":
        return snelle_lezer.controleer_aaneengesloten_snel(bron, bestandsnaam, huiskolom_ruw=huiskolom_ruw)
    gezien: set[str] = set()
    laatste: str | None = None
    with bron.open_bron(bestandsnaam) as stream:
        for chunk in zipbron_mod.lees_csv_in_chunks(
            stream, chunksize=chunksize, dtype={huiskolom_ruw: str}, usecols=[huiskolom_ruw]
        ):
            for waarde in chunk[huiskolom_ruw].to_numpy():
                if waarde != laatste:
                    if waarde in gezien:
                        return False
                    gezien.add(waarde)
                    laatste = waarde
    return True


def _cast_naar_schema(df: pd.DataFrame, schema: pa.Schema) -> pa.Table:
    """Bouw een ``pyarrow.Table`` met exact ``schema``: expliciete cast in plaats van vertrouwen op
    ``pandas``-inferentie, zodat het schema van chunk tot chunk (en van woning tot woning) identiek
    blijft en de ``ParquetWriter`` nooit struikelt over een subtiel afwijkend type."""
    tabel = pa.Table.from_pandas(df, preserve_index=False)
    return tabel.select(schema.names).cast(schema)


def _transformeer_chunk(
    chunk: pd.DataFrame,
    kolommen_map: dict[str, str],
    tijdstip_naar_utc: Callable[[pd.Series], pd.Series] | None,
    flag_fn: Callable[[pd.DataFrame], pd.DataFrame],
) -> pd.DataFrame:
    chunk = chunk.rename(columns=kolommen_map)
    if tijdstip_naar_utc is not None:
        chunk["tijdstip"] = tijdstip_naar_utc(chunk["tijdstip"])
    return flag_fn(chunk)


def _pandas_chunks(
    stream,
    kolommen_map: dict[str, str],
    tijdstip_naar_utc: Callable[[pd.Series], pd.Series],
    chunksize: int,
    dtype_ruw: dict | None,
    na_values: list | None,
) -> Iterator[pd.DataFrame]:
    """De oorspronkelijke route: ``pandas.read_csv(..., chunksize=...)``, hernoemen, en dan
    ``tijdstip_naar_utc`` op de HELE chunk (niet meer per woninggroep zoals in de eerste versie: dat
    is een pure elementgewijze bewerking, dus het resultaat is bit-voor-bit gelijk, en één aanroep
    per chunk is goedkoper dan één per groep)."""
    for chunk in zipbron_mod.lees_csv_in_chunks(stream, chunksize=chunksize, dtype=dtype_ruw, na_values=na_values):
        chunk = chunk.rename(columns=kolommen_map)
        chunk["tijdstip"] = tijdstip_naar_utc(chunk["tijdstip"])
        yield chunk


def _pyarrow_chunks(
    stream,
    kolommen_map: dict[str, str],
    kolom_types_pyarrow: dict[str, pa.DataType],
    na_values: list | None,
    block_size: int,
    huiskolom_ruw: str,
    afgeronde_woningen: set[str],
    op_rijen_gelezen: Callable[[int], None] | None = None,
) -> Iterator[pd.DataFrame]:
    """De snelle route (``snelle_lezer.py``): ``pyarrow.csv`` met vaste kolomtypen, ``Time``
    rechtstreeks als ``timestamp(ns, UTC)``. Rijen van woningen die in een VORIGE run al voltooid
    waren, worden hier al op Arrow-niveau weggefilterd (``filtreer_voltooide_woningen``), vóór de
    pandas-conversie; dat is de goedkope-hervat-eis uit ontwerp-preprocessing.md §8.

    ``op_rijen_gelezen(n)`` wordt na ELKE gelezen Arrow-batch aangeroepen met het cumulatieve aantal
    RUW gelezen rijen (vóór de hervat-filter), ook als die batch daarna volledig wordt weggefilterd
    en dus zelf niet ge-yield wordt. Zonder dit bleef ``_voortgang.json`` op 0 rijen staan zolang een
    hervatte run alleen al voltooide woningen aan het overslaan was (die batches worden nooit
    ge-yield, dus een teller die alleen ge-yielde chunks optelt komt nooit verder dan 0); zie
    VOORTGANG.md, "Eerste volledige run", punt 1."""
    rijen_gelezen_ruw = 0
    for batch in snelle_lezer.lees_batches(stream, kolom_types_pyarrow, extra_null_values=na_values, block_size=block_size):
        rijen_gelezen_ruw += batch.num_rows
        if op_rijen_gelezen is not None:
            op_rijen_gelezen(rijen_gelezen_ruw)
        batch = snelle_lezer.filtreer_voltooide_woningen(batch, huiskolom_ruw, afgeronde_woningen)
        if batch.num_rows == 0:
            continue
        chunk = snelle_lezer.batch_naar_pandas(batch)
        chunk = chunk.rename(columns=kolommen_map)
        yield chunk


def schrijf_per_woning_gesorteerd(
    bron,
    bestandsnaam: str,
    kolommen_map: dict[str, str],
    tijdstip_naar_utc: Callable[[pd.Series], pd.Series],
    flag_fn: Callable[[pd.DataFrame], pd.DataFrame],
    schema: pa.Schema,
    uit_dir: Path,
    onderdeel: str,
    manifest: Manifest,
    chunksize: int = zipbron_mod.CHUNKSIZE_STANDAARD,
    max_bytes: int | None = None,
    dtype_ruw: dict | None = None,
    na_values: list | None = None,
    op_voortgang: Callable[[int, int], None] | None = None,
    lezer: str = LEZER_STANDAARD,
    kolom_types_pyarrow: dict[str, pa.DataType] | None = None,
    block_size: int = snelle_lezer.BLOCK_SIZE_STANDAARD,
    huiskolom_ruw: str = "House",
) -> dict[str, int]:
    """Schrijf ``bestandsnaam`` streamend naar één Parquet-bestand per woning
    (``<uit_dir>/<onderdeel>/home_id=<id>.parquet``).

    Vereist dat de bron aaneengesloten per woning staat (zie ``controleer_aaneengesloten``); dit
    wordt tijdens het schrijven zelf nogmaals bewaakt (een woning die na sluiting van zijn writer
    toch opnieuw opduikt, is een :class:`SorteerFout`, geen stille datacorruptie).

    ``op_voortgang(bytes_gelezen, rijen_gelezen)`` wordt na elke chunk aangeroepen.

    ``lezer``: ``"pyarrow"`` (standaard) gebruikt de snelle route uit ``snelle_lezer.py`` en vereist
    dan ``kolom_types_pyarrow``; ``"pandas"`` behoudt de oorspronkelijke, langzamere route. Beide
    routes leveren, tot en met het cast-naar-schema-punt, bit-voor-bit dezelfde uitvoer (zie
    ``tests/test_snelle_lezer_gelijkheid.py``): alleen het stuk "bytes uit de zip -> pandas-chunk
    met vertaalde kolomnamen en al UTC-tijdstip" verschilt.

    Retourneert ``{home_id: aantal_rijen}`` voor de woningen die deze aanroep daadwerkelijk
    geschreven heeft (al voltooide woningen, zie de moduledocstring, staan er niet in).
    """
    uit_map = uit_dir / onderdeel
    uit_map.mkdir(parents=True, exist_ok=True)

    resultaat: dict[str, int] = {}
    afgeronde_woningen: set[str] = set(manifest.voltooide_sleutels(onderdeel))
    gesloten_deze_run: set[str] = set()

    huidige_home: str | None = None
    huidige_writer: pq.ParquetWriter | None = None
    huidige_tmp_pad: Path | None = None
    huidige_rijen = 0
    rijen_gelezen_totaal = 0
    #: Alle tijdstippen (int64 ns sinds epoch) die voor de HUIDIGE woning al gezien zijn, over
    #: chunkgrenzen heen; zie sentinels.flag_tijdstip_dubbel voor waarom dit een set moet zijn (de
    #: bron is niet op tijd gesorteerd binnen een woning) en niet volstaat met "vergelijk met de
    #: vorige rij". Wordt leeggemaakt zodra een nieuwe woning begint (woningen zijn zelf wél
    #: aaneengesloten, zie de moduledocstring), zodat het geheugengebruik hoogstens één woning groot
    #: is, niet het hele bestand.
    huidige_tijdstip_gezien: set[int] = set()

    def _sluit_huidige() -> None:
        nonlocal huidige_home, huidige_writer, huidige_tmp_pad, huidige_rijen
        if huidige_writer is not None:
            huidige_writer.close()
            eind_pad = uit_map / f"home_id={huidige_home}.parquet"
            huidige_tmp_pad.replace(eind_pad)
            manifest.voeg_toe(onderdeel, huidige_home, eind_pad, uit_dir, huidige_rijen)
            resultaat[huidige_home] = huidige_rijen
            gesloten_deze_run.add(huidige_home)
            log.info("%s: woning %s klaar, %d rij(en)", onderdeel, huidige_home, huidige_rijen)
        huidige_home = None
        huidige_writer = None
        huidige_tmp_pad = None
        huidige_rijen = 0

    def _bytes_callback(n: int) -> None:
        if op_voortgang is not None:
            op_voortgang(n, rijen_gelezen_totaal)

    def _rijen_callback(n: int) -> None:
        # Alleen gebruikt bij lezer="pyarrow" (zie hieronder): n is het cumulatieve aantal RUW
        # gelezen rijen, óók als de batch erna volledig wegvalt door de hervat-filter. Direct
        # rapporteren (in plaats van te wachten tot de volgende ge-yielde chunk) is precies de fix
        # voor het "rijen_gelezen blijft 0"-probleem uit VOORTGANG.md.
        nonlocal rijen_gelezen_totaal
        rijen_gelezen_totaal = n
        if op_voortgang is not None:
            op_voortgang(-1, rijen_gelezen_totaal)

    if lezer not in LEZERS:
        raise ValueError(f"onbekende lezer {lezer!r}, verwacht een van {LEZERS}")
    if lezer == "pyarrow" and kolom_types_pyarrow is None:
        raise ValueError("lezer='pyarrow' vereist kolom_types_pyarrow")

    with bron.open_bron(bestandsnaam, max_bytes=max_bytes, op_voortgang=_bytes_callback) as stream:
        if lezer == "pyarrow":
            chunks = _pyarrow_chunks(
                stream, kolommen_map, kolom_types_pyarrow, na_values, block_size, huiskolom_ruw, afgeronde_woningen,
                op_rijen_gelezen=_rijen_callback,
            )
        else:
            chunks = _pandas_chunks(stream, kolommen_map, tijdstip_naar_utc, chunksize, dtype_ruw, na_values)

        for chunk in chunks:
            if lezer != "pyarrow":
                # De pandas-route filtert nooit vóór het yielden (elke gelezen chunk wordt altijd
                # volledig ge-yield; het overslaan van al voltooide woningen gebeurt pas hieronder,
                # per groep), dus len(chunk) is hier al het juiste RUWE aantal.
                rijen_gelezen_totaal += len(chunk)
            for home, groep in chunk.groupby("home_id__str", sort=False):
                if home == huidige_home:
                    pass  # ga door met de al open writer voor deze woning
                elif home in gesloten_deze_run:
                    # Al gesloten (deze run) en nu toch weer terug: de bron is niet aaneengesloten.
                    raise SorteerFout(
                        f"{bestandsnaam}: woning {home} komt opnieuw voor nadat hij al gesloten "
                        "was; de bron is toch niet aaneengesloten per woning."
                    )
                elif home in afgeronde_woningen:
                    # Hervatting: deze woning was in een VORIGE run al klaar. Sla het dure werk over
                    # (geen vlaggen, geen schrijfactie), maar lees door (zie moduledocstring:
                    # hervatten bespaart transformatie/schrijven, geen I/O). Bij lezer="pyarrow" is
                    # dit al op Arrow-niveau weggefilterd (_pyarrow_chunks); deze tak is dan dode
                    # code die als veiligheidsnet blijft staan.
                    continue
                else:
                    _sluit_huidige()
                    huidige_home = home
                    huidige_tmp_pad = uit_map / f"home_id={home}.parquet.tmp"
                    huidige_tijdstip_gezien = set()
                groep = _transformeer_chunk(groep, {}, None, flag_fn)
                # flag_fn (sentinels.flag_*) doet al een df.copy(): groep hieronder muteren is dus
                # veilig, geen aliasing met de oorspronkelijke chunk.
                groep["q_flag_tijdstip_dubbel__bool"] = sentinels.flag_tijdstip_dubbel(
                    groep["tijdstip"].astype("int64"), huidige_tijdstip_gezien
                )
                # Allerlaatste stap: UTC -> weergavezone (tijd.naar_weergave_tijdzone), NA de
                # dedupvlag (die werkt op de tz-onafhankelijke epoch-waarde) en VOOR het schrijven.
                groep["tijdstip"] = tijd_mod.naar_weergave_tijdzone(groep["tijdstip"])
                tabel = _cast_naar_schema(groep, schema)
                if huidige_writer is None:
                    huidige_writer = pq.ParquetWriter(huidige_tmp_pad, schema, compression="zstd")
                huidige_writer.write_table(tabel)
                huidige_rijen += len(groep)
            if op_voortgang is not None:
                op_voortgang(-1, rijen_gelezen_totaal)  # -1: alleen rijen bijwerken, bytes komt via de stream-callback

    _sluit_huidige()
    return resultaat


def schrijf_per_woning_ongesorteerd(
    bron,
    bestandsnaam: str,
    kolommen_map: dict[str, str],
    tijdstip_naar_utc: Callable[[pd.Series], pd.Series],
    flag_fn: Callable[[pd.DataFrame], pd.DataFrame],
    schema: pa.Schema,
    uit_dir: Path,
    onderdeel: str,
    manifest: Manifest,
    chunksize: int = zipbron_mod.CHUNKSIZE_STANDAARD,
    max_bytes: int | None = None,
    dtype_ruw: dict | None = None,
    na_values: list | None = None,
    op_voortgang: Callable[[int, int], None] | None = None,
) -> dict[str, int]:
    """Fallback voor een NIET aaneengesloten bron: verdeel elke chunk over deelbestanden per woning
    per chunk, en compacteer daarna per woning met een rijtellingcontrole (zie de moduledocstring).
    """
    tijdelijk_dir = uit_dir / "_tijdelijk" / onderdeel
    tijdelijk_dir.mkdir(parents=True, exist_ok=True)
    afgeronde_woningen = set(manifest.voltooide_sleutels(onderdeel))

    rijen_per_home: dict[str, int] = defaultdict(int)
    rijen_gelezen_totaal = 0
    #: Net als bij de gesorteerde route (zie daar): per woning een set met alle al geziene
    #: tijdstippen, hier ÉÉN dict voor alle woningen tegelijk, want in deze route lopen de woningen
    #: door elkaar (dat is precies waarom deze route bestaat). De chunks worden hier wel strikt op
    #: bronvolgorde verwerkt (chunk 0, 1, 2, ...; binnen een chunk bewaart `groupby(sort=False)` de
    #: volgorde van eerste voorkomen), dus de dedupcontrole ziet elke woning in dezelfde volgorde als
    #: het bronbestand, ook al liggen de chunks van dezelfde woning niet aaneengesloten.
    gezien_tijdstippen_per_home: dict[str, set[int]] = defaultdict(set)

    def _bytes_callback(n: int) -> None:
        if op_voortgang is not None:
            op_voortgang(n, rijen_gelezen_totaal)

    with bron.open_bron(bestandsnaam, max_bytes=max_bytes, op_voortgang=_bytes_callback) as stream:
        for i, chunk in enumerate(zipbron_mod.lees_csv_in_chunks(stream, chunksize=chunksize, dtype=dtype_ruw, na_values=na_values)):
            rijen_gelezen_totaal += len(chunk)
            chunk = _transformeer_chunk(chunk, kolommen_map, tijdstip_naar_utc, flag_fn)
            for home, groep in chunk.groupby("home_id__str", sort=False):
                if home in afgeronde_woningen:
                    continue
                groep = groep.copy()
                groep["q_flag_tijdstip_dubbel__bool"] = sentinels.flag_tijdstip_dubbel(
                    groep["tijdstip"].astype("int64"), gezien_tijdstippen_per_home[home]
                )
                groep["tijdstip"] = tijd_mod.naar_weergave_tijdzone(groep["tijdstip"])
                deel_pad = tijdelijk_dir / f"{home}__deel_{i:06d}.parquet"
                tabel = _cast_naar_schema(groep, schema)
                pq.write_table(tabel, deel_pad, compression="zstd")
                rijen_per_home[home] += len(groep)
            if op_voortgang is not None:
                op_voortgang(-1, rijen_gelezen_totaal)

    uit_map = uit_dir / onderdeel
    uit_map.mkdir(parents=True, exist_ok=True)
    resultaat: dict[str, int] = {}
    for home, verwacht in rijen_per_home.items():
        delen = sorted(tijdelijk_dir.glob(f"{home}__deel_*.parquet"))
        eind_pad = uit_map / f"home_id={home}.parquet"
        tmp = eind_pad.with_suffix(".parquet.tmp")
        writer = pq.ParquetWriter(tmp, schema, compression="zstd")
        geschreven = 0
        try:
            for deel in delen:
                tabel = pq.read_table(deel)
                writer.write_table(tabel)
                geschreven += tabel.num_rows
        finally:
            writer.close()
        if geschreven != verwacht:
            tmp.unlink(missing_ok=True)
            raise RijenverschilFout(
                f"{onderdeel}/{home}: {geschreven} rij(en) gecompacteerd, {verwacht} verwacht "
                "uit de scatter-pas."
            )
        tmp.replace(eind_pad)
        manifest.voeg_toe(onderdeel, home, eind_pad, uit_dir, geschreven)
        resultaat[home] = geschreven
        for deel in delen:
            deel.unlink()

    shutil.rmtree(tijdelijk_dir, ignore_errors=True)
    return resultaat
