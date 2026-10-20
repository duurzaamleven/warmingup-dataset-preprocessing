# SPDX-License-Identifier: EUPL-1.2
"""Streamend lezen van een zip-lid dat met Deflate64 gecomprimeerd is (``compress_type == 9``).

**Waarom dit bestaat.** ``thermostat-temp.csv`` staat in het archief met Deflate64, en Python's
``zipfile`` kan dat compressietype niet uitpakken (het geeft ``NotImplementedError``). De gekozen
oplossing is de afhankelijkheid `inflate64 <https://pypi.org/project/inflate64/>`_, die een
Deflate64-inflater levert maar geen zip-integratie: die moeten we zelf leggen.

**Hoe dat werkt.** ``zipfile.ZipInfo.header_offset`` wijst naar het begin van de *lokale*
bestandsheader in de zip, niet naar de gecomprimeerde data zelf; daar zit nog een header (30 bytes
vast, plus een bestandsnaam en een optioneel extra-veld met een lengte die pas uit die header zelf
blijkt) tussen. Deze module leest die lokale header, berekent zo de bytepositie waar de
gecomprimeerde data begint, en voedt vervolgens precies ``compress_size`` bytes in blokken aan
``inflate64.Inflater``. Geverifieerd tegen het echte archief (``data/raw/data-en-resultaten.zip``,
``thermostat-temp.csv``): de eerste regels decomprimeren correct en komen overeen met de koppen die
het ontwerp noemt.

**Dit is de enige plek in de repo waarna ``inflate64`` gebruikt wordt.** Voor de vijf andere leden
van het archief (gewone Deflate, ``compress_type == 8``) volstaat ``zipfile.ZipFile.open`` gewoon.
"""

from __future__ import annotations

import io
import struct
import zipfile
from pathlib import Path
from typing import Callable

try:
    import inflate64
except ImportError as exc:  # pragma: no cover - alleen relevant als de dependency ontbreekt
    raise ImportError(
        "inflate64 ontbreekt; dit is een harde afhankelijkheid voor thermostat-temp.csv "
        "(Deflate64, compress_type 9). Installeer met `pip install -e \".[dev]\"`."
    ) from exc

#: Lokale-bestandsheader van een zip-lid: 4 bytes signature, dan acht 2- of 4-byte velden, dan de
#: lengte van de bestandsnaam en van het extra-veld. Zie APPNOTE.TXT §4.3.7. We hebben alleen de
#: laatste twee lengtes nodig om de dataoffset te berekenen.
_LOKALE_HEADER_LENGTE = 30
_LOKALE_HEADER_SIGNATUUR = b"PK\x03\x04"


class Deflate64Fout(ValueError):
    """De lokale header van het zip-lid is niet wat we verwachten; geen Deflate64-data te vinden."""


def _data_offset(fh: io.BufferedReader, info: zipfile.ZipInfo) -> int:
    """De bytepositie in ``fh`` waar de gecomprimeerde data van ``info`` echt begint."""
    fh.seek(info.header_offset)
    header = fh.read(_LOKALE_HEADER_LENGTE)
    if len(header) < _LOKALE_HEADER_LENGTE or header[:4] != _LOKALE_HEADER_SIGNATUUR:
        raise Deflate64Fout(
            f"{info.filename}: geen geldige lokale zip-header op offset {info.header_offset}"
        )
    (filename_len, extra_len) = struct.unpack("<HH", header[26:30])
    return info.header_offset + _LOKALE_HEADER_LENGTE + filename_len + extra_len


class Deflate64Stream(io.RawIOBase):
    """Een leesbare, streamende ``IO[bytes]`` voor één Deflate64-lid van een zip-archief.

    Bedoeld om rechtstreeks aan ``pandas.read_csv(..., chunksize=...)`` gegeven te worden, precies
    zoals bij een gewoon (Deflate) zip-lid via ``zipfile.ZipFile.open``. Nooit uitgepakt naar
    schijf: elk blok wordt gelezen, gedecomprimeerd en meteen weer losgelaten.

    ``op_voortgang`` is een optionele callback die na elk gelezen blok wordt aangeroepen met het
    cumulatieve aantal GEDECOMPRIMEERDE bytes tot nu toe; de pijplijn gebruikt dit voor
    ``_voortgang.json`` (zie ``voortgang.py``).
    """

    def __init__(
        self,
        zip_pad: str | Path,
        info: zipfile.ZipInfo,
        leesblok: int = 1 << 20,
        op_voortgang: Callable[[int], None] | None = None,
    ):
        super().__init__()
        if info.compress_type != 9:
            raise Deflate64Fout(f"{info.filename}: compress_type is {info.compress_type}, geen Deflate64 (9)")
        self._info = info
        self._leesblok = leesblok
        self._op_voortgang = op_voortgang
        self._fh = open(zip_pad, "rb")
        self._fh.seek(_data_offset(self._fh, info))
        self._inflater = inflate64.Inflater()
        self._resterend_gecomprimeerd = info.compress_size
        self._buf = b""
        self._uitgevoerd = 0

    def readable(self) -> bool:  # pragma: no cover - triviaal
        return True

    def _vul_buffer(self) -> None:
        while not self._buf and not self._inflater.eof and self._resterend_gecomprimeerd > 0:
            te_lezen = min(self._leesblok, self._resterend_gecomprimeerd)
            blok = self._fh.read(te_lezen)
            if not blok:
                break
            self._resterend_gecomprimeerd -= len(blok)
            self._buf = self._inflater.inflate(blok)
            self._uitgevoerd += len(self._buf)
            if self._op_voortgang is not None:
                self._op_voortgang(self._uitgevoerd)

    def readinto(self, b) -> int:  # type: ignore[override]
        if not self._buf:
            self._vul_buffer()
            if not self._buf:
                return 0
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n

    def close(self) -> None:
        if not self.closed:
            self._fh.close()
        super().close()

    def __enter__(self) -> "Deflate64Stream":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_deflate64(
    zip_pad: str | Path,
    naam: str,
    leesblok: int = 1 << 20,
    op_voortgang: Callable[[int], None] | None = None,
) -> io.BufferedReader:
    """Open lid ``naam`` (Deflate64) van ``zip_pad`` als een gebufferde, leesbare bytestream.

    Gebufferd (``io.BufferedReader``) omdat ``pandas.read_csv`` daarmee efficiënter leest dan
    rechtstreeks op de RawIOBase; ``inflate64`` zelf werkt intern al bloksgewijs, maar de
    C-CSV-parser van pandas doet veel kleine ``read()``-aanroepen die zonder buffering telkens de
    hele ``readinto``-keten (inclusief de eof/resterend-checks) opnieuw doorlopen.
    """
    zip_pad = Path(zip_pad)
    with zipfile.ZipFile(zip_pad) as z:
        info = z.getinfo(naam)
    ruw = Deflate64Stream(zip_pad, info, leesblok=leesblok, op_voortgang=op_voortgang)
    return io.BufferedReader(ruw, buffer_size=leesblok)
