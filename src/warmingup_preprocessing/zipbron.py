# SPDX-License-Identifier: EUPL-1.2
"""Streamend lezen uit ``data-en-resultaten.zip``, nooit uitgepakt naar schijf
(ontwerp-preprocessing.md §1; GEBRUIKSVOORWAARDEN.md).

Ondersteund wordt de versie van 27-10-2026 van de bron, zonder ``mapping.csv`` en zonder logger- en
serienummers; die heeft vijf leden. Vier daarvan staan met gewone Deflate in het archief en zijn met
``zipfile`` te openen; ``thermostat-temp.csv`` staat met Deflate64 en gaat via ``deflate64.open_deflate64`` (zie die
module). Deze module verbergt dat onderscheid achter één ``open_bron``-methode.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Callable, Iterator

import pandas as pd

from . import deflate64

BOILER_TEMP = "boiler-temp.csv"
THERMOSTAT_TEMP = "thermostat-temp.csv"
BOILER_24H_STATS = "boiler-24h-stats.csv"
README = "README.md"
RESULTATEN_XLSX = "resultaat-tabel-WarmingUP_KITE openbare versie.xlsx"

#: De vijf verplichte leden van het archief; ontbreekt er één, dan is het geen bruikbare bron.
VERPLICHTE_LEDEN = (BOILER_TEMP, THERMOSTAT_TEMP, BOILER_24H_STATS, README, RESULTATEN_XLSX)

#: Bestandsnamen waarvan de omvang zo groot is dat ze per woning worden opgesplitst; de rest wordt
#: als één geheel gelezen (ontwerp-preprocessing.md §2).
GROTE_MINUUTBESTANDEN = (BOILER_TEMP, THERMOSTAT_TEMP)

#: Standaard chunkgrootte voor ``pandas.read_csv(..., chunksize=...)`` op de grote bestanden.
CHUNKSIZE_STANDAARD = 250_000


class BronError(ValueError):
    """De opgegeven ruwe-databron is niet bruikbaar."""


class ZipBron:
    """Het gedownloade ``data-en-resultaten.zip``, uitsluitend streamend gelezen."""

    def __init__(self, zip_pad: str | Path):
        self.zip_pad = Path(zip_pad)
        if not self.zip_pad.is_file():
            raise BronError(f"Geen bestand: {self.zip_pad}")
        self._zip = zipfile.ZipFile(self.zip_pad)
        namen = set(self._zip.namelist())
        ontbrekend = [n for n in VERPLICHTE_LEDEN if n not in namen]
        if ontbrekend:
            raise BronError(f"{self.zip_pad.name}: ontbrekende leden {ontbrekend}")

    def sluit(self) -> None:
        self._zip.close()

    def __enter__(self) -> "ZipBron":
        return self

    def __exit__(self, *exc) -> None:
        self.sluit()

    def info(self, naam: str) -> zipfile.ZipInfo:
        return self._zip.getinfo(naam)

    def ongecomprimeerde_omvang(self, naam: str) -> int:
        """``file_size``: de omvang NA decompressie, gebruikt als noemer voor de voortgang."""
        return self._zip.getinfo(naam).file_size

    def open_bron(
        self,
        naam: str,
        max_bytes: int | None = None,
        op_voortgang: Callable[[int], None] | None = None,
    ) -> io.IOBase:
        """Open lid ``naam`` streamend, ongeacht compressietype (Deflate of Deflate64).

        ``max_bytes`` (gebruikt door ``--test``, zie ``pijplijn.py``) begrenst het aantal
        GEDECOMPRIMEERDE bytes dat maximaal wordt teruggegeven: de onderliggende stream raakt
        "leeg" zodra de grens bereikt is, ook al is het bronbestand nog niet uit. Dat is de
        testrun-eis uit de taak: alleen de eerste N MB per bronbestand lezen, zodat een testrun in
        minuten klaar is in plaats van in het kwartier dat de volledige bestanden vragen.
        """
        info = self.info(naam)
        if info.compress_type == 9:
            ruw: io.RawIOBase = deflate64.Deflate64Stream(self.zip_pad, info, op_voortgang=op_voortgang)
        else:
            ruw = _TelendeStream(self._zip.open(naam), op_voortgang=op_voortgang)
        stream: io.RawIOBase = _BegrensdeStream(ruw, max_bytes) if max_bytes is not None else ruw
        return io.BufferedReader(stream, buffer_size=1 << 20)

    def lees_resultaten_ruw(self) -> pd.DataFrame:
        """De resultatentabel (blad ``Sheet1``), header op rij 5. Klein (212 rijen), in één keer."""
        from .kolommen import RESULTATEN_HEADER_RIJ

        data = self._zip.read(RESULTATEN_XLSX)
        return pd.read_excel(io.BytesIO(data), sheet_name="Sheet1", header=RESULTATEN_HEADER_RIJ)

    def lees_info_blad_ruw(self) -> pd.DataFrame:
        """Het ``info``-blad van de resultatentabel, ruw (geen kop, geen vertaling): metadata over
        hoe de tabel gemaakt is (ontwerp-preprocessing.md §2)."""
        data = self._zip.read(RESULTATEN_XLSX)
        return pd.read_excel(io.BytesIO(data), sheet_name="info", header=None)

    def lees_readme(self) -> str:
        return self._zip.read(README).decode("utf-8")


class _TelendeStream(io.RawIOBase):
    """Wikkelt een leesbare bytestream in en roept ``op_voortgang`` aan met het cumulatieve aantal
    gelezen (= gedecomprimeerde, want ``zipfile.ZipExtFile`` decomprimeert al) bytes."""

    def __init__(self, onderliggend: io.IOBase, op_voortgang: Callable[[int], None] | None = None):
        super().__init__()
        self._onderliggend = onderliggend
        self._op_voortgang = op_voortgang
        self._gelezen = 0

    def readable(self) -> bool:  # pragma: no cover - triviaal
        return True

    def readinto(self, b) -> int:
        n = self._onderliggend.readinto(b)
        if n:
            self._gelezen += n
            if self._op_voortgang is not None:
                self._op_voortgang(self._gelezen)
        return n

    def close(self) -> None:
        if not self.closed:
            self._onderliggend.close()
        super().close()


class _BegrensdeStream(io.RawIOBase):
    """Laat de onderliggende stream leeg lijken zodra ``max_bytes`` gedecomprimeerde bytes gelezen
    zijn, ook als er in werkelijkheid nog meer volgt. Zie ``ZipBron.open_bron`` voor waarom.

    **Stopt op een regelgrens, niet op een willekeurige byte.** Een harde afkap midden in een CSV-
    regel zou een kapotte laatste rij aan ``pandas.read_csv`` voeren (geverifieerd: dat gaf een
    ``ValueError`` op een afgebroken tijdstempel). Zodra het budget op is, leest deze stream door tot
    de eerstvolgende ``\\n`` en stopt dan pas: de laatste regel van een ``--test``-run is dus altijd
    compleet, ook al is de exacte hoeveelheid gelezen data een fractie groter dan ``max_bytes``.
    """

    def __init__(self, onderliggend: io.IOBase, max_bytes: int):
        super().__init__()
        self._onderliggend = onderliggend
        self._resterend_budget = max_bytes
        self._buf = b""
        self._laatste_regel_gelezen = False
        self._klaar = False

    def readable(self) -> bool:  # pragma: no cover - triviaal
        return True

    def _vul(self) -> None:
        if self._buf or self._klaar:
            return
        if self._laatste_regel_gelezen:
            self._klaar = True
            return
        blok = self._onderliggend.read(min(1 << 16, max(self._resterend_budget, 1)))
        if not blok:
            self._klaar = True
            return
        self._resterend_budget -= len(blok)
        self._buf = blok
        if self._resterend_budget <= 0:
            while b"\n" not in self._buf:
                extra = self._onderliggend.read(1 << 16)
                if not extra:
                    break
                self._buf += extra
            nl = self._buf.find(b"\n")
            if nl != -1:
                self._buf = self._buf[: nl + 1]
            self._laatste_regel_gelezen = True

    def readinto(self, b) -> int:
        self._vul()
        if not self._buf:
            return 0
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n

    def close(self) -> None:
        if not self.closed:
            self._onderliggend.close()
        super().close()


def lees_csv_in_chunks(
    stream: io.IOBase,
    chunksize: int = CHUNKSIZE_STANDAARD,
    dtype: dict | None = None,
    na_values: list | None = None,
    usecols: list | None = None,
) -> Iterator[pd.DataFrame]:
    """Dunne wrapper om ``pandas.read_csv(..., chunksize=...)``, zodat aanroepers niet zelf met
    ``pandas`` hoeven te praten en een consistente ``dtype``/``na_values``-doorgave hebben.

    ``na_values`` bestaat specifiek voor de tekstsentinel ``"x"`` in ``boiler-temp.csv``
    (zie ``sentinels.BOILER_TEMP_NA_VALUES``): zonder dit leest ``pandas`` een numerieke kolom die
    ergens die tekst bevat voor het HELE chunk als tekst, wat verderop een harde ``TypeError`` geeft
    zodra die kolom met een plausibiliteitsgrens vergeleken wordt."""
    yield from pd.read_csv(stream, chunksize=chunksize, dtype=dtype, na_values=na_values, usecols=usecols)


def maak_bron(raw_pad: str | Path) -> ZipBron:
    """``raw_pad`` mag naar het zip-bestand zelf wijzen, of naar een map waarin het staat."""
    raw_pad = Path(raw_pad)
    if raw_pad.is_dir():
        kandidaten = sorted(raw_pad.glob("*.zip"))
        if len(kandidaten) == 1:
            return ZipBron(kandidaten[0])
        gerichte = [k for k in kandidaten if "resultaten" in k.name.lower()]
        if len(gerichte) == 1:
            return ZipBron(gerichte[0])
        raise BronError(f"Geen eenduidige zip gevonden in {raw_pad}; wijs er expliciet één aan")
    return ZipBron(raw_pad)
