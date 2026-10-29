# SPDX-License-Identifier: EUPL-1.2
"""Hervatbaarheid: ``_manifest.jsonl``, atomisch schrijven, en de contractversie.

**Twee lagen, met opzet verschillend duurzaam** (patroon overgenomen uit een eerdere preprocessing-repo, zie
``ontwerp-preprocessing.md`` §5):

1. Elk stuk uitvoer (een per-woningbestand, een etmaaltabel, ...) wordt eerst naar ``<pad>.tmp``
   geschreven en pas na een geslaagde schrijfactie atomisch hernoemd naar zijn definitieve naam
   (:func:`schrijf_atomisch`). Een halverwege afgebroken run laat dus nooit een bestand met de
   definitieve naam achter dat toch onvolledig is.
2. Pas ná die hernoeming wordt een regel aan ``_manifest.jsonl`` toegevoegd: onderdeel, sleutel
   (bijvoorbeeld een woning-id), relatief pad, sha256, aantal rijen, tijdstip. Een hervatting leest
   dit bestand en slaat een onderdeel over zodra het manifest zegt dat het al af is EN het bestand
   op schijf werkelijk bestaat met de juiste sha256 (zie :func:`is_voltooid`); een manifestregel
   zonder een kloppend bestand wordt behandeld als "nog te doen", nooit als een fout die de hele run
   blokkeert.

``UITVOER_CONTRACT_VERSIE`` staat in het manifest opgeslagen; wijzigt de vorm of betekenis van de
uitvoer, hoog deze op. Zonder die controle zou een hervatting na een codewijziging oude en nieuwe
uitvoer door elkaar kunnen laten staan zonder foutmelding (dezelfde les als in die eerdere repo).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

#: Versie van het uitvoercontract: kolomnamen, eenheden, tijdzone, sentinelbehandeling. Hoog dit op
#: zodra de betekenis of vorm van de uitvoer verandert; zie de moduledocstring.
#:
#: "2026-09-23-tweede-opzet" t.o.v. "2026-09-23-eerste-opzet" (de versie van de eerste volledige run,
#: zie VOORTGANG.md): twee vormveranderingen van de uitvoer.
#: (1) Nieuwe kolom ``q_flag_tijdstip_dubbel__bool`` in ``boiler_temp`` en ``thermostat_temp``
#: (sentinels.flag_tijdstip_dubbel): dubbele tijdstempels worden nu per rij gevlagd, niet alleen
#: geteld in dekking.parquet. (2) een identificatiekolom in ``resultaten.parquet`` werd een string
#: in plaats van int64 (die kolom is sinds "2026-10-28-vierde-opzet" vervallen).
#:
#: "2026-09-23-derde-opzet" t.o.v. "2026-09-23-tweede-opzet": de tz-aware tijdstempels (``tijdstip``
#: in boiler_temp/thermostat_temp, ``eerste_tijdstip``/``laatste_tijdstip`` in dekking.parquet) staan
#: nu in de weergavezone Europe/Amsterdam in plaats van UTC (``tijd.TIJDZONE_WEERGAVE``,
#: ``tijd.naar_weergave_tijdzone``). Het instant verandert niet, alleen de tz-metadata; zie
#: docs/datacatalogus.md §4 voor de onderbouwing.
#:
#: "2026-10-28-vierde-opzet" t.o.v. "2026-09-23-derde-opzet": gebouwd op de versie van 27-10-2026 van
#: de bron, zonder mapping.csv en zonder logger- en serienummers. ``mapping.parquet`` vervalt, en
#: ``resultaten.parquet`` verliest ``logger_id__str`` en ``serial_no__str``. Alle andere kolommen,
#: eenheden en de tijdzone zijn ongewijzigd.
UITVOER_CONTRACT_VERSIE = "2026-10-28-vierde-opzet"

MANIFEST_BESTANDSNAAM = "_manifest.jsonl"


@dataclass
class ManifestRegel:
    onderdeel: str
    sleutel: str
    pad: str
    sha256: str
    rijen: int
    contract: str = UITVOER_CONTRACT_VERSIE
    voltooid_op: str = ""

    def __post_init__(self) -> None:
        if not self.voltooid_op:
            self.voltooid_op = datetime.now(timezone.utc).isoformat()


def sha256_van_bestand(pad: Path, leesblok: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with pad.open("rb") as f:
        while True:
            blok = f.read(leesblok)
            if not blok:
                break
            h.update(blok)
    return h.hexdigest()


def schrijf_parquet_atomisch(pad: Path, df: pd.DataFrame, compressie: str = "zstd") -> None:
    """Schrijf ``df`` naar ``pad`` via ``<pad>.tmp`` + hernoeming; zie de moduledocstring."""
    pad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pad.with_suffix(pad.suffix + ".tmp")
    df.to_parquet(tmp, index=False, compression=compressie)
    tmp.replace(pad)


class Manifest:
    """Lees- en schrijftoegang tot ``<out_dir>/_manifest.jsonl``."""

    def __init__(self, out_dir: Path):
        self.pad = Path(out_dir) / MANIFEST_BESTANDSNAAM
        self._regels: dict[tuple[str, str], ManifestRegel] = {}
        self._laad()

    def _laad(self) -> None:
        if not self.pad.is_file():
            return
        with self.pad.open(encoding="utf-8") as f:
            for regel in f:
                regel = regel.strip()
                if not regel:
                    continue
                try:
                    post = json.loads(regel)
                except json.JSONDecodeError:
                    # Een afgebroken run kan een halve laatste regel achterlaten; dat mag de rest
                    # van het manifest niet ongeldig maken (zelfde tolerantie als de
                    # extractie-zusterrepo's compacteertool).
                    log.warning("Onvolledige manifestregel overgeslagen in %s", self.pad)
                    continue
                sleutel = (post["onderdeel"], post["sleutel"])
                self._regels[sleutel] = ManifestRegel(**post)

    def is_voltooid(self, onderdeel: str, sleutel: str, uit_dir: Path) -> bool:
        """True als het manifest dit onderdeel als af beschouwt ÉN het bestand op schijf nog
        klopt: bestaat, met dezelfde contractversie. De sha256 wordt bewust NIET opnieuw berekend
        bij elke hervat-check (dat zou een volledige herlezing van elk bestand vergen, wat het hele
        doel van hervatten ondermijnt); die dient als bewijs in het manifest zelf en als
        verificatiemiddel voor een mens, niet als iets dat bij elke opstart herhaald wordt."""
        regel = self._regels.get((onderdeel, sleutel))
        if regel is None:
            return False
        if regel.contract != UITVOER_CONTRACT_VERSIE:
            return False
        return (uit_dir / regel.pad).is_file()

    def voeg_toe(self, onderdeel: str, sleutel: str, pad: Path, uit_dir: Path, rijen: int) -> None:
        relatief = str(pad.relative_to(uit_dir))
        regel = ManifestRegel(
            onderdeel=onderdeel,
            sleutel=sleutel,
            pad=relatief,
            sha256=sha256_van_bestand(pad),
            rijen=rijen,
        )
        self._regels[(onderdeel, sleutel)] = regel
        self.pad.parent.mkdir(parents=True, exist_ok=True)
        with self.pad.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(regel), ensure_ascii=False) + "\n")

    def voltooide_sleutels(self, onderdeel: str) -> set[str]:
        return {s for (o, s) in self._regels if o == onderdeel}

    def totaal_rijen(self, onderdeel: str) -> int:
        return sum(r.rijen for (o, _), r in self._regels.items() if o == onderdeel)
