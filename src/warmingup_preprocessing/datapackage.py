# SPDX-License-Identifier: EUPL-1.2
"""Bouwt ``datapackage.json`` (Frictionless Data Package v1, met een Table Schema per resource) UIT
DE CODE, niet met de hand bijgehouden.

**Bronnen van waarheid.** De velden per resource komen uit de ``pyarrow.Schema``-objecten die de
pijplijn zelf al gebruikt om te schrijven of te controleren
(:data:`warmingup_preprocessing.pijplijn.BOILER_TEMP_SCHEMA`/``THERMOSTAT_TEMP_SCHEMA``,
:data:`warmingup_preprocessing.tabellen.ETMAAL_SCHEMA`/``RESULTATEN_SCHEMA``/
``INFO_METADATA_SCHEMA``, :data:`warmingup_preprocessing.dekking.DEKKING_SCHEMA`). De laatste drie
zijn REFERENTIESCHEMA's: ze sturen het schrijfpad zelf niet aan (``bouw_resultaten`` e.d. laten
``pandas.to_parquet`` het Parquet-type nog steeds uit de dtypes afleiden), maar zijn geverifieerd
tegen de echte volledige-run-uitvoer (23-09-2026) en worden bewaakt door een test die borgt dat elk
Parquet-veld in het datapackage staat en omgekeerd (``tests/test_datapackage.py``): de twee kunnen
dus niet uit de pas lopen zonder dat een test rood wordt.

De beschrijving per veld staat hieronder in :data:`VELD_BESCHRIJVINGEN`, overgenomen uit
``docs/datacatalogus.md`` (dat op zijn beurt uit ``kolommen.py`` en de bronkolomnamen zelf komt);
zie dat bestand voor de volledige toelichting per kolom, inclusief formules en uitzonderingen.

**``primaryKey``: eerlijk weggelaten waar hij niet klopt.** ``(home_id__str, tijdstip)`` is voor
``boiler_temp`` en ``thermostat_temp`` GEEN geldige primaire sleutel: dubbele tijdstempels komen
voor (zie ``q_flag_tijdstip_dubbel__bool``, ontdekt en gevlagd, niet ontdubbeld). Ook voor ``etmaal``
is ``(home_id__str, datum__str)`` niet uniek: 5.856 van de 199.776 rijen in de echte
volledige-run-uitvoer (23-09-2026) hebben een dubbele combinatie, een bevinding bij het schrijven van
deze module (niet eerder gedocumenteerd; zie VOORTGANG.md). Voor de overige drie tabellen (resultaten,
info_metadata, dekking) is de voor de hand liggende sleutel WEL uniek gebleken op diezelfde
uitvoer, en die staat er daarom wel bij.

**Resourcepad van de twee per-woning-tabellen: altijd een patroon-string.** Data Package v1 staat
voor ``path`` naast een losse string ook een ARRAY toe ("multipart"), en het aantal woningbestanden
verschilt sowieso per run (220 vs. 223 in de volledige run, een ander aantal bij ``--test``) -- een
expliciete lijst leek dus aantrekkelijk voor de kopie die ``pijplijn.run`` aan het eind van een
CONCRETE run schrijft. Bij uitproberen bleek dat toch de verkeerde keuze: de multipart-vorm van Data
Package betekent letterlijk "plak deze bestanden aan elkaar tot één bytestroom", wat voor CSV werkt
maar voor Parquet een ongeldig bestand oplevert (elk Parquet-bestand heeft zijn eigen
header/footer/metadata). ``frictionless``'s eigen structurele validatie
(``Package.metadata_validate``) wijst een array-``path`` op deze twee resources dan ook expliciet af
("is not of type 'string'"). Deze module gebruikt daarom ALTIJD een PATROON-string
(``"boiler_temp/home_id=*.parquet"``, geen strikte Data Package v1-syntax maar wel wat de
``frictionless``-referentie-implementatie zelf ondersteunt), ook wanneer ``pijplijn.run`` de echte
bestandenlijst van een concrete run meegeeft; dat aantal komt dan alleen in de resourcetitel terecht,
niet in ``path``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa

from . import dekking as dekking_mod
from . import tabellen
from .manifest import UITVOER_CONTRACT_VERSIE

# Bewust GEEN moduleniveau-import van pijplijn.py: die importeert op zijn beurt deze module (om
# datapackage.json aan het eind van een run te schrijven), en een import op moduleniveau in beide
# richtingen geeft een circulaire-importfout. BOILER_TEMP_SCHEMA/THERMOSTAT_TEMP_SCHEMA worden daarom
# pas bij aanroep van bouw_datapackage() geïmporteerd (tegen die tijd zijn beide modules al geladen).

DATAPACKAGE_BESTANDSNAAM = "datapackage.json"

#: Bron van het archief: de versie van 27-10-2026, zonder mapping.csv en zonder logger- en
#: serienummers (zie GEBRUIKSVOORWAARDEN.md). De omvang is op afstand vastgesteld, zonder download;
#: een sha256 van deze versie is nog niet vastgelegd, en een veld zonder waarde laten we weg in
#: plaats van het te raden (CLAUDE.md-regel 5).
BRON_DOWNLOAD_URL = "https://data.inversable.cloud/how-low-can-you-go/data-en-resultaten.zip"
BRON_VERSIE = "2026-10-27"
BRON_SHA256: str | None = None
BRON_OMVANG__B = 1_798_660_453
KITE_PAGINA_URL = "https://kennisdelen.rvo.nl/"  # community "Kennis- en Dataplatform Individuele Technieken", projectpagina How-Low-Can-You-Go

#: Arrow-type -> Table Schema-type (https://specs.frictionlessdata.io/table-schema/#types-and-formats).
_ARROW_NAAR_TYPE = {
    pa.types.is_string: "string",
    pa.types.is_large_string: "string",
    pa.types.is_boolean: "boolean",
    pa.types.is_integer: "integer",
    pa.types.is_floating: "number",
    pa.types.is_timestamp: "datetime",
}


def _table_schema_type(arrow_type: pa.DataType) -> tuple[str, dict]:
    for test, naam in _ARROW_NAAR_TYPE.items():
        if test(arrow_type):
            extra = {}
            if naam == "datetime" and getattr(arrow_type, "tz", None):
                extra["format"] = "default"  # ISO 8601; pyarrow schrijft dit al zo naar Parquet
            return naam, extra
    raise ValueError(f"Geen Table Schema-type bekend voor Arrow-type {arrow_type!r}")


#: Beschrijving per (resourcenaam, veldnaam), overgenomen uit docs/datacatalogus.md §5. Vlagkolommen
#: die niet met naam voorkomen, krijgen een generieke tekst (zie _beschrijving hieronder): dat
#: voorkomt dat deze dict bij elke nieuwe q_flag-kolom apart bijgewerkt moet worden en toch fout kan
#: blijven staan (CLAUDE.md-regel 5 gaat over een getal zonder herkomst; hier is het inconsistentie
#: tussen twee bronnen die uit de pas lopen -- hetzelfde risico).
VELD_BESCHRIJVINGEN: dict[str, dict[str, str]] = {
    "boiler_temp": {
        "home_id__str": "Pseudoniem van de woning (WU0..WU242), stabiel over alle tabellen.",
        "tijdstip": "Tijdstip van de meting, tz-aware Europe/Amsterdam (intern eerst als UTC geparsed uit de "
        "bron, verliesvrij omgezet naar deze weergavezone; het instant verandert niet), minuutresolutie.",
        "temp_aanvoer__degC": "Aanvoertemperatuur naar de radiatoren (bron: Boiler Water Supply Temperature (degC)). "
        "De tekstsentinel \"x\" in de bron wordt hier ontbrekend (NaN).",
        "temp_retour__degC": "Retourtemperatuur van de radiatoren (bron: Boiler Water Return Temperature (degC)).",
        "debiet_ruw__l_h": "Rauw debiet, ongewijzigd inclusief sentinel (bron: Flow (l/h)). "
        "De sentinel 4294967295 (2^32-1, \"onbekend\") blijft hier zichtbaar als getal.",
        "debiet__dm3_s_1": "Debiet omgerekend (debiet_ruw__l_h / 3600). De sentinel wordt hier wel ontbrekend "
        "(NaN): uitzondering op \"vlaggen, niet verwijderen\".",
        "q_afgifte__W": "Afgeleid afgiftevermogen: (debiet__dm3_s_1 / 1000) * 998,2 * 4186 * "
        "(temp_aanvoer__degC - temp_retour__degC). Ontbrekend zodra een van de zes kwaliteitsvlaggen "
        "van deze tabel True is.",
        "q_flag_debiet_sentinel__bool": "True wanneer debiet_ruw__l_h gelijk is aan 4294967295 (2^32-1).",
        "q_flag_debiet_bovengrens__bool": "True wanneer debiet_ruw__l_h boven 5.000 l/h ligt en niet de sentinel is "
        "(orde-van-grootte-keuze, geen meting; zie sentinels.FLOW_BOVENGRENS__l_h).",
        "q_flag_temp_aanvoer_ontbrekend__bool": "True wanneer temp_aanvoer__degC ontbreekt (NaN, inclusief de "
        "tekstsentinel \"x\" in de bron).",
        "q_flag_temp_retour_ontbrekend__bool": "True wanneer temp_retour__degC ontbreekt (NaN).",
        "q_flag_temp_aanvoer_bereik__bool": "True wanneer temp_aanvoer__degC een getal is buiten [0, 100] graden C.",
        "q_flag_temp_retour_bereik__bool": "True wanneer temp_retour__degC een getal is buiten [0, 100] graden C.",
        "q_flag_tijdstip_dubbel__bool": "True vanaf de tweede keer dat (home_id, tijdstip) voorkomt; de eerste keer "
        "blijft False. Rijen worden gevlagd, niet verwijderd of ontdubbeld.",
    },
    "thermostat_temp": {
        "home_id__str": "Pseudoniem van de woning.",
        "tijdstip": "Tijdstip van de gebeurtenis, tz-aware Europe/Amsterdam (zie boiler_temp.tijdstip). Niet "
        "equidistant: een ontbrekende minuut betekent \"niets veranderd\", niet \"geen meting\".",
        "temp_setpoint__degC": "Gewenste (ingestelde) temperatuur (bron: Thermostat Desired Temperature (degC)).",
        "temp_binnen__degC": "Gemeten binnentemperatuur (bron: Thermostat Measured Temperature (degC)).",
        "q_flag_temp_setpoint_bereik__bool": "True wanneer temp_setpoint__degC een getal is buiten [5, 35] graden C.",
        "q_flag_temp_binnen_bereik__bool": "True wanneer temp_binnen__degC een getal is buiten [0, 40] graden C.",
        "q_flag_tijdstip_dubbel__bool": "True vanaf de tweede keer dat (home_id, tijdstip) voorkomt; de eerste keer "
        "blijft False. Rijen worden gevlagd, niet verwijderd of ontdubbeld.",
    },
    "etmaal": {
        "home_id__str": "Pseudoniem van de woning.",
        "datum__str": "Lokale kalenderdag, Europe/Amsterdam, ISO-8601-tekst. Bewust GEEN timestamp: niet naar "
        "UTC omgerekend (dat zou de dag zelf laten verschuiven).",
        "g_tapwater__m3": "Gasverbruik tapwater (bron: Gas Usage Domestic Hot Water (DHW) (m3)).",
        "g_ruimteverwarming__m3": "Gasverbruik ruimteverwarming (bron: Gas Usage Central Heating (CH) (m3)).",
        "t_brander_tapwater__h": "Brandertijd tapwater (bron: Heater Active Duration DWH (hours); tikfout in de "
        "bron zelf, DWH i.p.v. DHW).",
        "t_brander_verwarming__h": "Brandertijd ruimteverwarming (bron: Heater Active Duration CH (hours)).",
        "p_cv_min__Pa": "Minimale cv-waterdruk over het etmaal, omgerekend naar Pa (bron in bar; sentinel -1 "
        "eerst naar NaN, dan pas * 1e5).",
        "p_cv_gem__Pa": "Gemiddelde cv-waterdruk over het etmaal, omgerekend naar Pa.",
        "p_cv_max__Pa": "Maximale cv-waterdruk over het etmaal, omgerekend naar Pa.",
        "q_flag_gas_ruimteverwarming_bereik__bool": "True wanneer g_ruimteverwarming__m3 een getal is buiten [0, 50] m3.",
        "q_flag_gas_tapwater_bereik__bool": "True wanneer g_tapwater__m3 een getal is buiten [0, 10] m3.",
        "q_flag_brander_verwarming_bereik__bool": "True wanneer t_brander_verwarming__h een getal is buiten [0, 24] uur.",
        "q_flag_brander_tapwater_bereik__bool": "True wanneer t_brander_tapwater__h een getal is buiten [0, 24] uur.",
        "q_flag_druk_min_onbekend__bool": "True wanneer de bronwaarde van p_cv_min gelijk was aan -1 bar (\"unknown\").",
        "q_flag_druk_gem_onbekend__bool": "True wanneer de bronwaarde van p_cv_gem gelijk was aan -1 bar.",
        "q_flag_druk_max_onbekend__bool": "True wanneer de bronwaarde van p_cv_max gelijk was aan -1 bar.",
    },
    "resultaten": {
        "resultaat_volgnummer__int": "Oorspronkelijke rijvolgorde in de bron-xlsx (bron: Order); geen fysische "
        "grootheid, bewaard als herkomst van de volgorde.",
        "home_id__str": "Pseudoniem van de woning (bron: woning_id).",
        "model_training_fout__onbekend": "Modelfout, trainingsdeel (bron: model_training_rms). Eenheid bewust "
        "\"onbekend\": niet gedocumenteerd door Deltares.",
        "model_validatie_fout__onbekend": "Modelfout, validatiedeel (bron: model_validation_rms). Eenheid onbekend.",
        "model_training_bias__onbekend": "Modelbias, trainingsdeel (bron: model_training_mean_bias_error). Eenheid onbekend.",
        "model_validatie_bias__onbekend": "Modelbias, validatiedeel (bron: model_validation_mean_bias_error). Eenheid onbekend.",
        "p_ontwerp__W": "Ontwerp-warmtevraag (bron: steady_state_heat_supply, Q_d [W]).",
        "c_binnen__J_K_1": "Thermische massa binnenschil, 2R2C-model (bron: C_i [J/C]).",
        "r_binnen_schil__K_W_1": "Warmteweerstand binnen-schil, 2R2C-model (bron: R_ie [C/W]).",
        "a_raam_effectief__m2": "Effectief raamoppervlak voor zoninval, 2R2C-model (bron: A_w [m2]).",
        "c_schil__J_K_1": "Thermische massa schil, 2R2C-model (bron: C_e [J/C]).",
        "r_schil_buiten__K_W_1": "Warmteweerstand schil-buiten, 2R2C-model (bron: R_ea [C/W]).",
        "temp_aanvoer_min__degC": "Minimale aanvoertemperatuur uit de modelfit (bron: sv_supply_wa_60T).",
        "temp_retour_min__degC": "Minimale retourtemperatuur uit de modelfit (bron: sv_return_wa_60T).",
        "woningtype__cat": "Woningtype (bron: Woning_type), o.a. hoekwoning, tussenwoning, appartement.",
        "bouwjaar_klasse__cat": "Bouwjaarklasse (bron: bouwjaar_bins).",
        "bouwjaar_klasse_eindrapport__cat": "Bouwjaarklasse zoals in het eindrapport (bron: BJ_Cat), grover dan "
        "bouwjaar_klasse__cat.",
        "oppervlak_klasse__cat": "Gebruiksoppervlakteklasse (bron: Gebruiksoppervlak_bin).",
        "g_jaarverbruik_indicatief__m3": "Indicatief jaarlijks gasverbruik (bron: indicatief_gas [m3]).",
        "p_afgifte_geinstalleerd__W": "Geinstalleerd radiatorvermogen (bron: Total installed power, Q_a (kW), "
        "omgerekend naar W).",
        "overdimensionering__frac": "Verhouding ontwerp- op geinstalleerd vermogen, Q_d / Q_a (bron: dimless heat "
        "power, Q_d/Q_a [-]).",
    },
    "info_metadata": {
        "regel__int": "Regelnummer in het oorspronkelijke info-blad van de resultaten-xlsx.",
        "tekst__str": "Tekst van de regel, celwaarden samengevoegd met \" | \"; geen vertaling, geen interpretatie.",
    },
    "dekking": {
        "home_id__str": "Pseudoniem van de woning.",
        "bron__cat": "\"boiler_temp\" of \"thermostat_temp\".",
        "rijen__int": "Aantal rijen van deze woning in deze bron.",
        "eerste_tijdstip": "Eerste tijdstip in het venster van deze woning.",
        "laatste_tijdstip": "Laatste tijdstip in het venster van deze woning.",
        "dubbele_tijdstippen__int": "Aantal dubbele tijdstempels binnen deze woning/bron; telt alleen, verwijdert niets.",
        "dekking_fractie__frac": "Alleen voor boiler_temp: rijen / minuten-in-venster. NaN voor thermostat_temp.",
        "gemiddeld_interval__s": "Alleen voor thermostat_temp: gemiddeld interval tussen opeenvolgende metingen. "
        "NaN voor boiler_temp.",
    },
}

#: Velden die nooit ontbreken (gebruikt om constraints.required te zetten): sleutel- en
#: tijdstipkolommen, niet de meetwaarden of vlaggen zelf (die MOGEN ontbreken, dat is precies waar de
#: "ontbrekend"-vlaggen voor bestaan).
_VEREISTE_VELDEN = {"home_id__str", "tijdstip", "datum__str", "regel__int", "bron__cat"}

#: (resourcenaam, primaryKey-velden) voor de drie tabellen waar de sleutel WEL uniek is gebleken op de
#: echte volledige-run-uitvoer (23-09-2026, zie de moduledocstring); boiler_temp, thermostat_temp en
#: etmaal staan hier bewust NIET in.
_PRIMARY_KEYS: dict[str, list[str]] = {
    "resultaten": ["home_id__str"],
    "info_metadata": ["regel__int"],
    "dekking": ["home_id__str", "bron__cat"],
}

_GEEN_PRIMARY_KEY_REDEN: dict[str, str] = {
    "boiler_temp": "(home_id__str, tijdstip) is NIET uniek: dubbele tijdstempels komen voor en worden "
    "gevlagd (q_flag_tijdstip_dubbel__bool), niet ontdubbeld. Zie docs/datacatalogus.md paragraaf 6.",
    "thermostat_temp": "(home_id__str, tijdstip) is NIET uniek, zelfde reden als boiler_temp.",
    "etmaal": "(home_id__str, datum__str) is NIET uniek: 5.856 van de 199.776 rijen in de echte "
    "volledige-run-uitvoer (23-09-2026) hebben een dubbele combinatie. Niet eerder gedocumenteerd; "
    "bevinding bij het schrijven van deze module, zie VOORTGANG.md.",
}


def _veld(schema_veld: pa.Field, resourcenaam: str) -> dict:
    type_naam, extra = _table_schema_type(schema_veld.type)
    veld = {"name": schema_veld.name, "type": type_naam}
    beschrijving = VELD_BESCHRIJVINGEN.get(resourcenaam, {}).get(schema_veld.name)
    if beschrijving is None and schema_veld.name.startswith("q_flag_"):
        beschrijving = f"Kwaliteitsvlag: True wanneer {schema_veld.name.replace('q_flag_', '').replace('__bool', '')} " \
            "een plausibiliteitsgrens overschrijdt of ontbreekt; zie docs/datacatalogus.md. Vlaggen, geen verwijdering."
    veld["description"] = beschrijving or "Zie docs/datacatalogus.md voor de volledige beschrijving van dit veld."
    veld.update(extra)
    if schema_veld.name in _VEREISTE_VELDEN:
        veld["constraints"] = {"required": True}
    return veld


def _resource_boiler_of_thermostat(
    naam: str, schema: pa.Schema, titel: str, woning_bestanden: list[str] | None
) -> dict:
    # Altijd een patroon-string, ook wanneer de ECHTE bestandenlijst van een concrete run bekend is
    # (``woning_bestanden``, alleen gebruikt voor het aantal in de beschrijving hieronder). Data
    # Package v1 staat voor ``path`` ook een array toe (multipart), maar dat betekent bij de
    # referentie-implementatie letterlijk "plak deze bestanden aan elkaar tot één bytestroom" --
    # correct voor CSV, maar NIET voor Parquet (elk bestand heeft zijn eigen header/footer/metadata;
    # aan elkaar plakken geeft geen geldig Parquet-bestand). Geverifieerd: `frictionless`s eigen
    # structurele validatie (``Package.metadata_validate``) wijst een array-``path`` bij deze
    # resources ook af ("is not of type 'string'"), dus de patroon-vorm is niet alleen semantisch
    # juister maar ook de enige vorm die hier daadwerkelijk valideert.
    aantal = f" ({len(woning_bestanden)} bestanden in deze run)" if woning_bestanden is not None else ""
    return {
        "name": naam,
        "title": titel + aantal,
        "format": "parquet",
        "path": f"{naam}/home_id=*.parquet",
        "schema": {
            "fields": [_veld(f, naam) for f in schema],
            "missingValues": [""],
        },
        "primaryKeyOmittedReason": _GEEN_PRIMARY_KEY_REDEN[naam],
    }


def _resource_enkel_bestand(naam: str, schema: pa.Schema, titel: str, bestandsnaam: str) -> dict:
    resource = {
        "name": naam,
        "title": titel,
        "format": "parquet",
        "path": bestandsnaam,
        "schema": {
            "fields": [_veld(f, naam) for f in schema],
            "missingValues": [""],
        },
    }
    if naam in _PRIMARY_KEYS:
        resource["schema"]["primaryKey"] = _PRIMARY_KEYS[naam]
    else:
        resource["primaryKeyOmittedReason"] = _GEEN_PRIMARY_KEY_REDEN[naam]
    return resource


def _bron_archief() -> dict:
    bron = {
        "title": f"data-en-resultaten.zip (ruwe brondata, Deltares), versie van {BRON_VERSIE}",
        "path": BRON_DOWNLOAD_URL,
        "version": BRON_VERSIE,
        "bytes": BRON_OMVANG__B,
    }
    if BRON_SHA256 is not None:
        bron["sha256"] = BRON_SHA256
    return bron


def bouw_datapackage(
    contract_versie: str = UITVOER_CONTRACT_VERSIE,
    boiler_temp_bestanden: list[str] | None = None,
    thermostat_temp_bestanden: list[str] | None = None,
) -> dict:
    """Bouw het datapackage-object (een gewone ``dict``, direct naar JSON te schrijven).

    ``boiler_temp_bestanden``/``thermostat_temp_bestanden``: relatieve paden van de ECHT geschreven
    per-woningbestanden van een concrete run (bijvoorbeeld ``["boiler_temp/home_id=WU0.parquet",
    ...]``); als deze worden meegegeven, krijgt die resource een spec-conforme multipart ``path``
    (een lijst) in plaats van de generieke patroon-string. ``pijplijn.run`` geeft dit mee.
    """
    from .pijplijn import BOILER_TEMP_SCHEMA, THERMOSTAT_TEMP_SCHEMA  # zie de opmerking bovenaan dit bestand

    resources = [
        _resource_boiler_of_thermostat(
            "boiler_temp", BOILER_TEMP_SCHEMA, "Minuutdata aanvoer-/retourtemperatuur en debiet, per woning",
            boiler_temp_bestanden,
        ),
        _resource_boiler_of_thermostat(
            "thermostat_temp", THERMOSTAT_TEMP_SCHEMA, "Gebeurtenisgestuurde setpoint- en binnentemperatuur, per woning",
            thermostat_temp_bestanden,
        ),
        _resource_enkel_bestand("etmaal", tabellen.ETMAAL_SCHEMA, "Etmaalstatistiek (gas, branderuren, waterdruk)", "etmaal.parquet"),
        _resource_enkel_bestand(
            "resultaten", tabellen.RESULTATEN_SCHEMA,
            "2R2C-modelparameters, ontwerp- en geinstalleerd vermogen, woningkenmerken", "resultaten.parquet",
        ),
        _resource_enkel_bestand("info_metadata", tabellen.INFO_METADATA_SCHEMA, "Herkomsttekst van het info-blad van de resultatentabel", "info_metadata.parquet"),
        _resource_enkel_bestand("dekking", dekking_mod.DEKKING_SCHEMA, "Dekkingsstatistiek per woning per bron", "dekking.parquet"),
    ]

    return {
        "name": "warmingup-how-low-can-you-go-processed",
        "title": "WarmingUP How Low Can You Go: voorbewerkte meetdata (getypeerde Parquet-tabellen)",
        "description": (
            "Voorbewerkte meetdata van het WarmingUP-project Acceptabele Verlaagde Aanvoertemperatuur "
            "(How Low Can You Go), uitgevoerd door Deltares. Deze repo is niet de data-eigenaar; zie "
            "GEBRUIKSVOORWAARDEN.md voor licentie, meldplicht en herkomst van het archief, en "
            "docs/datacatalogus.md voor de volledige beschrijving van elke tabel. Gegenereerd door "
            "warmingup_preprocessing.datapackage, niet met de hand bijgehouden."
        ),
        "version": contract_versie,
        "licenses": [
            {
                "name": "andere",
                "title": (
                    "Geen open licentie: Deltares noemt geen licentienaam (geen CC BY, CC0, ODbL). "
                    "Gebruik is toegestaan onder de KITE-voorwaarde (meld gebruik op kite@rvo.nl en "
                    "deel analyseresultaten met de KITE-community); herverspreiding van de ruwe "
                    "dataset is niet toegestaan. Zie GEBRUIKSVOORWAARDEN.md in deze repo."
                ),
                "path": "GEBRUIKSVOORWAARDEN.md",
            }
        ],
        "sources": [
            {
                "title": "How Low Can You Go, KITE-projectpagina (Kennis- en Dataplatform Individuele Technieken)",
                "path": KITE_PAGINA_URL,
            },
            _bron_archief(),
        ],
        "contributors": [
            {"title": "Deltares", "role": "author", "organization": "Deltares"},
            {"title": "Kenniscentrum Duurzaam Leven", "role": "processor"},
        ],
        "resources": resources,
    }


def schrijf_datapackage(
    pad: Path,
    contract_versie: str = UITVOER_CONTRACT_VERSIE,
    boiler_temp_bestanden: list[str] | None = None,
    thermostat_temp_bestanden: list[str] | None = None,
) -> None:
    """Schrijf ``datapackage.json`` atomisch naar ``pad`` (``<pad>.tmp`` + hernoeming, net als de
    rest van de uitvoer, zie manifest.py)."""
    pakket = bouw_datapackage(contract_versie, boiler_temp_bestanden, thermostat_temp_bestanden)
    pad = Path(pad)
    pad.parent.mkdir(parents=True, exist_ok=True)
    tmp = pad.with_suffix(pad.suffix + ".tmp")
    tmp.write_text(json.dumps(pakket, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(pad)


def _relatieve_woning_bestanden(uit_dir: Path, onderdeel: str) -> list[str] | None:
    map_pad = uit_dir / onderdeel
    if not map_pad.is_dir():
        return None
    bestanden = sorted(map_pad.glob("home_id=*.parquet"))
    if not bestanden:
        return None
    return [str(p.relative_to(uit_dir)).replace("\\", "/") for p in bestanden]


def schrijf_datapackage_voor_run(uit_dir: Path, contract_versie: str = UITVOER_CONTRACT_VERSIE) -> Path:
    """Aanroep vanuit ``pijplijn.run``: schrijft ``<uit_dir>/datapackage.json`` met de ECHT
    geschreven woningbestanden van deze run (spec-conforme multipart ``path``, zie de
    moduledocstring)."""
    uit_dir = Path(uit_dir)
    pad = uit_dir / DATAPACKAGE_BESTANDSNAAM
    schrijf_datapackage(
        pad,
        contract_versie,
        boiler_temp_bestanden=_relatieve_woning_bestanden(uit_dir, "boiler_temp"),
        thermostat_temp_bestanden=_relatieve_woning_bestanden(uit_dir, "thermostat_temp"),
    )
    return pad


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--uit", type=Path, default=None,
        help="Map met een concrete run (bijvoorbeeld data/processed); als deze bestaat en "
        "boiler_temp/thermostat_temp-bestanden bevat, worden die expliciet opgenomen. Zonder deze "
        "vlag (of als de map niet bestaat) wordt de generieke patroon-vorm gebruikt.",
    )
    p.add_argument(
        "--pad", type=Path, default=Path(__file__).resolve().parents[2] / DATAPACKAGE_BESTANDSNAAM,
        help="Waar datapackage.json geschreven wordt (standaard: de repo-root).",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    boiler_bestanden = thermo_bestanden = None
    if args.uit is not None and args.uit.exists():
        boiler_bestanden = _relatieve_woning_bestanden(args.uit, "boiler_temp")
        thermo_bestanden = _relatieve_woning_bestanden(args.uit, "thermostat_temp")
    schrijf_datapackage(args.pad, boiler_temp_bestanden=boiler_bestanden, thermostat_temp_bestanden=thermo_bestanden)
    print(f"Geschreven: {args.pad}")


if __name__ == "__main__":
    main()
