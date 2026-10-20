# SPDX-License-Identifier: EUPL-1.2
"""Sentinels en plausibiliteitsgrenzen (ontwerp-preprocessing.md §6).

**Kernregel: vlaggen, niet verwijderen.** Elke controle hier levert een boolean kwaliteitskolom op
(``q_...__bool``); er wordt nooit een rij weggegooid. Een afgeleide grootheid die op een gevlagde
invoerwaarde steunt (hier alleen ``q_afgifte__W``, dat debiet en beide temperaturen combineert) wordt
wél op ``NaN`` gezet zodra een van zijn invoerwaarden gevlagd is -- want een vermogen berekend uit
een sentinel of een kortgesloten sensor is niet "een extreme meting", het is rekenkundig onzin. De
ruwe brongrootheden zelf (``debiet_ruw__l_h``, ``temp_aanvoer__degC``, ...) blijven **ongewijzigd**
staan, sentinel inbegrepen: wie zelf met de ruwe data wil rekenen, mag dat, met de vlag ernaast.

Twee uitzonderingen waarbij een sentinel wél naar ``NaN`` gaat in de gewone kolom (niet alleen
gevlagd): de druksentinel ``-1`` bar (§6.4: "-1 → ontbrekend", de kolomnaam documenteert dit zelf
als "onbekend", geen meting) en de debiet-sentinel `2**32 - 1` in ``debiet__dm3_s_1`` (de
omgerekende kolom; ``debiet_ruw__l_h`` zelf blijft de rauwe waarde tonen). Zonder die twee zou een
argeloze `.mean()` op de "normale" kolom alsnog een torenhoog artefact meenemen.

**Vierde sentinel, gevonden tijdens het bouwen, niet in het ontwerp gedocumenteerd.** De letterlijke
tekst ``"x"`` komt voor in de kolom ``Boiler Water Supply Temperature (°C)`` van
``boiler-temp.csv`` in plaats van een getal: geverifieerd over de eerste 40.000.000 rijen (23-09-2026)
komt dit 999.002 keer voor (circa 2,5% van die steekproef), uitsluitend in deze ene kolom (niet in de
retourtemperatuur, niet in het debiet, niet in ``thermostat-temp.csv`` of ``boiler-24h-stats.csv``
binnen de gecontroleerde steekproef). Zonder maatregel laat dit ``pandas.read_csv`` de kolom voor een
heel chunk als tekst inlezen in plaats van als getal, wat verderop een harde ``TypeError`` geeft
zodra die kolom met een grens vergeleken wordt. ``ZipBron.open_bron``/de lees-aanroepen geven daarom
``na_values=[TEMP_AANVOER_TEKST_SENTINEL]`` mee aan ``pandas.read_csv``, zodat de kolom altijd
numeriek blijft; ``q_flag_temp_aanvoer_ontbrekend__bool`` hieronder maakt dit gemiste-meting-geval
zichtbaar, apart van "buiten het plausibele bereik".
"""

from __future__ import annotations

import numpy as np
import pandas as pd

#: Het uint32-maximum: de expliciete sentinel voor "debiet onbekend" (ontwerp-preprocessing.md §6).
#: Dit is GEEN nul en mag nooit als nul gelezen worden.
FLOW_SENTINEL__l_h = 2**32 - 1

#: Bovengrens van orde 5.000 l/h (ontwerp-preprocessing.md §10.1): de expliciete sentinel alleen is niet
#: genoeg, de echte vervuiling zit in de bovenstaart eronder (gemeten gemiddelde 13.442 l/h over
#: alle draaiminuten, fysisch onmogelijk voor een woninginstallatie). Waar de grens PRECIES hoort is
#: niet vastgesteld; deze waarde is een keuze, geen meting, en staat
#: daarom hier als aparte, genoemde constante in plaats van verstopt in een expressie.
FLOW_BOVENGRENS__l_h = 5_000.0

TEMP_AANVOER_BEREIK__degC = (0.0, 100.0)
TEMP_RETOUR_BEREIK__degC = (0.0, 100.0)
TEMP_BINNEN_BEREIK__degC = (0.0, 40.0)
TEMP_SETPOINT_BEREIK__degC = (5.0, 35.0)

GAS_RUIMTEVERWARMING_BEREIK__m3 = (0.0, 50.0)
GAS_TAPWATER_BEREIK__m3 = (0.0, 10.0)
BRANDERUREN_BEREIK__h = (0.0, 24.0)

#: De kolomnaam documenteert dit zelf: "Bar -1=unknown".
WATERDRUK_SENTINEL__bar = -1.0

#: Zie de moduledocstring: letterlijke tekst "x" i.p.v. een getal, alleen aangetroffen in de
#: aanvoertemperatuur van ``boiler-temp.csv``. Als ``na_values`` aan ``pandas.read_csv`` meegegeven
#: (zie ``zipbron.py``), zodat de kolom numeriek blijft.
TEMP_AANVOER_TEKST_SENTINEL = "x"

#: Kolommen waarin de tekstsentinel hierboven kan voorkomen; gebruikt door de lees-aanroepen om
#: ``na_values`` toe te passen. Vooralsnog alleen bevestigd voor de aanvoertemperatuur, maar
#: preventief ook voor de andere twee kolommen van ``boiler-temp.csv`` meegegeven: mocht "x" daar
#: ooit ook voorkomen, dan crasht de pijplijn niet stil op een dtype-fout maar geeft hij gewoon een
#: ontbrekende meting.
BOILER_TEMP_NA_VALUES = [TEMP_AANVOER_TEKST_SENTINEL]


def _buiten_bereik_numeriek(kolom: pd.Series, bereik: tuple[float, float]) -> pd.Series:
    """True waar de waarde een GETAL is dat buiten ``bereik`` valt. ``NaN`` (ontbrekend, sentinel of
    onparseerbare tekst) telt hier NIET mee -- dat is een apart, eigen "ontbrekend"-geval, zie de
    aanroepers. Zonder dit onderscheid zou "ontbrekend" en "gemeten maar implausibel" onder dezelfde
    vlag vallen, en dat zijn twee verschillende dingen om aan een gebruiker te melden."""
    laag, hoog = bereik
    return kolom.notna() & ~kolom.between(laag, hoog)


def flag_boiler_temp(df: pd.DataFrame) -> pd.DataFrame:
    """Vlag ``boiler-temp.csv``-rijen (kolomnamen al vertaald, zie ``kolommen.py``) en voeg
    ``debiet__dm3_s_1`` en ``q_afgifte__W`` toe.

    Verwacht kolommen ``home_id__str, tijdstip, temp_aanvoer__degC, temp_retour__degC,
    debiet_ruw__l_h``. ``q_afgifte__W = debiet * rho * c_p * (T_aanvoer - T_retour)``
    (ontwerp-preprocessing.md §10.7), met water bij standaardwaarden.
    """
    df = df.copy()

    debiet_is_sentinel = df["debiet_ruw__l_h"] == FLOW_SENTINEL__l_h
    debiet_boven_bovengrens = (df["debiet_ruw__l_h"] > FLOW_BOVENGRENS__l_h) & ~debiet_is_sentinel
    df["q_flag_debiet_sentinel__bool"] = debiet_is_sentinel
    df["q_flag_debiet_bovengrens__bool"] = debiet_boven_bovengrens

    debiet__dm3_s_1 = df["debiet_ruw__l_h"].astype("float64") / 3600.0
    debiet__dm3_s_1 = debiet__dm3_s_1.mask(debiet_is_sentinel, np.nan)
    df["debiet__dm3_s_1"] = debiet__dm3_s_1.astype("float32")

    df["q_flag_temp_aanvoer_ontbrekend__bool"] = df["temp_aanvoer__degC"].isna()
    df["q_flag_temp_retour_ontbrekend__bool"] = df["temp_retour__degC"].isna()
    df["q_flag_temp_aanvoer_bereik__bool"] = _buiten_bereik_numeriek(df["temp_aanvoer__degC"], TEMP_AANVOER_BEREIK__degC)
    df["q_flag_temp_retour_bereik__bool"] = _buiten_bereik_numeriek(df["temp_retour__degC"], TEMP_RETOUR_BEREIK__degC)

    # q_afgifte__W: alleen betrouwbaar waar geen van de invoerwaarden gevlagd of ontbrekend is.
    # T_retour > T_aanvoer is HIER GEEN FOUT (ontwerp-preprocessing.md §6): bij een
    # stilstaande pomp en een afkoelende ketel kan de retour tijdelijk boven de aanvoer liggen, en
    # dat levert dan gewoon een negatief q_afgifte__W op, wat correct is en niet gevlagd hoort te
    # worden.
    onbetrouwbaar = (
        df["q_flag_debiet_sentinel__bool"]
        | df["q_flag_debiet_bovengrens__bool"]
        | df["q_flag_temp_aanvoer_ontbrekend__bool"]
        | df["q_flag_temp_retour_ontbrekend__bool"]
        | df["q_flag_temp_aanvoer_bereik__bool"]
        | df["q_flag_temp_retour_bereik__bool"]
    )
    RHO_WATER__KG_M3 = 998.2
    CP_WATER__J_KG_K = 4186.0
    delta_t = df["temp_aanvoer__degC"] - df["temp_retour__degC"]
    q_afgifte = (debiet__dm3_s_1 / 1000.0) * RHO_WATER__KG_M3 * CP_WATER__J_KG_K * delta_t
    df["q_afgifte__W"] = q_afgifte.mask(onbetrouwbaar, np.nan).astype("float32")

    return df


def flag_thermostat_temp(df: pd.DataFrame) -> pd.DataFrame:
    """Vlag ``thermostat-temp.csv``-rijen. Verwacht ``home_id__str, tijdstip, temp_setpoint__degC,
    temp_binnen__degC``."""
    df = df.copy()
    df["q_flag_temp_setpoint_bereik__bool"] = _buiten_bereik_numeriek(df["temp_setpoint__degC"], TEMP_SETPOINT_BEREIK__degC)
    df["q_flag_temp_binnen_bereik__bool"] = _buiten_bereik_numeriek(df["temp_binnen__degC"], TEMP_BINNEN_BEREIK__degC)
    return df


def flag_tijdstip_dubbel(tijdstip__ns: pd.Series, gezien_tijdstippen: set[int]) -> pd.Series:
    """``q_flag_tijdstip_dubbel__bool``: True voor elke rij waarvan dit tijdstip (voor deze woning)
    al eerder is gezien; de EERSTE keer dat een tijdstip voorkomt blijft False. Bij drie identieke
    tijdstempels zijn dus rij 2 en 3 beide True, rij 1 niet. Dubbele tijdstempels worden hier
    uitsluitend GEVLAGD, niet verwijderd (CLAUDE.md-regel 5 / de moduledocstring hierboven).

    **Stateful, anders dan de overige ``flag_*``-functies in dit bestand.** De aanroeper geeft een
    MUTABLE ``set`` mee met alle tijdstippen (int64-nanoseconden sinds epoch) die voor deze woning al
    eerder zijn aangeboden, over willekeurig veel eerdere aanroepen (chunks of Arrow-batches) heen;
    deze functie werkt die set bij. Dat is nodig omdat gecontroleerd is dat de bron NIET op tijd
    gesorteerd is binnen een woning: een steekproef van 6 woningen uit de eerste volledige run
    (``data/processed-test300``, 23-09-2026) laat per woning tot enkele duizenden minuten
    "terugspringende" tijdstempels zien (bijvoorbeeld WU1: 10 sprongen terug van 121 tot 2.639
    minuten, over 1.272.082 rijen). Alleen de vorige rij vergelijken (zoals de aaneengesloten-
    controle voor woningen zelf doet) zou dubbelingen missen die verder terug in het bestand liggen;
    een ``set`` met ALLE eerder geziene tijdstippen van deze woning mist er geen enkele, ongeacht de
    volgorde. De enige eis aan de aanroeper: de rijen van één woning in hun oorspronkelijke
    bronvolgorde aanbieden (over chunkgrenzen heen), niet dat die volgorde op tijd gesorteerd is.

    Geverifieerd tegen de bestaande ``dekking.parquet`` van de eerste volledige run (23-09-2026): op
    een steekproef van 6 woningen gaf deze aanpak exact hetzelfde aantal dubbele tijdstempels als
    ``dekking.py`` altijd al berekende (``tijdstip.sort_values().duplicated().sum()``), zie
    VOORTGANG.md. De twee tellingen zijn wiskundig gelijk (allebei "aantal rijen met een waarde die
    ook al ergens anders in dezelfde woning voorkomt"); dit is dus geen nieuwe telling maar dezelfde
    telling, nu WEL zichtbaar op rijniveau.

    ``tijdstip__ns`` moet al een int64-kolom zijn (de aanroeper zet dat om met ``.astype("int64")``
    op de tz-aware ``tijdstip``-kolom; dat werkt, want intern is dat toch al UTC-nanoseconden).
    """
    al_eerder_gezien = tijdstip__ns.isin(gezien_tijdstippen)
    dubbel_binnen_dit_stuk = tijdstip__ns.duplicated(keep="first")
    gezien_tijdstippen.update(tijdstip__ns.tolist())
    return (al_eerder_gezien | dubbel_binnen_dit_stuk).astype(bool)


def flag_boiler_24h_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Vlag ``boiler-24h-stats.csv``-rijen. Verwacht de acht grootheden na kolomvertaling plus
    ``home_id__str, datum__str``.

    De drukkolommen krijgen de sentinel `-1` bar vervangen door ``NaN`` (zie moduledocstring); de
    gas- en branderuurkolommen behouden hun rauwe (mogelijk negatieve of absurd hoge) waarde, alleen
    gevlagd -- want anders dan bij druk is hier geen letterlijke "onbekend"-sentinel gedocumenteerd,
    alleen een plausibiliteitsgrens (tellerbreuken, geen sentinel).
    """
    df = df.copy()

    df["q_flag_gas_ruimteverwarming_bereik__bool"] = _buiten_bereik_numeriek(
        df["g_ruimteverwarming__m3"], GAS_RUIMTEVERWARMING_BEREIK__m3
    )
    df["q_flag_gas_tapwater_bereik__bool"] = _buiten_bereik_numeriek(df["g_tapwater__m3"], GAS_TAPWATER_BEREIK__m3)
    df["q_flag_brander_verwarming_bereik__bool"] = _buiten_bereik_numeriek(
        df["t_brander_verwarming__h"], BRANDERUREN_BEREIK__h
    )
    df["q_flag_brander_tapwater_bereik__bool"] = _buiten_bereik_numeriek(df["t_brander_tapwater__h"], BRANDERUREN_BEREIK__h)

    for kolom, vlagnaam in (
        ("p_cv_min__bar", "q_flag_druk_min_onbekend__bool"),
        ("p_cv_gem__bar", "q_flag_druk_gem_onbekend__bool"),
        ("p_cv_max__bar", "q_flag_druk_max_onbekend__bool"),
    ):
        # De kolom staat op dit punt nog in bar; tabellen.build_etmaal rekent pas ná deze
        # sentinelvervanging om naar Pa (bar_naar_pa), zodat NaN gewoon NaN blijft.
        onbekend = df[kolom] == WATERDRUK_SENTINEL__bar
        df[vlagnaam] = onbekend
        df[kolom] = df[kolom].mask(onbekend, np.nan)

    return df
