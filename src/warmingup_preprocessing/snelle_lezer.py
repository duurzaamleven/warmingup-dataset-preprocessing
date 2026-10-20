# SPDX-License-Identifier: EUPL-1.2
"""Snelle CSV-leesroute met ``pyarrow.csv`` voor de twee grote minuutbestanden
(ontwerp-preprocessing.md §2 en §8, prestatieparagraaf).

**Waarom dit bestaat.** Een cProfile-run op de volledige pijplijn liet zien dat
:func:`schrijf_per_woning_gesorteerd` (``schrijvers.py``) ~64% van zijn tijd kwijt was aan
``tijd.naar_utc_tijdstip`` (``pandas.to_datetime`` met een expliciet formaat, dat toch op de trage
``_array_strptime_with_fallback``-route terechtkwam) en ~37% aan ``pandas.read_csv`` zelf. Op een
benchmark van 1.000.000 tijdstempels bleek ``pyarrow.csv`` met expliciete kolomtypen ruim 5x sneller
dan de pandas-C-parser + losse ``strptime``-stap, met identieke waarden.

**Bit-voor-bit dezelfde uitvoer, andere lezer.** Deze module vervangt UITSLUITEND het stuk tussen
"bytes uit de zip" en "een pandas-``DataFrame`` met dezelfde kolomnamen en dtypes alsof
``pandas.read_csv`` het gelezen had". Alles daarna (hernoemen, vlaggen berekenen met
``sentinels.flag_*``, casten naar het Parquet-schema) blijft ONGEWIJZIGD in ``schrijvers.py``: de
vergelijkbaarheid met de oude route staat of valt met dat ene punt, en die is met een gelijkheidstoets
bewaakt (``tests/test_snelle_lezer_gelijkheid.py`` en de handmatige vergelijking in
``ontwerp-preprocessing.md`` §8).

**Wat hier expliciet wordt gemaakt, in plaats van aan ``pyarrow``-inferentie overgelaten:**

* ``column_types``: elke kolom krijgt een vast Arrow-type. Zonder dit baseert ``pyarrow.csv`` zijn
  typeninferentie op het EERSTE blok van de stream; bij een bestand van honderden miljoenen rijen,
  in blokken van enkele tientallen MB gelezen, zou een latere afwijking (bijvoorbeeld een kolom die
  pas na blok 400 voor het eerst leeg is) een verrassende typewisseling of foutmelding kunnen geven.
  Met een vast type is het gedrag voorspelbaar en gelijk aan wat ``dtype_ruw``/het Parquet-schema al
  afdwingen.
* ``null_values``/``strings_can_be_null``: hiermee wordt de tekstsentinel ``"x"``
  (``sentinels.TEMP_AANVOER_TEKST_SENTINEL``) hetzelfde behandeld als ``pandas.read_csv(...,
  na_values=[...])`` doet: als ontbrekende waarde, niet als string die de hele kolom naar tekst
  dwingt. ``pyarrow``'s eigen standaardlijst met NA-teksten (lege string, ``NA``, ``NULL``, ``NaN``,
  ...) is vrijwel gelijk aan die van ``pandas``; deze module vult ``"x"`` er alleen aan toe waar de
  bron dat vraagt (``boiler-temp.csv``), precies zoals ``BOILER_TEMP_NA_VALUES`` dat nu al doet.
* De ``Time``-kolom wordt rechtstreeks als ``timestamp(ns, UTC)`` gevraagd. ``pyarrow`` herkent
  ``2021-11-05T09:27:00Z`` (ISO-8601 met ``Z``) zonder een apart formaat te hoeven opgeven, en
  geverifieerd (zie de gelijkheidstoets) tegen ``pandas.to_datetime(..., format="%Y-%m-%dT%H:%M:%SZ",
  utc=True)``: dezelfde waarden, alleen sneller berekend.
"""

from __future__ import annotations

import io
from typing import Iterable, Iterator

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

#: Bescheiden blokgrootte (ontwerp-eis: het systeem heeft tijdens de volledige run maar enkele
#: honderden MB vrij naast het lopende hoofdproces).
#:
#: Gemeten op ``--test --test-mb 200`` tegen de echte bron (23-09-2026, rustige machine, geen andere
#: run mee actief), piekgeheugen met ``psutil`` bemonsterd elke 0,2 s:
#:
#: | block_size | duur | doorvoer (rijen/s) | piekgeheugen (RSS) |
#: |---|---:|---:|---:|
#: | 32 MB | 470,8 s | 22.584 | 599,1 MB |
#: | 16 MB | 512,4 s | 20.748 | **561,5 MB** |
#: | 8 MB  | 610,1 s | 17.427 | 611,2 MB |
#:
#: Piekgeheugen daalt NIET monotoon met een kleinere blokgrootte (8 MB gaf zelfs het hoogste
#: piekgeheugen van de drie, niet het laagste); alleen de doorvoer daalt wel duidelijk en monotoon
#: naarmate het blok kleiner wordt. 16 MB is dus gekozen omdat het op deze meting het laagste
#: piekgeheugen gaf tegen een bescheiden doorvoerverlies (8% trager dan 32 MB, tegenover 23% trager
#: bij 8 MB) -- niet omdat "kleiner is altijd zuiniger" hier klopt.
#:
#: **Kanttekening.** Deze meting (200 MB per bronbestand, circa 5,1 + 5,5 miljoen rijen) is veel
#: kleiner dan de volledige run (243 + 69 miljoen rijen) waarin een piek van 1,5 GB werd gezien
#: (VOORTGANG.md); de standaard Arrow-geheugenpool geeft vrijgegeven blokken niet aan het systeem
#: terug (zie ook de toelichting in ``draai_volledig.cmd`` bij ``ARROW_DEFAULT_MEMORY_POOL=system``),
#: dus de commit charge kan bij veel meer chunks/woningen achter elkaar verder oplopen dan hier
#: gemeten. ``block_size`` alleen verklaart het verschil tussen 599-611 MB hier en 1,5 GB in de
#: volledige run dus vermoedelijk niet volledig; de geheugenpoolinstelling in ``draai_volledig.cmd``
#: is daar waarschijnlijk minstens zo belangrijk voor.
BLOCK_SIZE_STANDAARD = 16 << 20

#: ``pyarrow``'s eigen standaard-NA-teksten (leeg, "NA", "NULL", "NaN", ...), als vast startpunt.
#: Bepaald bij importtijd (``pyarrow.csv.ConvertOptions()`` zonder argumenten) zodat een toekomstige
#: ``pyarrow``-versie met een andere standaardlijst hier niet stilzwijgend een ander gedrag geeft.
NULL_VALUES_STANDAARD: tuple[str, ...] = tuple(pacsv.ConvertOptions().null_values)


def _open_reader(
    stream: io.IOBase,
    column_types: dict[str, pa.DataType],
    extra_null_values: Iterable[str] | None,
    block_size: int,
) -> pacsv.CSVStreamingReader:
    null_values = list(NULL_VALUES_STANDAARD)
    if extra_null_values:
        null_values += list(extra_null_values)
    read_options = pacsv.ReadOptions(block_size=block_size)
    convert_options = pacsv.ConvertOptions(
        column_types=column_types,
        null_values=null_values,
        strings_can_be_null=True,
    )
    return pacsv.open_csv(stream, read_options=read_options, convert_options=convert_options)


def lees_batches(
    stream: io.IOBase,
    column_types: dict[str, pa.DataType],
    extra_null_values: Iterable[str] | None = None,
    block_size: int = BLOCK_SIZE_STANDAARD,
) -> Iterator[pa.RecordBatch]:
    """Streamende ``pyarrow.csv``-lezing: geeft Arrow ``RecordBatch``'es terug (nog GEEN pandas).

    Gebruikt door :func:`filtreer_en_naar_pandas` (de hoofdroute in ``schrijvers.py``) en door de
    snelle sorteringscontrole (:func:`controleer_aaneengesloten_snel`), die alleen de huiskolom
    nodig heeft en dus zelf een beperktere ``column_types`` meegeeft.
    """
    reader = _open_reader(stream, column_types, extra_null_values, block_size)
    for batch in reader:
        yield batch


def filtreer_voltooide_woningen(
    batch: pa.RecordBatch, huiskolom_ruw: str, afgeronde_woningen: set[str]
) -> pa.RecordBatch:
    """Verwijder rijen van woningen die al voltooid zijn, VOORDAT naar pandas geconverteerd wordt.

    Dit is de kern van goedkoop hervatten (ontwerp-preprocessing.md §8): bij een hervatte run zijn
    de meeste woningen in een batch vaak al klaar, en het kost dan niets om ze te vertalen, te
    vlaggen of weg te schrijven -- het enige dat nog moet gebeuren is doorlezen tot de eerste NIET
    al voltooide woning. ``pyarrow.compute.is_in`` werkt rechtstreeks op de Arrow-kolom, dus dit
    filter kost geen pandas-conversie voor de rijen die toch worden weggegooid.
    """
    if not afgeronde_woningen:
        return batch
    kolom = batch.column(huiskolom_ruw)
    voltooid_mask = pc.is_in(kolom, value_set=pa.array(sorted(afgeronde_woningen), type=kolom.type))
    return batch.filter(pc.invert(voltooid_mask))


def batch_naar_pandas(batch: pa.RecordBatch) -> pd.DataFrame:
    """``RecordBatch`` naar ``pandas.DataFrame``, met dezelfde dtype-uitkomsten als de rest van de
    pijplijn verwacht (numpy-backed, geen ``pyarrow``-backed pandas-dtypes: ``sentinels.py`` en
    ``tijd.py`` doen gewone ``numpy``/``pandas``-bewerkingen op deze kolommen)."""
    return batch.to_pandas(types_mapper=None)


def _kolom_naar_runs(kolom: pa.Array | pa.ChunkedArray) -> list[str]:
    """De WAARDEN van ``kolom`` gereduceerd tot "runs": elke aaneengesloten reeks gelijke waarden
    wordt precies één keer teruggegeven, in volgorde. Bijvoorbeeld ``[A, A, A, B, B, C]`` -> ``[A, B,
    C]``. Volledig vectoraal (``numpy``-vergelijking van ``arr[1:] != arr[:-1]``): geen Python-lus
    over elke rij, alleen over het veel kleinere aantal RUNS. Zie
    :func:`controleer_aaneengesloten_snel` voor waarom dit ertoe doet."""
    arr = kolom.to_numpy(zero_copy_only=False)
    n = len(arr)
    if n == 0:
        return []
    veranderd = np.empty(n, dtype=bool)
    veranderd[0] = True
    veranderd[1:] = arr[1:] != arr[:-1]
    return arr[veranderd].tolist()


def controleer_aaneengesloten_snel(
    bron,
    bestandsnaam: str,
    huiskolom_ruw: str = "House",
    block_size: int = BLOCK_SIZE_STANDAARD,
    max_bytes: int | None = None,
) -> bool:
    """Zelfde controle als ``schrijvers.controleer_aaneengesloten``, maar leest met ``pyarrow.csv``
    en ALLEEN de huiskolom (``include_columns``): geen andere kolom wordt geparsed of naar pandas
    omgezet. Retourneert True als elke woningwaarde aaneengesloten in het bestand staat.

    ``max_bytes`` begrenst net als bij ``ZipBron.open_bron`` het aantal ontcomprimeerde bytes; de
    pijplijn gebruikt dit voor de begrensde sorteringscontrole van een ``--test``-run.

    **Vectoraal, sinds repair 5 (profiling, 23-09-2026).** Een cProfile-meting op een rustige
    machine (geen andere run mee actief) van de sorteringscontrole van ``thermostat-temp.csv``
    (Deflate64) liet zien waar de tijd heen ging, over 439 MB / 10.157.401 rijen: 64% in
    ``inflate64.Inflater.inflate`` (de decompressie zelf, inherent aan Deflate64, niet te
    versnellen zonder een andere decompressor), 14% in de schijf-I/O
    (``io.BufferedReader.read``, eveneens inherent), en **16% in de Python-lus die vóór deze fix
    over ELKE RIJ ging** (``for waarde in batch.column(...).to_pylist(): ...``). Dat laatste deel is
    wél te vermijden: :func:`_kolom_naar_runs` reduceert een batch tot zijn aaneengesloten "runs"
    met een vectorale ``numpy``-vergelijking, zodat de Python-lus alleen nog over het aantal
    woningwissels loopt (bij een aaneengesloten bestand: hoogstens het aantal woningen in het hele
    bestand, niet het aantal rijen). Voor `thermostat-temp.csv` (69.166.957 rijen, 223 woningen)
    scheelt dat in het beste geval een factor van meer dan 300.000. Gemeten op dezelfde 439 MB-
    steekproef: geen meetbare regressie in de decompressie- of I/O-tijd (die twee lagen zijn
    ongewijzigd), en de Python-lus zelf verdwijnt vrijwel volledig uit het cProfile-profiel.
    """
    gezien: set[str] = set()
    laatste: str | None = None
    with bron.open_bron(bestandsnaam, max_bytes=max_bytes) as stream:
        read_options = pacsv.ReadOptions(block_size=block_size)
        convert_options = pacsv.ConvertOptions(
            column_types={huiskolom_ruw: pa.string()},
            include_columns=[huiskolom_ruw],
            null_values=list(NULL_VALUES_STANDAARD),
            strings_can_be_null=True,
        )
        reader = pacsv.open_csv(stream, read_options=read_options, convert_options=convert_options)
        for batch in reader:
            for waarde in _kolom_naar_runs(batch.column(huiskolom_ruw)):
                if waarde != laatste:
                    if waarde in gezien:
                        return False
                    gezien.add(waarde)
                    laatste = waarde
    return True
