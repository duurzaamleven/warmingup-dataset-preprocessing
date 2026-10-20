# SPDX-License-Identifier: EUPL-1.2
"""Tijdzones en intervalsemantiek (ontwerp-preprocessing.md §4 en §5).

**Twee tijdzones in één dataset.** ``boiler-temp.csv`` en ``thermostat-temp.csv`` dragen een
``Z``-suffix (UTC) in de ``Time``-kolom. ``boiler-24h-stats.csv`` heeft een kolom die letterlijk
``Day (Europe/Amsterdam)`` heet: een **lokale kalenderdag**, geen tijdstip. De twee mogen nooit
zonder omrekening naast elkaar gelegd worden: rond de zomertijdovergang schuift dat een uur, en op
de overgangsdagen zelf telt het etmaal 23 of 25 uur.

**Intern UTC, in de uitvoer Europe/Amsterdam.** Elke tz-aware tijdstempel wordt eerst met
``naar_utc_tijdstip`` naar UTC geparsed (dat blijft de interne rekenbasis: sentinels, dekking en de
plausibiliteitsvlaggen werken allemaal op UTC) en pas als allerlaatste stap, vlak voor het schrijven,
met ``naar_weergave_tijdzone`` omgezet naar de weergavezone ``TIJDZONE_WEERGAVE`` (Europe/Amsterdam;
zie die constante voor de onderbouwing). Dat is een zuivere weergavezone-omzetting: het instant zelf
verandert niet, alleen de tz-metadata. De etmaaltabel blijft een kalenderdag (een ``date``, geen
``timestamp``); wie hem tegen de minuutdata wil leggen, moet zelf expliciet de lokale
middernachtgrens omrekenen (met ``etmaalgrens_utc`` hieronder, dat een UTC-venster teruggeeft; een
vergelijking met een Europe/Amsterdam-tijdstempel werkt daar automatisch overheen, want
tijdzonevergelijking in pandas gaat altijd via het instant), en dat gebeurt hier bewust niet
stilzwijgend voor hem.
"""

from __future__ import annotations

from zoneinfo import ZoneInfo

import pandas as pd

TIJDZONE_ETMAAL = ZoneInfo("Europe/Amsterdam")

#: Weergavezone van de tz-aware tijdstempels in de UITVOER (``tijdstip`` in boiler_temp/
#: thermostat_temp, ``eerste_tijdstip``/``laatste_tijdstip`` in dekking.parquet). Aanvullende eis
#: van de opdrachtgever (23-09-2026), analoog aan de Installatiemonitor-preprocessing
#: (``datetime64[ns, Europe/Amsterdam]``). Onderbouwing: de bron labelt de etmaaltabel zelf als
#: ``Day (Europe/Amsterdam)``; de steekproef is gericht op de Nederlandse woningvoorraad
#: (Deltares-eindrapport 2022, p. 7-8); KNMI-station Deelen ligt "geographically closest to most
#: studied buildings" (idem, p. 11); de vijf warmtebedrijven leveren in Europees Nederland (idem,
#: p. 2). **Het instant zelf verandert niet**: dit is een weergavezone-omzetting op een kolom die al
#: correct als UTC is geparsed (``naar_utc_tijdstip`` hieronder blijft de eerste, interne stap), geen
#: herinterpretatie van een naïeve tijdstempel. Zie ``naar_weergave_tijdzone``.
TIJDZONE_WEERGAVE = "Europe/Amsterdam"

#: **Expliciete aanname, geen vaststaand feit** (ontwerp-preprocessing.md §6). Of het debiet in `boiler-temp.csv` begin- of eindgelabeld is, is niet
#: gedocumenteerd door Deltares en niet uit de metadata af te leiden; het is alleen uit de data zelf
#: te toetsen (zie ``intervalsemantiek.py``). Deze pijplijn doet zelf GEEN resampling en GEEN
#: interval-integratie (ze slaat de ruwe momentane/pulswaarden op zoals ze binnenkomen), dus de
#: aanname raakt hier geen berekening. Ze staat hier toch vast, met naam, zodat een latere gebruiker
#: die wél gaat resamplen of integreren een expliciete keuze overneemt in plaats van er zelf
#: stilzwijgend een te verzinnen -- en zodat het één plek is om te wijzigen zodra de toets in
#: ``intervalsemantiek.py`` een uitkomst heeft.
AANNAME_DEBIET_INTERVAL_LABEL = "onbekend"

#: De twee mogelijke waarden die ``AANNAME_DEBIET_INTERVAL_LABEL`` ooit kan aannemen zodra de toets
#: een uitkomst heeft: een minuutwaarde op tijdstip t dekt het interval
#: [t-1min, t] ("eindgelabeld") of [t, t+1min] ("begingelabeld").
INTERVAL_LABEL_EIND = "eindgelabeld"
INTERVAL_LABEL_BEGIN = "begingelabeld"


def naar_utc_tijdstip(kolom: pd.Series) -> pd.Series:
    """Parseer een ISO-8601-kolom met ``Z``-suffix (``boiler-temp.csv``/``thermostat-temp.csv``)
    naar tz-aware ``datetime64[ns, UTC]``. Faalt hard op een niet-parseerbare waarde: een stille
    ``NaT`` zou een gat in de dekking maskeren als een echte meting."""
    resultaat = pd.to_datetime(kolom, format="%Y-%m-%dT%H:%M:%SZ", utc=True, errors="raise")
    return resultaat


def naar_weergave_tijdzone(kolom: pd.Series) -> pd.Series:
    """Zet een tz-aware kolom (intern al correct als UTC geparsed, zie ``naar_utc_tijdstip``) om
    naar de weergavezone ``TIJDZONE_WEERGAVE`` (Europe/Amsterdam). ``Series.dt.tz_convert`` verandert
    het instant NIET, alleen de tz-metadata waarmee het getoond wordt; het onderliggende
    UTC-nanoseconden-getal (en dus de Parquet-bytes op fysiek niveau) blijft identiek. Toegepast als
    allerlaatste stap vóór het casten naar het Parquet-schema (``schrijvers.py``), zodat alle
    tussenliggende logica (sentinels.flag_tijdstip_dubbel, plausibiliteitsvlaggen) op UTC blijft
    werken zoals altijd."""
    return kolom.dt.tz_convert(TIJDZONE_WEERGAVE)


def naar_lokale_datum(kolom: pd.Series) -> pd.Series:
    """``Day (Europe/Amsterdam)`` blijft een kalenderdag: gevalideerd als datum (faalt hard op een
    onparseerbare waarde) maar opgeslagen als ISO-8601-tekst (``datum__str``, conform de
    kolomvertaling), NIET als tijdstip en NIET naar UTC omgerekend. Dat laatste zou de dag zelf
    laten verschuiven, wat een kalenderdag nooit mag; de ``__str``-naam markeert bewust dat dit geen
    ``timestamp`` is."""
    gevalideerd = pd.to_datetime(kolom, format="%Y-%m-%d", errors="raise")
    return gevalideerd.dt.strftime("%Y-%m-%d")


def etmaalgrens_utc(lokale_dag) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Het UTC-tijdvenster ``[begin, eind)`` van de lokale kalenderdag ``lokale_dag``
    (``datetime.date`` of iets dat ``pandas.Timestamp`` kan parsen).

    Gebruikt om een etmaalwaarde te vergelijken met UTC-minuutdata; zie de moduledocstring. Rond de
    zomertijdovergang is de lengte van dit venster 23 of 25 uur, precies zoals het ontwerp
    voorschrijft (geen aanname van 24 uur).
    """
    # Let op: de volgende kalenderdag EERST bepalen op de naïeve (tz-loze) datum, en PAS DAARNA de
    # tijdzone aanzetten. ``begin_lokaal + pd.Timedelta(days=1)`` zou hier een bug zijn: dat is een
    # vaste 24-uursverschuiving in absolute tijd, en geeft op een DST-dag dus niet de lokale
    # middernacht van de volgende dag maar 23:00 of 01:00 lokale tijd.
    dag = pd.Timestamp(lokale_dag)
    volgende_dag = dag + pd.Timedelta(days=1)
    begin_lokaal = pd.Timestamp(dag.year, dag.month, dag.day, tzinfo=TIJDZONE_ETMAAL)
    eind_lokaal = pd.Timestamp(volgende_dag.year, volgende_dag.month, volgende_dag.day, tzinfo=TIJDZONE_ETMAAL)
    return begin_lokaal.tz_convert("UTC"), eind_lokaal.tz_convert("UTC")
