# SPDX-License-Identifier: EUPL-1.2
"""``data/processed/_voortgang.json``: zodat iemand van buitenaf, zonder de log te lezen, een ETA
kan uitrekenen (ontwerp-preprocessing.md §9).

**Formaat.** Eén JSON-object, bij elke update in zijn geheel overschreven (geen ``.jsonl``: er hoeft
geen geschiedenis bewaard te blijven, alleen de laatste stand). Zie ``README.md`` voor de
documentatie die een lezer van buiten dit bestand nodig heeft; deze docstring is de bron daarvan.

.. code-block:: json

    {
      "uitvoer_contract_versie": "2026-09-23-eerste-opzet",
      "fase": "boiler_temp",
      "gestart_op": "2026-09-23T10:00:00+00:00",
      "laatst_bijgewerkt_op": "2026-09-23T10:04:12+00:00",
      "bronbestanden": {
        "boiler-temp.csv": {
          "bytes_gelezen__B": 512000000,
          "bytes_totaal__B": 9841494342,
          "rijen_gelezen": 12345678,
          "voltooid": false
        }
      }
    }

``bytes_gelezen__B`` is het aantal ONTCOMPRIMEERDE bytes dat uit het bronbestand gelezen is (niet
het aantal bytes van de gecomprimeerde zip-data); ``bytes_totaal__B`` is ``file_size`` uit de
zip-index, dus de ontcomprimeerde totale omvang. ``bytes_gelezen__B / bytes_totaal__B`` is dus
rechtstreeks een voortgangsfractie voor dat bronbestand, en samen met ``laatst_bijgewerkt_op`` minus
``gestart_op`` een ETA.

**Schrijffrequentie.** :class:`VoortgangSchrijver` schrijft bij elke aanroep van :meth:`update`,
maar ``update`` zelf wordt door de pijplijn na elke gelezen CSV-chunk aangeroepen (typisch enkele
keren per seconde tot enkele keren per minuut, afhankelijk van de chunkgrootte); dit object bewaakt
zelf dat er nooit meer dan :data:`MAX_INTERVAL__s` tussen twee schrijfacties zit door bij een trage
fase een schrijfactie te FORCEREN ook zonder nieuwe voortgang, in plaats van te wachten op de
volgende chunk. Schrijven gebeurt atomisch (``.tmp`` + hernoeming), zodat een lezer nooit een half
geschreven JSON-bestand aantreft.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

#: Uiterste tijd tussen twee schrijfacties naar ``_voortgang.json`` (ontwerp-eis: "minstens elke
#: minuut bijgewerkt"). Ruim onder de minuut gekozen zodat een langzame laatste chunk de garantie
#: niet net mist.
MAX_INTERVAL__s = 45.0

VOORTGANG_BESTANDSNAAM = "_voortgang.json"


@dataclass
class BronVoortgang:
    bytes_gelezen__B: int = 0
    bytes_totaal__B: int = 0
    rijen_gelezen: int = 0
    voltooid: bool = False


class VoortgangSchrijver:
    def __init__(self, uit_dir: Path, contract_versie: str):
        self.pad = Path(uit_dir) / VOORTGANG_BESTANDSNAAM
        self._contract_versie = contract_versie
        self._gestart_op = datetime.now(timezone.utc).isoformat()
        self._fase = "start"
        self._bronnen: dict[str, BronVoortgang] = {}
        self._laatste_schrijf__monotonic = 0.0

    def zet_fase(self, fase: str, forceer: bool = True) -> None:
        self._fase = fase
        if forceer:
            self._schrijf()

    def zet_totaal(self, bronbestand: str, bytes_totaal__B: int) -> None:
        self._bronnen.setdefault(bronbestand, BronVoortgang()).bytes_totaal__B = bytes_totaal__B

    def update(
        self,
        bronbestand: str,
        bytes_gelezen__B: int | None = None,
        rijen_gelezen: int | None = None,
        forceer: bool = False,
    ) -> None:
        bron = self._bronnen.setdefault(bronbestand, BronVoortgang())
        if bytes_gelezen__B is not None:
            bron.bytes_gelezen__B = bytes_gelezen__B
        if rijen_gelezen is not None:
            bron.rijen_gelezen = rijen_gelezen
        if forceer or (time.monotonic() - self._laatste_schrijf__monotonic) >= MAX_INTERVAL__s:
            self._schrijf()

    def zet_voltooid(self, bronbestand: str) -> None:
        self._bronnen.setdefault(bronbestand, BronVoortgang()).voltooid = True
        self._schrijf()

    def klaar(self) -> None:
        self.zet_fase("klaar", forceer=True)

    def _schrijf(self) -> None:
        inhoud = {
            "uitvoer_contract_versie": self._contract_versie,
            "fase": self._fase,
            "gestart_op": self._gestart_op,
            "laatst_bijgewerkt_op": datetime.now(timezone.utc).isoformat(),
            "bronbestanden": {
                naam: {
                    "bytes_gelezen__B": b.bytes_gelezen__B,
                    "bytes_totaal__B": b.bytes_totaal__B,
                    "rijen_gelezen": b.rijen_gelezen,
                    "voltooid": b.voltooid,
                }
                for naam, b in self._bronnen.items()
            },
        }
        self.pad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pad.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(inhoud, ensure_ascii=False, indent=2), encoding="utf-8")
        # Op een netwerkschijf weigert het overschrijven soms kortstondig (WinError 5) als het vorige
        # exemplaar nog open is, bijvoorbeeld door een virusscanner; vooral bij snel opeenvolgende
        # schrijfacties, zoals de fasen van een migratie. Een paar keer opnieuw proberen volstaat.
        for poging in range(6):
            try:
                tmp.replace(self.pad)
                break
            except PermissionError:
                if poging == 5:
                    raise
                time.sleep(0.2 * 2**poging)
        self._laatste_schrijf__monotonic = time.monotonic()
