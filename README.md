# warmingup-dataset-preprocessing

Van de ruwe meetdata van het WarmingUP-project **How Low Can You Go** naar getypeerde, herleidbare
Parquet-tabellen per woning. De preprocessing staat op zichzelf: wat hier uit komt is bruikbaar voor
iedereen die met deze dataset aan de slag gaat, ongeacht welke analyse erop volgt.

> **Lees eerst [`GEBRUIKSVOORWAARDEN.md`](GEBRUIKSVOORWAARDEN.md).** Gebruik moet gemeld worden bij
> KITE, analyseresultaten horen gedeeld te worden met de KITE-community, en de ruwe data staat niet
> in deze repo en wordt er ook niet via verspreid.

## Wat dit is

220 gasketelwoningen, anderhalf tot drie jaar lang gemonitord met een debietmeter en twee
temperatuursensoren op aanvoer en retour naar de radiatoren, op minuutresolutie, plus de
thermostaat- en ketellogging. Per woning is het opgenomen radiatorvermogen bekend. Het is voor zover
wij weten de enige Nederlandse veldcampagne die de **afgiftekant** zo meet.

## Wat eruit komt

Parquet per woning (zstd) voor de twee grote minuutbestanden, plus tabellen voor de etmaalstatistiek,
de sleuteltabel en de resultatentabel. Zie [`ontwerp-preprocessing.md`](ontwerp-preprocessing.md)
voor de volledige kolomvertaling, de keuzes en de aannames.

- streamend lezen uit de originele zip, zonder uitpakken;
- `thermostat-temp.csv` staat in het archief met **Deflate64** (`compress_type = 9`), wat Python's
  `zipfile` niet kan uitpakken; daarvoor is [`inflate64`](https://pypi.org/project/inflate64/) een
  afhankelijkheid, met een eigen kleine lezer eromheen (`deflate64.py`), zodat de keten zonder
  handwerk loopt;
- alle tijdstempels worden tz-aware opgeslagen, intern eerst als UTC geparsed en pas als laatste
  stap omgezet naar de weergavezone Europe/Amsterdam (zelfde instant, andere tz-metadata; zie
  ontwerp-preprocessing.md §6); de etmaaltabel blijft een lokale kalenderdag (`Europe/Amsterdam`),
  als tekst, niet omgerekend;
- dubbele tijdstempels (dezelfde woning, hetzelfde tijdstip) komen voor en worden gevlagd
  (`q_flag_tijdstip_dubbel__bool`), niet verwijderd of ontdubbeld;
- of het debiet begin- of eindgelabeld is, is **niet bekend**; de aanname staat expliciet en met naam
  in `tijd.py`, en `intervalsemantiek.py` is een losse toets die er een indicatie voor geeft, geen
  automatische beslissing (uitkomst over alle woningen: VOORTGANG.md);
- sentinels (`4294967295` voor debiet, `-40` °C, `-1` bar) en plausibiliteitsgrenzen worden gevlagd,
  niet verwijderd; alleen de afgeleide `q_afgifte__W` wordt `NaN` bij een onbetrouwbare invoerwaarde;
- de run is **hervatbaar** (`_manifest.jsonl`) en schrijft elke 45 seconden een voortgangsbestand
  (zie hieronder).

## Beginnen

```
pip install -e ".[dev]"
pytest -q
```

Zet `data-en-resultaten.zip` in `data/raw/` (zie GEBRUIKSVOORWAARDEN.md voor waar je hem vandaan
haalt) en draai:

```
python -m warmingup_preprocessing --droogloop         # laat zien wat er zou gebeuren
python -m warmingup_preprocessing --test               # een steekproef, klaar in minuten
python -m warmingup_preprocessing                      # de volledige run (circa een uur; zie VOORTGANG.md)
```

Belangrijkste CLI-opties: `--raw-dir` (standaard `data/raw`), `--uit`/`--out-dir` (standaard
`data/processed`), `--test` met `--test-mb` (standaard 50 MB per groot bronbestand), `--opnieuw` om
een eerdere gedeeltelijke run weg te gooien, `--droogloop` om niets te schrijven, `--lezer
pandas|pyarrow` (standaard `pyarrow`: de snelle route voor de twee grote minuutbestanden, zie
ontwerp-preprocessing.md §4; `pandas` is de oorspronkelijke, langzamere route en bestaat om de
gelijkheidstoets reproduceerbaar te houden). Zonder `--opnieuw` hervat een nieuwe aanroep een eerder
afgebroken run automatisch.

Voor de volledige, onbeheerde run: [`draai_volledig.cmd`](draai_volledig.cmd) (en
[`taak-volledig.xml`](taak-volledig.xml) om dat als Windows-taakplannertaak te registreren). Deze
repo start of registreert die taak niet zelf.

## Losse toetsen op de bron en de uitvoer

Twee modules die niets in de uitvoer van de pijplijn veranderen, bedoeld om met de hand te draaien (de
`draai_*.cmd`-bestanden doen dat los van een sessie):

```
python -m warmingup_preprocessing.bronscan --raw-dir data/raw --bestand boiler-temp.csv --uit data/scan
python -m warmingup_preprocessing.intervalsemantiek --uit data/processed --steekproef 0 --max-starts 0
```

`bronscan` leest elke rij van elke kolom van een CSV-lid van de zip en telt tekstwaarden, lege
velden, extremen en bekende sentinelwaarden (uitkomsten: [`docs/datacatalogus.md`](docs/datacatalogus.md)
§6.1). `intervalsemantiek` meet over alle woningen van een uitvoermap hoeveel minuten de
temperatuursprong na een pompstart afwijkt van de debietstart (uitkomst: [`VOORTGANG.md`](VOORTGANG.md)).
Beide lezen alleen en streamend.

## Het voortgangsbestand

`data/processed/_voortgang.json` wordt tijdens een run minstens elke 45 seconden overschreven (nooit
aangevuld), zodat iemand van buitenaf zonder de log te lezen een ETA kan uitrekenen:

```json
{
  "uitvoer_contract_versie": "2026-10-28-vierde-opzet",
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
```

`bytes_gelezen__B` en `bytes_totaal__B` zijn beide **ontcomprimeerd**, dus rechtstreeks deelbaar voor
een voortgangsfractie; `fase` loopt door `boiler_temp -> thermostat_temp -> etmaal ->
kleine_tabellen -> dekking -> kwaliteitsrapport -> datapackage -> klaar`. Zie
[`ontwerp-preprocessing.md`](ontwerp-preprocessing.md) §9 voor de volledige toelichting.

## Machineleesbare beschrijving: datapackage.json

Naast `docs/datacatalogus.md` (voor mensen) schrijft de pijplijn aan het eind van elke run ook
`datapackage.json`: een machineleesbare beschrijving van de zes uitvoertabellen volgens de
[Frictionless Data Package-standaard](https://specs.frictionlessdata.io/data-package/) (kolomnamen,
types, beschrijvingen, sleutels waar die uniek zijn). Wordt uit de code gegenereerd, niet met de
hand bijgehouden; regenereren kan met `python -m warmingup_preprocessing.datapackage`.

## Een uitvoermap van een oudere contractversie

De pijplijn verwerkt de versie van 27-10-2026 van de bron, zonder `mapping.csv` en zonder logger- en
serienummers (uitvoercontractversie `2026-10-28-vierde-opzet`). Uitvoer van een oudere
contractversie bouw je opnieuw op met een volledige run in een nieuwe uitvoermap; zie
`docs/datacatalogus.md` §7.

## Documenten

| document | waarover |
|---|---|
| [`GEBRUIKSVOORWAARDEN.md`](GEBRUIKSVOORWAARDEN.md) | de voorwaarden van de dataset, de meldplicht, en hoe je de dataset zelf verkrijgt |
| [`LICENSE`](LICENSE) | de licentie van de **code**: EUPL-1.2 |
| [`ontwerp-preprocessing.md`](ontwerp-preprocessing.md) | wat deze pijplijn doet, de kolomvertaling, en de keuzes |
| [`docs/datacatalogus.md`](docs/datacatalogus.md) | metadatabeschrijving van de uitvoer voor een datacatalogus: tabellen, kolommen, kwaliteit, hoe te laden |
| `docs/data-quality.md` | gegenereerd kwaliteitsrapport, door de pijplijn zelf geschreven |
| `datapackage.json` | machineleesbare Frictionless Data Package-beschrijving, door de pijplijn zelf gegenereerd |
| [`VOORTGANG.md`](VOORTGANG.md) | bouwstatus van de repo zelf: wat af is, wat volgt, open vragen |

## Licentie

De **code** in deze repository valt onder de European Union Public Licence 1.2 (`EUPL-1.2`), zie
[`LICENSE`](LICENSE). Kenniscentrum Duurzaam Leven heeft daartoe op 19-10-2026 besloten.

Copyright © 2026 Kenniscentrum Duurzaam Leven, Stichting Milieu Centraal

De **data** valt daar niet onder. De dataset en alles wat er per woning uit volgt, blijven onder de
voorwaarden van de dataset: gebruik melden bij KITE en analyseresultaten delen met de
KITE-community. De ruwe data staat niet in deze repo en wordt er ook niet via verspreid. Zie
[`GEBRUIKSVOORWAARDEN.md`](GEBRUIKSVOORWAARDEN.md).
