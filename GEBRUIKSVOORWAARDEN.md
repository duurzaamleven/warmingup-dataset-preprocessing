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

Het archief zelf bevat geen licentiebestand, alleen een `README.md` van vier regels die niets over
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
  (1.798.671.500 bytes, 11,5 GiB uitgepakt; sha256
  `ecc288dda7b49cba1896f127f8269b6fb80e848bc96d26aa1c2a8598dafa87e0`, opgehaald 22-09-2026)

Zet het archief ongewijzigd in `data/raw/`. **Pak het niet uit**: de pijplijn leest streamend uit de
zip, en één CSV is uitgepakt al 9,8 GB.

De KITE-pagina noemt onder "Versie" *"kite-versie 1.0 - oktober 2026"*, terwijl de set op 22-09-2026
is opgehaald. Welke versie je precies hebt, stel je dus vast met de sha256, niet met de pagina.
