# SPDX-License-Identifier: EUPL-1.2
"""Volledige scan van de ruwe bronbestanden op tekstwaarden en andere onbekende sentinels.

**Waarom.** De eerste bouwsessie vond de tekst ``x`` in de aanvoertemperatuur, maar alleen over de
eerste 40 miljoen rijen van ``boiler-temp.csv`` (ontwerp-preprocessing.md §6). Deze module leest
ELKE rij van ELKE kolom van de vier CSV-bestanden in het archief (en de kolommen van de
resultatentabel) en telt wat geen getal is, zodat "alleen in deze kolom" een telling is en geen
steekproefindruk.

**Wat er geteld wordt**, per bestand en kolom:

* ``leeg``: het veld is een lege tekst;
* ``niet_numeriek``: het veld is niet leeg en past niet bij de verwachte vorm van de kolom (een getal,
  een ISO-tijdstempel met ``Z``, een kalenderdag, een woningcode ``WU<n>``), met de meest voorkomende
  waarden en de meest voorkomende VORMEN (cijfers vervangen door ``9``);
* voor getalkolommen ook het minimum, het maximum en hoe vaak een lijst bekende of denkbare
  sentinelwaarden (``-1``, ``-40``, ``9999``, ``2**32-1``, ...) als getal voorkomt;
* per woning hoeveel rijen en hoeveel niet-numerieke velden (en hoeveel de tekst ``x``) er zijn;
* het aantal rijen met een afwijkend aantal velden (die slaat de lezer over en telt hij hier).

**Streamend en zuinig.** Dezelfde lezers als de pijplijn (``ZipBron.open_bron``, dus ook de
Deflate64-route, plus ``pyarrow.csv.open_csv``), alles als tekst ingelezen, blokken van 16 MB; er
staat nooit meer dan een blok in het geheugen. Het is een toets, geen onderdeel van de pijplijn: er
komt niets in de uitvoer van de pijplijn terecht.

Gebruik::

    python -m warmingup_preprocessing.bronscan --raw-dir data/raw --bestand boiler-temp.csv --uit data/scan
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
from collections import Counter
from pathlib import Path
from typing import IO, Callable, Iterable

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv

from . import zipbron
from .snelle_lezer import BLOCK_SIZE_STANDAARD

log = logging.getLogger(__name__)

#: Een getal zoals de bron het schrijft: optioneel teken, cijfers met optioneel een decimaaldeel,
#: optioneel een exponent. Alles anders (``x``, ``NaN``, ``inf``, een spatie ervoor) is "niet numeriek".
RE_GETAL = r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$"
RE_TIJD = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
RE_DAG = r"^\d{4}-\d{2}-\d{2}$"
RE_WONING = r"^WU\d+$"

#: Verwachte vorm per soort kolom. ``vrij``: geen verwachte vorm, alleen lege velden tellen.
PATRONEN = {"getal": RE_GETAL, "tijd": RE_TIJD, "dag": RE_DAG, "woning": RE_WONING}

#: Bekende en denkbare sentinelwaarden voor getalkolommen. ``-1`` (waterdruk), ``-40`` (kortgesloten
#: sensor) en ``2**32-1`` (debiet) zijn al bekend (sentinels.py); de rest zijn gangbare
#: "geen waarde"-codes die we juist willen uitsluiten of vinden.
KANDIDAAT_SENTINELS = (
    -1.0, -40.0, -99.0, -999.0, -9999.0, -32768.0, 99.0, 999.0, 9999.0, 99999.0,
    255.0, 65535.0, 32767.0, float(2**31 - 1), float(2**32 - 1), float(2**32), 1e9, 1e10,
)

#: Hoeveel verschillende niet-numerieke waarden per kolom we bijhouden (daarboven telt alleen de vorm).
MAX_UNIEKE_WAARDEN = 500

#: Soort per kolom, op POSITIE (de ruwe kolomnamen bevatten tekens die per codering verschillen).
KOLOMSOORTEN: dict[str, tuple[str, ...]] = {
    zipbron.BOILER_TEMP: ("woning", "tijd", "getal", "getal", "getal"),
    zipbron.THERMOSTAT_TEMP: ("woning", "tijd", "getal", "getal"),
    zipbron.BOILER_24H_STATS: ("woning", "dag") + ("getal",) * 7,
}


def vorm_van(waarde: str) -> str:
    """De 'vorm' van een tekstwaarde: elk cijfer wordt ``9``. ``12.5x`` en ``30.1x`` zijn dan gelijk."""
    return re.sub(r"\d", "9", waarde)


class KolomTelling:
    """Optelsom voor één kolom van één bestand."""

    def __init__(self, naam: str, soort: str):
        self.naam = naam
        self.soort = soort
        self.rijen = 0
        self.leeg = 0
        self.niet_numeriek = 0
        self.waarden: Counter[str] = Counter()
        self.waarden_overig = 0  # niet-numerieke velden met een waarde die buiten de top viel
        self.vormen: Counter[str] = Counter()
        self.minimum: float | None = None
        self.maximum: float | None = None
        self.min_tekst: str | None = None
        self.max_tekst: str | None = None
        self.sentinels: Counter[float] = Counter()

    def tel_batch(self, kolom: pa.ChunkedArray | pa.Array) -> pa.Array:
        """Verwerk één kolom van één batch en geef het masker 'niet leeg en niet passend' terug."""
        n = len(kolom)
        self.rijen += n
        leeg = pc.equal(kolom, "")
        self.leeg += pc.sum(leeg).as_py() or 0
        if self.soort == "vrij":
            return pa.array([False] * n)
        past = pc.match_substring_regex(kolom, PATRONEN[self.soort])
        niet_numeriek = pc.and_(pc.invert(past), pc.invert(leeg))
        k = pc.sum(niet_numeriek).as_py() or 0
        self.niet_numeriek += k
        if k:
            vreemd = pc.filter(kolom, niet_numeriek)
            for r in pc.value_counts(vreemd).to_pylist():
                waarde, aantal = r["values"], r["counts"]
                if waarde in self.waarden or len(self.waarden) < MAX_UNIEKE_WAARDEN:
                    self.waarden[waarde] += aantal
                else:
                    self.waarden_overig += aantal
                self.vormen[vorm_van(waarde)] += aantal
        passend = pc.filter(kolom, past)
        if len(passend) == 0:
            return niet_numeriek
        if self.soort == "getal":
            getallen = pc.cast(passend, pa.float64())
            mm = pc.min_max(getallen).as_py()
            self.minimum = mm["min"] if self.minimum is None else min(self.minimum, mm["min"])
            self.maximum = mm["max"] if self.maximum is None else max(self.maximum, mm["max"])
            treffers = pc.filter(getallen, pc.is_in(getallen, value_set=pa.array(KANDIDAAT_SENTINELS)))
            if len(treffers):
                for r in pc.value_counts(treffers).to_pylist():
                    self.sentinels[r["values"]] += r["counts"]
        else:  # tijd, dag, woning: alleen de uiterste waarden (tekstvolgorde = tijdvolgorde bij ISO)
            if self.soort in ("tijd", "dag"):
                mm = pc.min_max(passend).as_py()
                self.min_tekst = mm["min"] if self.min_tekst is None else min(self.min_tekst, mm["min"])
                self.max_tekst = mm["max"] if self.max_tekst is None else max(self.max_tekst, mm["max"])
        return niet_numeriek

    def als_dict(self) -> dict:
        return {
            "kolom": self.naam,
            "soort": self.soort,
            "rijen": self.rijen,
            "leeg": self.leeg,
            "niet_numeriek": self.niet_numeriek,
            "niet_numeriek_waarden": dict(self.waarden.most_common()),
            "niet_numeriek_waarden_overig": self.waarden_overig,
            "niet_numeriek_vormen": dict(self.vormen.most_common(25)),
            "minimum": self.minimum,
            "maximum": self.maximum,
            "minimum_tekst": self.min_tekst,
            "maximum_tekst": self.max_tekst,
            "sentinelwaarden": {repr(k): v for k, v in sorted(self.sentinels.items())},
        }


def _piekgeheugen__MB() -> float | None:
    try:
        import psutil

        info = psutil.Process().memory_info()
        return round(getattr(info, "peak_wset", info.rss) / 1e6, 1)
    except Exception:  # psutil ontbreekt of het platform kent peak_wset niet: dan niets rapporteren
        return None


def _open_als_tekst(stream, namen: list[str], block_size: int, ongeldig: dict) -> pacsv.CSVStreamingReader:
    def _ongeldige_rij(rij) -> str:
        ongeldig["aantal"] += 1
        if len(ongeldig["voorbeelden"]) < 5:
            ongeldig["voorbeelden"].append(
                {"verwacht": rij.expected_columns, "gevonden": rij.actual_columns, "tekst": rij.text[:200]}
            )
        return "skip"

    return pacsv.open_csv(
        stream,
        read_options=pacsv.ReadOptions(block_size=block_size),
        parse_options=pacsv.ParseOptions(invalid_row_handler=_ongeldige_rij),
        convert_options=pacsv.ConvertOptions(
            column_types={n: pa.string() for n in namen},
            strings_can_be_null=False,
            null_values=[],
        ),
    )


def kolomnamen_uit_kop(open_bron_fn) -> list[str]:
    """De kolomnamen uit de kopregel (eerste regel van de stroom), als tekst."""
    stream = open_bron_fn()
    try:
        kop = stream.readline()
    finally:
        stream.close()
    return next(iter(_csv_regel(kop.decode("utf-8", errors="replace"))))


def _csv_regel(tekst: str) -> Iterable[list[str]]:
    import csv

    yield from csv.reader([tekst.rstrip("\r\n")])


def scan_bestand(
    bron: zipbron.ZipBron,
    bestandsnaam: str,
    block_size: int = BLOCK_SIZE_STANDAARD,
    max_bytes: int | None = None,
    voortgang_elke_rijen: int = 20_000_000,
) -> dict:
    """Scan één CSV-lid van het archief. ``max_bytes`` alleen voor tests en proefdraaien."""
    return scan_stroom(
        lambda: bron.open_bron(bestandsnaam, max_bytes=max_bytes),
        KOLOMSOORTEN[bestandsnaam],
        bestandsnaam,
        block_size=block_size,
        voortgang_elke_rijen=voortgang_elke_rijen,
    )


def scan_stroom(
    open_stroom: Callable[[], IO[bytes]],
    soorten: tuple[str, ...],
    bestandsnaam: str,
    block_size: int = BLOCK_SIZE_STANDAARD,
    voortgang_elke_rijen: int = 20_000_000,
) -> dict:
    """Scan een CSV (kop op de eerste regel). ``open_stroom`` geeft bij elke aanroep een verse stroom:
    één voor de kop en één voor de rijen, want een stroom kan niet terug."""
    namen = kolomnamen_uit_kop(open_stroom)
    if len(namen) != len(soorten):
        raise ValueError(f"{bestandsnaam}: {len(namen)} kolommen in de kop, {len(soorten)} verwacht: {namen}")
    ongeldig: dict = {"aantal": 0, "voorbeelden": []}
    kolommen = [KolomTelling(naam, soort) for naam, soort in zip(namen, soorten)]
    per_woning: dict[str, dict[str, int]] = {}
    start = time.monotonic()
    rijen_totaal = 0
    volgende_melding = voortgang_elke_rijen

    stream = open_stroom()
    try:
        reader = _open_als_tekst(stream, namen, block_size, ongeldig)
        for batch in reader:
            tabel = pa.Table.from_batches([batch])
            woning = tabel.column(0)
            velden: dict[str, pa.Array] = {"woning": woning}
            numeriek = [i for i, s in enumerate(soorten) if s == "getal"]
            for i, kolom in enumerate(kolommen):
                masker = kolom.tel_batch(tabel.column(i))
                if i in numeriek:
                    velden[f"nn{i}"] = pc.cast(masker, pa.int64())
                    velden[f"x{i}"] = pc.cast(pc.equal(tabel.column(i), "x"), pa.int64())
            velden["rijen"] = pa.array([1] * len(tabel), type=pa.int64())
            agg = pa.table(velden).group_by("woning").aggregate(
                [(k, "sum") for k in velden if k != "woning"]
            )
            for rij in agg.to_pylist():
                d = per_woning.setdefault(rij["woning"], {})
                for k, v in rij.items():
                    if k != "woning":
                        sleutel = k.removesuffix("_sum")
                        d[sleutel] = d.get(sleutel, 0) + (v or 0)
            rijen_totaal += len(tabel)
            if rijen_totaal >= volgende_melding:
                volgende_melding += voortgang_elke_rijen
                log.info(
                    "%s: %s rijen na %.0f s, piekgeheugen %s MB",
                    bestandsnaam, f"{rijen_totaal:,}", time.monotonic() - start, _piekgeheugen__MB(),
                )
    finally:
        stream.close()

    return {
        "bestand": bestandsnaam,
        "rijen": rijen_totaal,
        "rijen_met_afwijkend_aantal_velden": ongeldig["aantal"],
        "afwijkende_rijen_voorbeelden": ongeldig["voorbeelden"],
        "woningen": len(per_woning),
        "duur__s": round(time.monotonic() - start, 1),
        "piekgeheugen__MB": _piekgeheugen__MB(),
        "kolommen": [k.als_dict() for k in kolommen],
        "per_woning": per_woning,
    }


def scan_resultaten(bron: zipbron.ZipBron) -> dict:
    """De resultatentabel (xlsx, 212 rijen): per kolom het type, de lege cellen en, bij een grotendeels
    numerieke kolom, de cellen die toch tekst zijn."""
    df = bron.lees_resultaten_ruw()
    kolommen = []
    for naam in df.columns:
        serie = df[naam]
        niet_leeg = serie.dropna()
        waarden = [w for w in niet_leeg.tolist()]
        is_getal = [isinstance(w, (int, float)) and not isinstance(w, bool) for w in waarden]
        grotendeels_getal = bool(waarden) and sum(is_getal) / len(waarden) >= 0.5
        vreemd = Counter(str(w) for w, g in zip(waarden, is_getal) if grotendeels_getal and not g)
        kolommen.append(
            {
                "kolom": str(naam),
                "rijen": len(serie),
                "leeg": int(serie.isna().sum()),
                "grotendeels_numeriek": grotendeels_getal,
                "niet_numeriek": sum(vreemd.values()),
                "niet_numeriek_waarden": dict(vreemd.most_common(20)),
                "minimum": float(niet_leeg[is_getal].min()) if grotendeels_getal and any(is_getal) else None,
                "maximum": float(niet_leeg[is_getal].max()) if grotendeels_getal and any(is_getal) else None,
            }
        )
    return {"bestand": zipbron.RESULTATEN_XLSX, "rijen": len(df), "kolommen": kolommen}


def schrijf_resultaat(resultaat: dict, uit_dir: Path, naam: str) -> Path:
    """Schrijf het resultaat als JSON naar ``uit_dir`` (atomisch via een tijdelijk bestand)."""
    uit_dir.mkdir(parents=True, exist_ok=True)
    pad = uit_dir / f"bronscan-{naam}.json"
    tmp = pad.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(resultaat, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(pad)
    return pad


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    p.add_argument(
        "--bestand",
        choices=[*KOLOMSOORTEN, zipbron.RESULTATEN_XLSX],
        required=True,
        help="Welk lid van het archief gescand wordt",
    )
    p.add_argument("--uit", type=Path, default=Path("data/scan"))
    p.add_argument("--max-mb", type=int, default=None, help="Alleen de eerste N MB (proefdraaien)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(message)s")
    with zipbron.ZipBron(args.raw_dir / "data-en-resultaten.zip") as bron:
        if args.bestand == zipbron.RESULTATEN_XLSX:
            resultaat = scan_resultaten(bron)
            naam = "resultaten"
        else:
            max_bytes = args.max_mb * 1_000_000 if args.max_mb else None
            resultaat = scan_bestand(bron, args.bestand, max_bytes=max_bytes)
            naam = args.bestand.removesuffix(".csv")
    pad = schrijf_resultaat(resultaat, args.uit, naam)
    log.warning("Scan klaar: %s", pad)


if __name__ == "__main__":
    main()
