# SPDX-License-Identifier: EUPL-1.2
"""Kolomvertaling van de ruwe WarmingUP-koppen naar ``physiquant__unit``-namen.

De ruwe kolomnamen zijn hier **geverifieerd tegen het echte archief**
(``data/raw/data-en-resultaten.zip``, 23-09-2026), niet overgenomen uit een samenvatting: twee
namen wijken af van wat je op het eerste gezicht zou verwachten.

* ``boiler-24h-stats.csv`` heet de tapwaterkolom in het echt ``Gas Usage Domestic Hot Water (DHW)
  (m³)`` (niet ``Gas Usage DHW (m³)``), en de kolom voor de brandertijd tapwater heet ``Heater
  Active Duration DWH (hours)`` -- met een **tikfout in de bron zelf** (``DWH``, niet ``DHW``). Dat
  is geen aanname van deze module maar een letterlijk citaat van de header.
* De watertdrukkolommen dragen hun eenheid en sentinelbetekenis al in de kop:
  ``Water Pressure CH Min (Bar -1=unknown)`` e.d.

Conventie: eenheid na de dubbele underscore, ``_cum`` alleen voor een meterstand op een moment
(hier komt dat niet voor: er staat geen enkele meterstand in deze dataset, zie
``ontwerp-preprocessing.md`` §3).
"""

from __future__ import annotations

#: ``boiler-temp.csv``: de kerntabel, één rij per woning per minuut.
BOILER_TEMP_KOLOMMEN = {
    "House": "home_id__str",
    "Time": "tijdstip",
    "Boiler Water Supply Temperature (°C)": "temp_aanvoer__degC",
    "Boiler Water Return Temperature (°C)": "temp_retour__degC",
    "Flow (l/h)": "debiet_ruw__l_h",
}

#: ``thermostat-temp.csv``: niet-equidistant, gebeurtenisgestuurd (zie ``ontwerp-preprocessing.md``
#: §4). Een ontbrekende minuut betekent hier "niets veranderd", niet "geen meting".
THERMOSTAT_TEMP_KOLOMMEN = {
    "House": "home_id__str",
    "Time": "tijdstip",
    "Thermostat Desired Temperature (°C)": "temp_setpoint__degC",
    "Thermostat Measured Temperature (°C)": "temp_binnen__degC",
}

#: ``boiler-24h-stats.csv``: etmaalstatistiek uit de ketel zelf, lokale tijdzone (zie ``tijd.py``).
BOILER_24H_STATS_KOLOMMEN = {
    "House": "home_id__str",
    "Day (Europe/Amsterdam)": "datum__str",
    "Gas Usage Domestic Hot Water (DHW) (m³)": "g_tapwater__m3",
    "Gas Usage Central Heating (CH) (m³)": "g_ruimteverwarming__m3",
    "Heater Active Duration DWH (hours)": "t_brander_tapwater__h",
    "Heater Active Duration CH (hours)": "t_brander_verwarming__h",
    # Nog in bar: pas ná sentinelvervanging (sentinels.flag_boiler_24h_stats) omrekenen naar Pa,
    # zie tabellen.build_etmaal. Een kolomnaam die al __Pa zegt terwijl de waarde nog in bar staat
    # zou zelf een klein foutbron zijn.
    "Water Pressure CH Min (Bar -1=unknown)": "p_cv_min__bar",
    "Water Pressure CH Avg (Bar -1=unknown)": "p_cv_gem__bar",
    "Water Pressure CH Max (Bar -1=unknown)": "p_cv_max__bar",
}

#: De resultatentabel (blad ``Sheet1`` van de xlsx), header op rij 5 (0-geïndexeerd), 22 kolommen in
#: de versie van 27-10-2026 van de bron (zonder ``logger_id`` en ``serial_no``).
#: ``blank col1`` is in de bron een volledig lege kolom (geverifieerd: alle 212 rijen NaN) en wordt
#: hier bewust weggelaten in plaats van vertaald.
#:
#: Twee kolomparen krijgen de eenheid ``__onbekend``: de bron documenteert ``model_*_rms``/
#: ``model_*_mean_bias_error`` niet, en aannemen dat dit °C is (plausibel voor een 2R2C-fit op de
#: binnentemperatuur) zou een gok als feit presenteren. Zie ontwerp-preprocessing.md, "Eigen
#: keuzes", en CLAUDE.md-regel 5: een getal zonder herkomst is schuld, en dat geldt evengoed voor
#: een eenheid zonder herkomst.
RESULTATEN_KOLOMMEN = {
    "Order": "resultaat_volgnummer__int",
    "woning_id": "home_id__str",
    "model_training_rms": "model_training_fout__onbekend",
    "model_validation_rms": "model_validatie_fout__onbekend",
    "model_training_mean_bias_error": "model_training_bias__onbekend",
    "model_validation_mean_bias_error": "model_validatie_bias__onbekend",
    "steady_state_heat_supply, Q_d [W]": "p_ontwerp__W",
    "C_i [J/C]": "c_binnen__J_K_1",
    "R_ie [C/W]": "r_binnen_schil__K_W_1",
    "A_w [m2]": "a_raam_effectief__m2",
    "C_e [J/C]": "c_schil__J_K_1",
    "R_ea [C/W]": "r_schil_buiten__K_W_1",
    "sv_supply_wa_60T": "temp_aanvoer_min__degC",
    "sv_return_wa_60T": "temp_retour_min__degC",
    "Woning_type": "woningtype__cat",
    "bouwjaar_bins": "bouwjaar_klasse__cat",
    "BJ_Cat": "bouwjaar_klasse_eindrapport__cat",
    "Gebruiksoppervlak_bin": "oppervlak_klasse__cat",
    "indicatief_gas [m3]": "g_jaarverbruik_indicatief__m3",
    "Total installed power, Q_a (kW)": "p_afgifte_geinstalleerd__W",
    "dimless heat power, Q_d/Q_a [-]": "overdimensionering__frac",
}

#: Kolom die in de bron leeg is en bewust niet wordt meegenomen (zie module-docstring).
RESULTATEN_GENEGEERDE_KOLOM = "blank col1"

#: Rij waarop de kop van ``Sheet1`` staat (0-geïndexeerd, dus ``header=5`` in ``pandas.read_excel``).
RESULTATEN_HEADER_RIJ = 5

#: Kolommen die bij het lezen met kW-eenheid binnenkomen en naar W omgerekend moeten worden.
RESULTATEN_KW_NAAR_W = ("Total installed power, Q_a (kW)",)


def debiet_l_h_naar_dm3_s(debiet__l_h):
    """``Flow (l/h)`` naar ``debiet__dm3_s_1``: 1 l = 1 dm3, dus delen door 3600 s/h.

    Conform de tapwaterconventie die elders in de zusterrepo's gebruikt wordt: delen door 3600, niet
    door 3,6. **Let op: dit moet toegepast worden ná het apart houden van de sentinel** (§6.4); de
    sentinel `2^32-1` is geen debiet en mag niet worden omgerekend en als getal doorgegeven, zie
    ``sentinels.py``.
    """
    return debiet__l_h / 3600.0


def bar_naar_pa(druk__bar):
    """Bar naar pascal: × 1e5. De sentinel ``-1`` (onbekend) wordt hier NIET afgehandeld; zie
    ``sentinels.py`` voor de sentinelvervanging naar NaN vóórdat deze omrekening plaatsvindt."""
    return druk__bar * 1e5
