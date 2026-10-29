# Gebruiksvoorwaarden van de WarmingUP-dataset "How Low Can You Go"

Deze repository verwerkt de openbare meetdata van het WarmingUP-project **Acceptabele Verlaagde
Aanvoertemperatuur** (*How Low Can You Go*), uitgevoerd door **Deltares** met installatiebedrijf
Feenstra en de warmtebedrijven Vattenfall, HVC, SVP, Eneco en ENnatuurlijk; MMIP-projectnummer
TEUE819001. De ruwe dataset staat **niet** in deze git-repo (`data/` is gitignored) en wordt niet
door of via deze repo verspreid.

## Letterlijke voorwaarden

Van de KITE-pagina van het project, kopje "Licentie en gebruik":

> *"De dataset is openbaar beschikbaar gesteld door Deltares, maar beperkt zodat individuele
> personen/adressen onherleidbaar zijn."*
>
> *"KITE voorwaarde voor gebruik: meld datagebruik op kite@rvo.nl en deel uw analyseresultaten met de
> KITE community."*

Deltares is volgens dezelfde pagina auteur en **data-eigenaar**. Er wordt **geen licentienaam**
genoemd: geen CC BY, geen CC0, geen ODbL. Er staat dus niet dat de data herverspreid mag worden.

Het archief zelf bevat geen licentiebestand, alleen een `README.md` van drie regels die niets over
gebruik zegt.

## Wat dit betekent voor deze repo

1. **Melden vóór gebruik** op <kite@rvo.nl>, en in elk geval vóór er iets naar buiten gaat. Of de
   meldplicht ook geldt voor intern gebruik zonder publicatie is niet vastgesteld; de formulering
   *"meld datagebruik"* suggereert van wel.
2. **Analyseresultaten delen met de KITE-community.** Deze repo doet zelf geen analyse, maar wie de
   uitvoer gebruikt, valt onder deze voorwaarde.
3. **De ruwe data blijft buiten versiebeheer**, net als alles wat eruit volgt op woningniveau. De
   voorwaarde geeft geen recht de dataset te herpubliceren.
4. **Het eindrapport valt hier niet onder.** Dat draagt het standaard-Deltares-voorbehoud (*"© Alle
   rechten voorbehouden"*) en is strenger dan de dataset. Citeren met bronvermelding kan; meesturen
   of overnemen niet. Het staat daarom ook niet in deze repo.
5. **De code valt onder een eigen licentie.** De voorwaarde vraagt analyseresultaten te delen, niet
   de rekenmethode onder een bepaalde licentie. Deze voorbewerking is daarom zelf open: de code valt
   onder `EUPL-1.2` (besluit van Kenniscentrum Duurzaam Leven, 19-10-2026; zie [`LICENSE`](LICENSE)),
   zodat iedereen die de set bij KITE ophaalt, haar kan gebruiken en controleren. Inzichten en
   resultaten blijven onder de voorwaarden hierboven.

## Hoe je de dataset zelf verkrijgt

Het archief staat op een open URL, aangekondigd via de KITE-projectpagina *How-Low-Can-You-Go* in de
community *Kennis- en Dataplatform Individuele Technieken* op <https://kennisdelen.rvo.nl/>:

- <https://data.inversable.cloud/how-low-can-you-go/data-en-resultaten.zip>
  (versie van 27-10-2026, zonder `mapping.csv` en zonder logger- en serienummers; 1.798.660.453
  bytes, 11,5 GiB uitgepakt; sha256
  `cb33481174c70ad22a1116d4d6f54921e0c4133ca748d64931b3fee1a2a85ffc`)

Zet het archief ongewijzigd in `data/raw/`. **Pak het niet uit**: de pijplijn leest streamend uit de
zip, en één CSV is uitgepakt al 9,8 GB.

De KITE-pagina noemt onder "Versie" *"kite-versie 1.0 - oktober 2026"*; die aanduiding onderscheidt
de versies van het archief niet. Welke versie je hebt, stel je dus vast aan het archief zelf: de
omvang hierboven en de vijf leden (`boiler-temp.csv`, `thermostat-temp.csv`, `boiler-24h-stats.csv`,
`README.md` en de resultatentabel, zonder `mapping.csv`). De pijplijn is gebouwd op deze versie.
