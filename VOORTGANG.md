# Voortgang van deze repo

Bijgewerkt: 28-10-2026. Dit document zegt wat er is, wat gemeten is en wat openstaat. Tijden in de
logs en hieronder zijn lokale tijd. De bouwgeschiedenis verderop blijft staan voor de redenering
achter de keuzes; wat er eerder was, staat in de git-geschiedenis.

## Stand

- De pijplijn verwerkt de versie van 27-10-2026 van de bron, zonder `mapping.csv` en zonder logger-
  en serienummers (uitvoercontractversie `2026-10-28-vierde-opzet`; zie "Bronversie van 27-10-2026"
  hieronder). Getest met synthetische data (`pytest -q`: 90 geslaagd, 3 slaan zichzelf over zonder de
  ruwe zip in `data/raw/`). Een volledige run op deze versie van de bron is nog niet gedaan.
- De volledige run en de migratie naar uitvoercontractversie `2026-09-23-derde-opzet` zijn gedaan
  (23-09-2026), op de vorige versie van de bron. Die uitvoer klopt rij voor rij met die bron, maar
  hoort niet bij het huidige contract.
- De twee kwaliteitstoetsen die nog openstonden zijn gedaan (03-10-2026): de intervalsemantiek over
  alle woningen en een volledige scan van de bronbestanden op tekstwaarden en andere sentinels.
  Uitkomsten hieronder en in `docs/datacatalogus.md` §6.1.
- De ruwe zip staat niet meer in `data/raw/` maar op een netwerkschijf buiten deze repo; geef de map
  mee met `--raw-dir` (of de omgevingsvariabele `RAW` in `draai_bronscan.cmd`).
- Open: zie "Open vragen".

## Bronversie van 27-10-2026

De bronhouder heeft op 27-10-2026 een nieuwe versie van `data-en-resultaten.zip` gepubliceerd op
dezelfde URL (1.798.660.453 bytes, zie GEBRUIKSVOORWAARDEN.md), zonder `mapping.csv` en zonder logger-
en serienummers. Vastgesteld door de centrale directory en de koppen op afstand te lezen, zonder de
hele zip te downloaden:

- Vijf leden in plaats van zes: `mapping.csv` ontbreekt; `README.md` (drie regels uitleg bij de
  csv's) staat er nog.
- In de resultatentabel (blad `Sheet1`) ontbreken de kolommen `logger_id` en `serial_no`; de kop
  staat nog op rij 6 en er zijn nog 212 woningen. Het `info`-blad heeft een andere tekst.
- De drie CSV-bestanden hebben dezelfde koppen en bestandsdatums als in de vorige versie.

Wat er in de code veranderd is: `mapping.csv` is geen verplicht lid meer en `mapping.parquet` vervalt;
`resultaten.parquet` verliest `logger_id__str` en `serial_no__str`; `migreer.py` en
`draai_migratie.cmd` zijn verwijderd, omdat uitvoer van de vorige bronversie niet zonder de nieuwe
bron om te zetten is. `draai_volledig.cmd` leest de zip nu uit de omgevingsvariabele `RAW`
(standaard `data
aw`). Een sha256 van deze versie is nog niet vastgelegd.

## De volledige run en de migratie (23-09-2026)

**De run.** Gestart om 13:15 via de Taakplanner (`draai_volledig.cmd`) met de pandas-lezer; om 15:34
gestopt en hervat met de pyarrow-lezer; klaar om 16:38 met exitcode 0. Het laatste deel duurde 3.876,6 s
(`Klaar in 3876.6 s` in `data/volledig-run.log`). De uitvoer staat in de uitvoermap van de volledige
run, op een netwerkschijf buiten deze repo, 3,2 GB:

| onderdeel | woningen | rijen |
|---|---:|---:|
| `boiler_temp` | 220 | 243.041.542 |
| `thermostat_temp` | 223 | 69.166.957 |
| `etmaal.parquet` | 223 | 199.776 |
| `mapping.parquet` | 243 | 243 |
| `resultaten.parquet` | 212 | 212 |
| `info_metadata.parquet` | | 17 |
| `dekking.parquet` | 220 + 223 | 443 |

De rijaantallen van de twee grote tabellen zijn gelijk aan de bron, zowel volgens het manifest als
geteld uit de Parquet-metadata; er zijn geen dubbele manifestregels, geen achtergebleven `.tmp` en
één schema per onderdeel. In de uitvoermap staan 220 bestanden in `boiler_temp/` en 223 in
`thermostat_temp/`, en `_voortgang.json` zegt fase `klaar`.

**De migratie** (`migreer.py`, zie `data/migratie.log`) naar `2026-09-23-derde-opzet`:

- Eerste start 20:52, klaar 21:14 (22 minuten) met exitcode 0: 243.041.542 en 69.166.957 rijen
  herschreven, `dekking.parquet` (443 rijen), `docs/data-quality.md` en `datapackage.json` herbouwd.
- Tweede start 21:55 stopte na 4 seconden met een `PermissionError` bij het overschrijven van
  `_voortgang.json` op de netwerkschijf (die weigerde dat tijdelijk). Sindsdien probeert het
  overschrijven het opnieuw (commit 8dca38b).
- Derde start 21:58 tot 22:05, exitcode 0: niets meer te migreren (0 rijen), wel `dekking.parquet`,
  het kwaliteitsrapport, `datapackage.json` en `_voortgang.json` bijgewerkt.

**Schatting en werkelijkheid.** Eerder geschat: 40 tot 50 minuten voor de run (eerste sessie), circa 75
minuten voor het resterende deel met de pyarrow-lezer (tweede sessie), 3,2 GB uitvoer en 1 tot 2 uur
voor de migratie. Gemeten: het laatste deel van de run 64,6 minuten, 3,2 GB, de migratie 22 minuten.

**Het kwaliteitsrapport.** `docs/data-quality.md` is het rapport van de volledige run, na de migratie
(243.041.542 en 69.166.957 rijen, 220 en 223 woningen, contractversie `2026-09-23-derde-opzet`; niet
van een testrun) en staat daarom ongewijzigd in de repo. Opvallend: 1.622.716 keer ontbrekende
aanvoertemperatuur (0,67%, de tekst `x`), 149.602 keer debiet boven 5.000 l/h, 253.721 dubbele
tijdstempels in `boiler_temp` en 2.368.296 in `thermostat_temp`.

**Geheugen.** De pyarrow-lezer gebruikte in de volledige run tot 1,5 GB (de pandas-lezer 0,44 GB) op
een machine met 8 GB. Daarna zijn de blokgrootte (16 MB) en `ARROW_DEFAULT_MEMORY_POOL=system`
aangepast (zie "Derde bouwsessie", punt 4); het piekgeheugen van een volledige run is daarna niet
opnieuw gemeten. De scan hieronder haalde met 16 MB blokken en dezelfde pool-instelling een piek van
894 MB (`boiler-temp.csv`) en 998 MB (`thermostat-temp.csv`).

## Kwaliteitstoetsen na de run (03-10-2026)

Beide gedraaid los van de sessie (`draai_intervalsemantiek.cmd`, `draai_bronscan.cmd`), alleen lezend
in de uitvoermap en de zip; de tussenresultaten staan onder `data/` (buiten git).

### Intervalsemantiek over alle woningen

`python -m warmingup_preprocessing.intervalsemantiek --steekproef 0 --max-starts 0` over de uitvoermap
van de volledige run, 18:06 tot 18:44 (38 minuten; het piekgeheugen is hier niet gemeten, een losse
steekproef van het proces gaf 200 MB). De vertraging is de minuut van de sterkste temperatuurstijging
in een venster van drie minuten voor tot drie minuten na de pompstart, min de startminuut van het
debiet. Negatief is dus "de temperatuur sprong vóór het debiet", nul "in dezelfde minuut", 1 "een
minuut erna".

- **Omvang.** 220 woningen gelezen, 219 met pompstarts: 3.959.734 pompstarts. WU175 heeft er geen,
  omdat zijn debiet in alle 132.524 niet-nul rijen boven de bovengrens van 5.000 l/h ligt (mediaan
  3.000.000 l/h) en dus gevlagd is. Per woning mediaan 15.430 pompstarts (grootste 82.628, kleinste na WU175 987).
- **"Zuivere" starts**: het venster bestaat uit echt opeenvolgende minuten (gevlagde rijen vallen
  weg, en de bron heeft gaten en dubbele tijdstempels) en de sterkste stijging is minstens 0,5 °C
  (kleiner is ruis; een keuze van de toets, geen meting). Dat zijn er 3.362.398; elke woning behalve
  WU175 heeft er minstens 861.
- **Verdeling over alle pompstarts** (vertraging in minuten: aantal): -2: 273.436, -1: 174.473,
  0: 1.441.080, 1: 1.180.126, 2: 548.271, 3: 342.348. Dat is 11,3% vóór de debietstart, 36,4% in
  dezelfde minuut en 52,3% erna (29,8% precies een minuut). Mediaan 1 minuut, p25 0, p75 1.
- **Verdeling over de zuivere pompstarts**: -2: 152.716, -1: 91.569, 0: 1.330.814, 1: 1.094.617,
  2: 456.058, 3: 236.624; 7,3% vóór, 39,6% gelijktijdig, 53,2% erna (32,6% precies een minuut).
  Mediaan 1, p25 0, p75 1.
- **Per woning** (zuivere starts, 219 woningen; percentielen p0, p10, p25, p50, p75, p90, p100 over
  de woningen): aandeel gelijktijdig 0,10, 0,24, 0,31, 0,40, 0,52, 0,63, 0,82; aandeel precies een
  minuut erna 0,08, 0,19, 0,24, 0,30, 0,41, 0,51, 0,74; aandeel vóór de start 0,00, 0,003, 0,007,
  0,024, 0,079, 0,157, 0,363. De mediane vertraging per woning is 0 bij 94 woningen, 1 bij 123 en 2
  bij 2; bij alle starts 0 bij 102, 1 bij 115 en 2 bij 2. Geen enkele woning heeft een negatieve
  mediaan.
- **Geen samenhang met het loggertype.** Per loggerserie (drie series, afgeleid uit de sleuteltabel
  van de vorige bronversie) is de verdeling van de woningmedianen vrijwel gelijk (34/42/1, 34/46/0 en 24/35/1
  woningen met mediaan 0, 1 en 2), dus het verschil tussen woningen is niet het verschil tussen drie
  loggertypen.

**Is dit genoeg om `tijd.AANNAME_DEBIET_INTERVAL_LABEL` vast te stellen? Nee.** Niet omdat er te
weinig data is (bijna vier miljoen pompstarts uit 219 woningen), maar omdat de uitkomst niet
eenduidig is: 47% van de zuivere starts heeft de temperatuursprong in dezelfde minuut of eerder, 53%
een of meer minuten later, en de helft van de woningen heeft mediaan 0 en de andere helft mediaan 1.
Onder de aanname dat debiet en temperatuur op hetzelfde moment worden bemonsterd, voorspelt een
begingelabeld debiet (de waarde op t dekt t tot t+1) een temperatuursprong op zijn vroegst een minuut
na de debietstart, dus nooit 0 of lager; dat komt bij 47% voor. Een eindgelabeld debiet (de waarde op t
dekt t-1 tot t) voorspelt 0 of 1, afhankelijk van hoe snel de sensor reageert; dat past bij 72% van de
starts, maar ruim 20% ligt twee of meer minuten erna (het venster houdt op bij 3, dus dat is een
ondergrens). Eindgelabeld past daarmee beter dan begingelabeld, maar geen van beide conventies past
zuiver, en met een minuutresolutie en een onbekende reactietijd van de sensor is labeling niet te
scheiden van sensorvertraging. Dit is een redenering, geen bewijs: dat temperatuur en debiet echt op
hetzelfde moment worden bemonsterd is niet vastgesteld.

**Aanbeveling.** Laat `AANNAME_DEBIET_INTERVAL_LABEL` op `"onbekend"` en verander hem niet op grond van
deze meting. Wie integreert of resamplet, doet er goed aan de keuze als gevoeligheid door te rekenen
(een verschuiving van nul en een van een minuut) in plaats van er een vast te kiezen. Vaststellen kan
alleen met informatie van buiten de data: vraag Deltares of de loggerleverancier hoe het debiet en de
temperatuur worden tijdgestempeld. De eerdere voorlopige indicatie "eerder begingelabeld" (mediaan 1
op 7 woningen, 23-09-2026) is hiermee achterhaald: ze berustte op 7 woningen met een fout in de
meting, zie hieronder; de uitkomst is nu eerder dat eindgelabeld iets beter past, maar niet zuiver.

**Correctie op de eerdere meting.** `numpy.argmax` geeft bij een `NaN` in het venster de plek van de
eerste `NaN` terug. Een ontbrekende aanvoertemperatuur (de tekst `x`) trok de gemeten vertraging dus
naar het gat. De standaard slaat `NaN` nu over (`--zonder-nan-correctie` reproduceert de oude
meting). Deze correctie is niet apart nagemeten op alle woningen: de run over alle woningen is met de
correctie gedaan.

### Volledige scan op tekstwaarden en andere sentinels

`python -m warmingup_preprocessing.bronscan` over elke rij van elke kolom van de vier CSV-leden en de
resultatentabel in `data-en-resultaten.zip`, streamend, als tekst. Looptijd: `boiler-temp.csv`
1.225 s (243.041.542 rijen), `thermostat-temp.csv` 136 s (69.166.957 rijen), de rest enkele
seconden; 17:42 tot 18:06 in totaal. Geen enkele rij heeft een afwijkend aantal velden. De volledige
tabel met per bestand en kolom wat er gevonden is staat in `docs/datacatalogus.md` §6.1. In het kort:

- `x` staat 1.622.716 keer in de aanvoertemperatuur (9 woningen; WU1 78,4% van zijn rijen, WU177
  61,7%, 211 woningen geen) en **881 keer in de retourtemperatuur** (3 woningen, vrijwel allemaal
  WU177). Beide aantallen zijn gelijk aan de twee `ontbrekend`-vlaggen in `data-quality.md`. De
  eerdere bewering "uitsluitend in de aanvoertemperatuur" (steekproef van 40 miljoen rijen) klopte
  dus niet.
- Andere tekst: `null` in `thermostat-temp.csv` (1.683 keer in de gewenste en 1.749 keer in de
  gemeten temperatuur) en `NaN` in `boiler-24h-stats.csv` (23 rijen, in de vier gas- en
  branderuurkolommen tegelijk, 12 woningen). Beide worden door de lezers al als lege waarde herkend.
- Geen nieuwe getalsentinels. Van de gezochte codes komen alleen de debietsentinel 2^32-1 (2.565 keer)
  en de waterdruk -1 (2 keer per kolom) voor, plus in de aanvoertemperatuur -40 (9), -1 (29) en 99
  (25). Fysiek onmogelijke getallen komen wel voor (gas per etmaal tot 429.000 m³, een
  binnentemperatuur van -319,6 °C) en worden door de bereikvlaggen afgevangen.
- In de resultatentabel staan geen tekstcellen in numerieke kolommen, wel parameters op een rond
  getal dat op een fitgrens lijkt (`C_i` 999.999.999,99 in 5 rijen, `A_w` 0 in 12 rijen); alleen een
  waarneming.

## Niet gedaan, bewust of nog niet

- De ongesorteerde schrijfroute (`schrijf_per_woning_ongesorteerd`) wordt door de echte data niet
  geraakt (beide grote bestanden zijn aaneengesloten per woning) en is alleen met een synthetische
  fixture getest.
- De intervalsemantiek-correctie voor `NaN` is niet apart doorgemeten op alle woningen (zie boven).
- `AANNAME_DEBIET_INTERVAL_LABEL` is niet aangepast; dat is bewust (zie de aanbeveling hierboven).
- Het verschil tussen de twee tellingen van de zomertijdgaten (kwaliteitsrapport 117 en 117 woningen,
  telling van de opdrachtgever 125 en 126) is niet uitgezocht; zie `docs/datacatalogus.md` §4.1.
- De drie tests tegen het echte archief (`tests/test_deflate64_echte_data.py`) slaan zichzelf over
  zolang de zip niet in `data/raw/` staat; ze zijn bij deze sessie niet gedraaid.

## Open vragen voor een volgende sessie of voor de opdrachtgever

1. Is `FLOW_BOVENGRENS__l_h = 5.000` een goede keuze? Het is een orde-van-grootte-schatting, geen
   afgeleide grens; zie `sentinels.py` en ontwerp-preprocessing.md §10.1. WU175 heeft een debiet dat
   er in alle niet-nul rijen ver boven ligt (mediaan 3.000.000 l/h); dat is eerder een fout in de bron
   dan een grensgeval.
2. De eenheid van `model_training_rms` e.d. is niet vastgesteld (`__onbekend`); wie de
   projectrapportage (`Verlengd meetproject Verlaagde aanvoertemperatuur.pdf`, genoemd in het
   `info`-blad) erbij haalt, kan dit mogelijk ophelderen.
3. De tekst `x` in de temperaturen (en `null`/`NaN` elders) is nergens gedocumenteerd, en bijna alles
   zit in twee woningen (WU1 en WU177). Het zou de moeite waard zijn dit bij KITE/Deltares te melden
   samen met de gebruiksmelding uit GEBRUIKSVOORWAARDEN.md.
4. Hoe worden debiet en temperatuur tijdgestempeld (begin, einde of moment van het interval)? Zonder
   antwoord blijft de intervalsemantiek `"onbekend"`.

## Voor wie hier verder gaat

- Alle code, tests en documenten staan gecommit. De branch `onderhoud/na-volledige-run` is gepusht;
  er is geen pull request en er is niet gemerged.
- Een volledige run: `draai_volledig.cmd` (zet `UITVOER` en `RAW` als de uitvoer of de zip elders
  staan; gebruik voor een nieuwe contractversie een nieuwe uitvoermap). De twee toetsen hierboven:
  `draai_bronscan.cmd` en `draai_intervalsemantiek.cmd`.
- Alles wat langer dan een paar minuten duurt, draai je los van een editor of chatsessie
  (`Start-Process ... -WindowStyle Hidden` met een van de `.cmd`-bestanden): de machine heeft weinig
  vrij geheugen en een proces uit een terminal gaat mee met de sessie.
- Op Windows faalt af en toe willekeurig een van de `test_run_*`-tests in `test_pijplijn.py` met een
  `PermissionError` bij het opruimen van een `tmp_path`-map; een tweede aanroep is groen. Dat is een
  bekend opruimprobleem van Windows en pytest.

## Eerste bouwsessie: wat er gebouwd is (23-09-2026)

Alles hieronder is de bouwgeschiedenis; waar iets inmiddels achterhaald is, staat dat erbij.

- Skelet gelezen (CLAUDE.md, README, GEBRUIKSVOORWAARDEN.md, pyproject.toml) en de vijf regels
  toegepast.
- Een zelfstandig `ontwerp-preprocessing.md` geschreven, zonder verwijzing naar de afnemende repo.
- Opzet, testpatroon en taakplanner-XML overgenomen uit een eerdere preprocessing-repo van dezelfde
  soort (manifest, atomisch schrijven, `.cmd`+`.xml`-paar); alleen de patronen, niet de inhoud.
- **Deflate64 opgelost en geverifieerd tegen de echte data**: `deflate64.py` leest de lokale
  zip-header zelf, berekent de dataoffset, en voedt `inflate64.Inflater` in blokken. Drie tests in
  `tests/test_deflate64_echte_data.py` draaien tegen het echte archief en slaan zichzelf over als
  `data/raw/` ontbreekt.
- **Sorteringscontrole uitgevoerd op de volledige, echte bronbestanden** (niet alleen een steekproef):
  `boiler-temp.csv` (243.041.542 rijen, 220 woningen, 208,6 s) en `thermostat-temp.csv`
  (69.166.957 rijen, 223 woningen, 62,7 s) staan BEIDE volledig aaneengesloten per woning, geen
  enkele revisit. De gesorteerde schrijfroute is dus de route die de volledige run neemt.
- Kernpijplijn gebouwd: `zipbron.py`, `kolommen.py`, `tijd.py`, `sentinels.py`, `manifest.py`,
  `voortgang.py`, `schrijvers.py` (gesorteerde route + ongesorteerde scatter/compacteer-fallback),
  `tabellen.py`, `dekking.py`, `intervalsemantiek.py`, `kwaliteitsrapport.py`, `pijplijn.py` (CLI met
  `--droogloop`, `--test`/`--test-mb`, `--opnieuw`, `--min-vrije-schijfruimte-gb`).
- 41 tests geschreven en groen (synthetische fixtures + drie Deflate64-tests tegen echte data).
  Onderweg een echte DST-bug gevonden en gefixt in `tijd.etmaalgrens_utc` (een vaste
  24-uursoptelling bij een tz-aware tijdstip springt niet mee met de zomertijdovergang).
- **Een echte, tot dusver ongedocumenteerde datavervuiling gevonden en opgelost**: de tekst `"x"` in
  plaats van een getal in de kolom `Boiler Water Supply Temperature (°C)` van `boiler-temp.csv`.
  Eerst gevonden over de eerste 40.000.000 rijen (999.002 keer); de volledige scan van 03-10-2026
  gaf het geheel: 1.622.716 keer, bijna alles in WU1 en WU177, en ook 881 keer in de retourtemperatuur
  (zie "Kwaliteitstoetsen na de run"). Opgelost met `na_values` in de CSV-lezer plus een aparte
  `q_flag_temp_aanvoer_ontbrekend__bool` (onderscheiden van "buiten het plausibele bereik"). Dit stond
  nergens in de documentatie van de bron of op de KITE-pagina.
- Volledige pijplijn end-to-end getest tegen de echte zip, met oplopende steekproefgrootte
  (`--test-mb` 5, 20, 50, 300): alle uitvoerbestanden correct, hervatten geverifieerd (een herhaalde
  aanroep op dezelfde steekproef: 0,8 s, alles overgeslagen), kolomwaarden gecontroleerd tegen de bron
  (`p_ontwerp__W`, `p_afgifte_geinstalleerd__W` kloppen exact met de xlsx).
- Doorvoer en piekgeheugen gemeten (zie hieronder) en de looptijd en omvang van een volledige run
  geëxtrapoleerd.
- De `intervalsemantiek`-toets gedraaid op een steekproef van 7 woningen (achterhaald; de toets is
  inmiddels over alle woningen gedraaid, zie "Kwaliteitstoetsen na de run").
- `draai_volledig.cmd` en `taak-volledig.xml` geschreven; de run is later via de Taakplanner gestart
  (zie "De volledige run en de migratie").
- `pyproject.toml` uitgebreid met `openpyxl` (nodig voor de resultatentabel; ontbrak in het skelet).

## Gemeten getallen

Gemeten met `--test --test-mb 300 --opnieuw --uit data/processed-test300` (23-09-2026, dezelfde
machine als de sorteringscontrole). `data/processed-test300` staat NIET in git (net als alle
`data/`-inhoud) en is een aparte map, los van `data/processed/` dat leeg is achtergelaten voor de
volledige run.

| bronbestand | gelezen (ontcomprimeerd) | rijen | duur schrijffase | doorvoer (schrijffase) | eenmalige sorteringscontrole |
|---|---:|---:|---:|---:|---:|
| `boiler-temp.csv` | 300 MB | 7.536.005 | 50 s | **6,0 MB/s** | 208,6 s (volledig bestand, eerder gemeten) |
| `thermostat-temp.csv` (Deflate64) | 300 MB | 8.242.461 | 65 s | **4,6 MB/s** | 62,7 s (volledig bestand, eerder gemeten) |
| `boiler-24h-stats.csv` | 11 MB (volledig) | 199.776 | < 2 s | (klein, niet apart gemeten) | n.v.t. |

Totale wandkloktijd van deze testrun: 161,0 s (waarvan circa 42 s eenmalige sorteringscontroles voor
déze steekproefgrootte, en circa 5 s voor etmaal + de drie kleine tabellen + dekking +
kwaliteitsrapport over de 7+24 woningen in de steekproef).

**Piekgeheugen: 331,4 MB** (RSS, hoofdproces; gemeten met `psutil`, bemonsterd elke 0,5 s). Ruim
onder de 8 GB-eis; de architectuur (hoogstens één `ParquetWriter` open per woning, streamend chunk
voor chunk) maakt dit in principe onafhankelijk van de bestandsgrootte, dus een piek van dezelfde
orde werd ook voor de volledige run verwacht. Dat klopte niet: de pyarrow-lezer haalde daar tot
1,5 GB (zie "De volledige run en de migratie", onderdeel Geheugen).

**Uitvoeromvang**: 81 MB voor 7.536.005 boiler_temp-rijen (10,7 bytes/rij), 72 MB voor 8.242.461
thermostat_temp-rijen (8,7 bytes/rij), beide zstd. `etmaal.parquet` (volledig, 199.776 rijen): 2,67 MB.

### Intervalsemantiek-toets: eerste meting op 7 woningen (23-09-2026)

Gedraaid met `python -m warmingup_preprocessing.intervalsemantiek --uit data/processed-test300
--steekproef 8`, op de 7 woningen uit de doorvoermeting hierboven, met een plafond van 200 pompstarts
per woning:

```
1400 pompstart(s) over 7 woning(en), mediane vertraging 1.00 minuut.
WU0: 1.0   WU1: 0.0   WU10: 1.0   WU100: 1.0   WU101: 0.0   WU102: 1.0   WU103: 0.0
```

Die meting is **achterhaald**: ze had een fout (bij een ontbrekende aanvoertemperatuur, de tekst `x`,
koos `numpy.argmax` de plek van het gat) en ze gebruikte maar een klein deel van de pompstarts. De
meting over alle woningen staat in "Kwaliteitstoetsen na de run".

## Tweede bouwsessie: snelheidsfix tijdens een lopende volledige run

**Aanleiding.** De volledige run (gestart via de Taakplanner, uitvoer op een netwerkschijf buiten
deze repo, zie `draai_volledig.cmd`) haalde circa 15.000 rijen/s in plaats van de circa
150.000 uit de eerste-sessie-testrun. Deze sessie werkte UITSLUITEND aan bronbestanden (het draaiende
proces heeft zijn code al geladen); `data/processed`, de Taakplannertaak en het proces zelf zijn niet
aangeraakt.

### Diagnose en oplossing

`cProfile` op `schrijf_per_woning_gesorteerd` (`--test --test-mb 100`) wees uit: circa 64% van de tijd
in `tijd.naar_utc_tijdstip` (`pandas.to_datetime` met een expliciet formaat, dat toch op de trage
`_array_strptime_with_fallback`-route terechtkwam), circa 37% in `pandas.read_csv` zelf. Een
microbenchmark op 1.000.000 tijdstempels bevestigde drie routes met IDENTIEKE waarden, sterk
verschillende snelheid: het huidige formaat 40 s, `format="ISO8601"` 17 s, `pyarrow.compute.strptime`
7 s.

Nieuwe module `src/warmingup_preprocessing/snelle_lezer.py`: leest `boiler-temp.csv` en
`thermostat-temp.csv` met `pyarrow.csv.open_csv` (streamend, blokgrootte 32 MB, vaste kolomtypen,
`Time` rechtstreeks naar `timestamp(ns, UTC)`, `"x"` als null via `null_values`/
`strings_can_be_null`), en levert per Arrow-batch een pandas-`DataFrame` met dezelfde kolomnamen en
dtypes als de oude route. Alles NA dat punt -- hernoemen, `sentinels.flag_*`, cast naar het
Parquet-schema -- is ONGEWIJZIGD: dat is waar de bit-voor-bit-gelijkheid op steunt (zie
ontwerp-preprocessing.md §4.1 voor de volledige onderbouwing).

`schrijvers.schrijf_per_woning_gesorteerd` kreeg een `lezer`-parameter (`"pyarrow"` nieuwe standaard,
`"pandas"` de oude route) en `pijplijn.py` een `--lezer pandas|pyarrow` CLI-vlag. Voltooide woningen
worden bij de pyarrow-route al op Arrow-niveau weggefilterd (`filtreer_voltooide_woningen`, vóór de
pandas-conversie): dat maakt hervatten goedkoper. De sorteringscontrole
(`controleer_aaneengesloten`/`snelle_lezer.controleer_aaneengesloten_snel`) kreeg dezelfde
lezer-keuze, met `include_columns=["House"]` zodat alleen de huiskolom geparsed wordt.

### Tests

50 pytests groen (was 41; de bestaande schrijvers-tests draaien nu voor beide lezers, plus een nieuwe
`tests/test_snelle_lezer_gelijkheid.py` met een synthetische fixture die "x", lege velden, de
debiet-sentinel (`2**32-1`) en de Nederlandse zomertijdovergang van 28 maart 2021 combineert).

### Gelijkheidstoets tegen de echte bron

`--test --test-mb 50` gedraaid met beide lezers naar `data/vergelijk-oud` en `data/vergelijk-nieuw`
(apart van `data/processed`, buiten git). Resultaat, per tabel:

| tabel | aantal woningen/rijen | bit-voor-bit gelijk (`pyarrow.parquet.read_table(...).equals(...)`) |
|---|---|---|
| `boiler_temp` | 2 woningen (902.564 + 388.542 rijen, met 113.208 "x"-rijen in WU1) | **ja** |
| `thermostat_temp` | 5 woningen (1.409.955 rijen totaal) | **ja** |
| `etmaal.parquet` | 199.776 rijen | **ja** |
| `mapping.parquet` | 243 rijen | **ja** |
| `resultaten.parquet` | 212 rijen | **ja** |
| `info_metadata.parquet` | 17 rijen | **ja** |
| `dekking.parquet` | 7 rijen | **ja** |

Geen enkel verschil gevonden. Het "x"-aantal (113.208) is bovendien onafhankelijk geverifieerd tegen
een derde, losse telling rechtstreeks op de ruwe CSV-tekst (exact gelijk) -- dus niet alleen "de twee
routes zijn het eens", maar "de twee routes zijn het eens EN hebben allebei gelijk". Een herhaalde
aanroep met dezelfde `--test-mb 50` op dezelfde `data/vergelijk-nieuw`-map: 3,4 s, geen enkele woning
opnieuw geschreven (hervatten werkt).

### Doorvoermeting (oud vs. nieuw, ONDER DE HUIDIGE SYSTEEMLAST -- de volledige run liep tegelijk mee
op dezelfde ene kern)

| bronbestand | steekproef | pandas (oud) | pyarrow (nieuw) | versnelling |
|---|---:|---:|---:|---:|
| `boiler-temp.csv` | 150 MB, 3.880.525 rijen | 155,6 s -- 24.947 rijen/s | 50,9 s -- 76.280 rijen/s | 3,1x |
| `thermostat-temp.csv` (Deflate64) | 100 MB, 2.772.898 rijen | 248,2 s -- 11.172 rijen/s | 39,9 s -- 69.472 rijen/s | 6,2x |

Dit is een ONDERGRENS: zonder de meelopende volledige run (die dezelfde ene kern deelt) zou de winst
waarschijnlijk groter zijn.

### Hervatten met de nieuwe code

De lopende run is op 23-09-2026 om 15:34 gestopt en met de pyarrow-lezer hervat; dat werkte zonder
handmatig opruimen, omdat een bestand pas zijn definitieve naam krijgt na een geslaagde schrijfactie
en een manifestregel pas daarna komt (ontwerp-preprocessing.md §5), en omdat `_sortering.json` een
feit over de brondata is, niet over de lezer die het vaststelde. De uitkomst van die hervatte run
staat in "De volledige run en de migratie" bovenaan.

## Derde bouwsessie: vijf reparaties, datapackage.json, migratiescript, aanvullende eisen (23-09-2026)

**Aanleiding.** Vier open punten uit de eerste volledige run (hierboven), plus een dubbele-
tijdstempel-reparatie, plus (tijdens deze sessie binnengekomen) drie aanvullende eisen van de
opdrachtgever: Europe/Amsterdam als weergavezone, een migratiescript in plaats van een herrun, en
geen intern NAS-pad in gedeelde documentatie. Ook een vierde aanvulling met een zomertijd-bevinding
(zomertijdgaten in `boiler_temp`) en een vijfde met te verwerken content uit het Deltares-eindrapport
voor `docs/datacatalogus.md`. De NAS-uitvoermap is deze sessie **niet aangeraakt**; alle metingen en
testruns gingen naar aparte, lokale mappen onder `data/` (buiten git).

### 1. Dubbele tijdstempels vlaggen (q_flag_tijdstip_dubbel__bool)

Nieuwe kolom in `boiler_temp` en `thermostat_temp`: True vanaf de TWEEDE keer dat een tijdstip voor
een woning voorkomt. Gecontroleerd of de bron op tijd gesorteerd is binnen een woning (zoals de
opdracht vroeg): **nee** -- een steekproef van 6 woningen uit `data/processed-test300` liet
terugspringende tijdstempels zien (WU1: 10 sprongen terug van 121 tot 2.639 minuten over 1.272.082
rijen). De implementatie (`sentinels.flag_tijdstip_dubbel`) houdt daarom een `set` bij met ALLE
eerder geziene tijdstippen van de huidige woning, over chunk-/batchgrenzen heen, in plaats van alleen
de vorige rij te vergelijken. Geverifieerd tegen de bestaande `dekking.parquet`
(`dubbele_tijdstippen__int`) op een steekproef van 6 woningen: exact gelijk. `dekking.py` gebruikt de
nieuwe kolom nu als bron van waarheid (valt terug op de oude sort+duplicated-berekening als de kolom
ontbreekt, voor oudere uitvoer). Telling ook in `kwaliteitsrapport.py`.

### 2. logger_id__str overal tekst

`kolommen.naar_string_zonder_punt0`: cast expliciet naar tekst via de nullable `Int64`-extensie
(voorkomt een `.0`-staart bij een ontbrekende waarde). Toegepast in `tabellen.bouw_resultaten` (waar
het echte verschil zat, `int64` i.p.v. `string`) en defensief in `bouw_mapping`.

Na 1 en 2: `UITVOER_CONTRACT_VERSIE` naar `"2026-09-23-tweede-opzet"`.

### 3. rijen_gelezen bleef 0 bij hervatten met de pyarrow-lezer

Oorzaak: `_pyarrow_chunks` filtert per Arrow-batch de rijen van al voltooide woningen weg vóórdat de
batch ge-yield wordt; een batch die daardoor volledig leeg werd, werd overgeslagen (`continue`, geen
yield), en de buitenste lus telde `rijen_gelezen_totaal` alleen op via `len(chunk)` van ge-yielde
chunks. Fix: `_pyarrow_chunks` krijgt een `op_rijen_gelezen`-callback die na ELKE gelezen batch wordt
aangeroepen met het cumulatieve aantal RUWE (nog niet gefilterde) rijen. Regressietoets: een
hervatting met alle woningen al voltooid rapporteert nu het volledige bronrijenaantal, niet 0.

### 4. Geheugen van de pyarrow-lezer

Gemeten op `--test --test-mb 200` tegen de echte bron, rustige machine, piekgeheugen met `psutil`
elke 0,2 s bemonsterd:

| block_size | duur | doorvoer (rijen/s) | piekgeheugen (RSS) |
|---|---:|---:|---:|
| 32 MB | 470,8 s | 22.584 | 599,1 MB |
| 16 MB | 512,4 s | 20.748 | **561,5 MB** |
| 8 MB  | 610,1 s | 17.427 | 611,2 MB |

Piekgeheugen daalt NIET monotoon met een kleinere blokgrootte (8 MB gaf het HOOGSTE piekgeheugen);
alleen de doorvoer daalt duidelijk en monotoon. Nieuwe standaard: **16 MB** (laagste piekgeheugen op
deze meting, 8% doorvoerverlies t.o.v. 32 MB tegenover 23% bij 8 MB). Kanttekening: deze meting
(5-5,5 miljoen rijen) is veel kleiner dan de volledige run (243+69 miljoen rijen); de standaard
Arrow-geheugenpool geeft vrijgegeven blokken niet aan het systeem terug
(`ARROW_DEFAULT_MEMORY_POOL=system` in `draai_volledig.cmd`), dus `block_size` verklaart het eerder
geziene 1,5 GB vermoedelijk niet volledig -- de geheugenpoolinstelling is er waarschijnlijk minstens
zo belangrijk voor. `--block-size-mb` toegevoegd als CLI-vlag om dit reproduceerbaar te houden.

### 5. Waar gaat de tijd bij Deflate64 heen?

cProfile op het ONBEGRENSDE pad (zoals de volledige run het echt gebruikt, dus zonder
`_BegrensdeStream`) van de sorteringscontrole van `thermostat-temp.csv`, rustige machine, 420-440 MB
steekproef: **circa 78% in inflate64.Inflater.inflate** (de decompressie zelf, inherent, niet te
versnellen zonder een andere decompressor), **circa 16% in schijf-I/O** (`io.BufferedReader.read`,
eveneens inherent), en vóór de fix **circa 16% in de Python-lus** die over elke rij ging om
aaneengeslotenheid te controleren (`for waarde in batch.column(...).to_pylist(): ...`).

Dat laatste deel IS opgelost: `snelle_lezer._kolom_naar_runs` reduceert een Arrow-batch tot zijn
aaneengesloten "runs" met een vectorale `numpy`-vergelijking (`arr[1:] != arr[:-1]`) in plaats van een
Python-lus over elke waarde; de lus loopt daarna alleen nog over het aantal woningwisselingen. Op
dezelfde steekproef: de Python-overhead van de testharness daalde van 1,83 s naar 0,39 s (tottime in
het cProfile-profiel), zonder regressie in de decompressie- of I/O-tijd.

**Relativering van de eerdere metingen.** Op deze rustige machine haalt `inflate64` hier circa 48
MB/s pure decompressiedoorvoer, ongeveer het dubbele van de eerder (onder belasting) aangenomen 24
MB/s. De eerder gerapporteerde 1.153 s voor de volledige sorteringscontrole van `thermostat-temp.csv`
is dus vermoedelijk grotendeels toe te schrijven aan systeembelasting tijdens die meting (de
volledige run liep toen nog mee), niet aan een verborgen fout -- de nu opgeloste Python-lus scheelt
voor het volledige bestand naar schatting enkele seconden op een totaal van meerdere honderden
seconden: een reële maar niet dominante besparing.

### 6-8. datapackage.json (Frictionless Data Package v1)

Nieuwe module `datapackage.py` bouwt het bestand UIT DE CODE: de Parquet-schema's die de pijplijn al
gebruikt (`pijplijn.BOILER_TEMP_SCHEMA`/`THERMOSTAT_TEMP_SCHEMA`, `tabellen.ETMAAL_SCHEMA` plus drie
nieuwe referentieschema's `MAPPING_SCHEMA`/`RESULTATEN_SCHEMA`/`INFO_METADATA_SCHEMA`,
`dekking.DEKKING_SCHEMA`), met beschrijvingen overgenomen uit `docs/datacatalogus.md`.
`primaryKey` eerlijk behandeld: `mapping`/`resultaten`/`info_metadata`/`dekking` hebben er een
(geverifieerd uniek op de echte volledige-run-uitvoer), `boiler_temp`/`thermostat_temp`/`etmaal`
NIET -- voor `etmaal` een NIEUWE bevinding bij het bouwen van deze module: 5.856 van de 199.776 rijen
hebben een dubbele `(home_id, datum)`-combinatie, niet eerder gedocumenteerd.

Resourcepad van `boiler_temp`/`thermostat_temp`: ALTIJD een patroon-string
(`"boiler_temp/home_id=*.parquet"`). Eerst geprobeerd met de spec-conforme "multipart"-array-vorm
wanneer de echte bestandenlijst van een run bekend was, maar dat bleek zowel inhoudelijk fout
(multipart betekent "plak deze bestanden aan elkaar", wat voor Parquet een ongeldig bestand geeft) als
door `frictionless`'s eigen structurele validatie afgewezen te worden; ontdekt tijdens het testen van
een `--test --test-mb 50`-run, hersteld in een aparte commit.

`frictionless>=5,<6` toegevoegd als dev-afhankelijkheid. Structurele validatie
(`Package.metadata_validate`, dus tegen het JSON Schema-profiel, zonder de Parquet-data te lezen): 0
fouten, zowel voor de generieke repo-root-kopie als voor de kopie van een concrete testrun. Validatie
tegen echte data, bewust beperkt tot een kleine steekproef (niet de hele set): `resultaten.parquet`
(212 rijen) en één woningbestand uit een `--test --test-mb 5`-run, beide geldig met
`frictionless.Resource.validate()`. Ter controle ook geprobeerd tegen
`data/processed-test300/resultaten.parquet` (oude contractversie, vóór de `logger_id__str`-fix): dat
gaf terecht type-fouten op `logger_id__str` (`int64` in plaats van `string`) -- de validatie
onderscheidt dus daadwerkelijk oude van nieuwe uitvoer.

`tests/test_datapackage.py` borgt dat elk veld in de Parquet-schema's in het datapackage staat en
omgekeerd. README.md en `docs/datacatalogus.md` verwijzen nu naar `datapackage.json`.

### Aanvullende eis: Europe/Amsterdam als weergavezone

Alle tz-aware tijdstempels in de uitvoer (`tijdstip` in `boiler_temp`/`thermostat_temp`,
`eerste_tijdstip`/`laatste_tijdstip` in `dekking.parquet`) staan sinds deze sessie in de
weergavezone Europe/Amsterdam in plaats van UTC. Het instant verandert niet, alleen de tz-metadata:
`tijd.naar_utc_tijdstip` blijft de interne rekenbasis, `tijd.naar_weergave_tijdzone` (nieuw,
`tz_convert`, geen `tz_localize`) zet pas als allerlaatste stap vóór het schrijven om, op precies
dezelfde plek in beide schrijfroutes (na de dedupvlag, vóór de schema-cast), zodat de pandas- en
pyarrow-route bit-voor-bit gelijk blijven. Onderbouwing (van de opdrachtgever, met bronvermelding
overgenomen in `docs/datacatalogus.md` §4): de bron labelt de etmaaltabel al als
`Day (Europe/Amsterdam)`; de steekproef is gericht op de Nederlandse woningvoorraad; het
KNMI-weerstation dat het eindrapport gebruikt (Deelen) ligt geografisch het dichtst bij de meeste
onderzochte gebouwen; de vijf warmtebedrijven leveren in Europees Nederland. `UITVOER_CONTRACT_VERSIE`
naar `"2026-09-23-derde-opzet"`.

### Aanvullende eis: migratiescript in plaats van een herrun

Achterhaald: `migreer.py` is verwijderd bij de overstap naar de bronversie van 27-10-2026
(contractversie `2026-10-28-vierde-opzet`).

`python -m warmingup_preprocessing.migreer --uit <map>` (nieuwe module `migreer.py`) migreert een
bestaande uitvoermap van `"2026-09-23-eerste-opzet"` naar de huidige contractversie zonder de ruwe zip
opnieuw te lezen: per woningbestand rijgroep voor rijgroep herschreven (nooit het hele bestand
tegelijk in geheugen), `resultaten`/`mapping` krijgen `logger_id__str` als string,
`etmaal`/`info_metadata` krijgen alleen een nieuwe manifestregel (geen inhoudelijke wijziging),
`dekking.parquet`/`docs/data-quality.md`/`datapackage.json` worden herbouwd. Hervatbaar en idempotent
via hetzelfde `Manifest.is_voltooid`-mechanisme als de hoofdpijplijn; geen apart
migratiestatusbestand.

Gevalideerd tegen een verse run met de huidige code: een kopie van twee woningen uit
`data/processed-test300` (nog van de oude contractversie) gemigreerd en met
`pyarrow.parquet.read_table(...).equals(...)` vergeleken met dezelfde twee woningen uit een `--test
--test-mb 300`-run met de huidige code -- **bit-voor-bit gelijk**, voor `boiler_temp`,
`thermostat_temp`, `resultaten.parquet` en `mapping.parquet`. Idempotentie bevestigd (tweede aanroep:
0,5 s, niets opnieuw geschreven). Daarna door de opdrachtgever op de uitvoermap van de volledige run gedraaid
(zie "De volledige run en de migratie").

### Aanvullende eis: geen intern NAS-pad in gedeelde documentatie

Een zoektocht naar de interne NAS-hostnaam gaf zes treffers (VOORTGANG.md x2, docs/datacatalogus.md, draai_volledig.cmd,
manifest.py, tabellen.py); allemaal generiek gemaakt ("de uitvoermap van de eerste volledige run",
"een netwerkschijf buiten deze repo"), behalve `draai_volledig.cmd` (lokale configuratie, toegestaan)
-- daar is de STANDAARDWAARDE van de `UITVOER`-omgevingsvariabele omgezet naar een lokaal pad
(`data\processed`); wie naar een netwerkschijf wil schrijven, zet die variabele zelf, zonder dat de
repo de hostnaam hardcodeert. Na deze wijziging staat die hostnaam nergens meer
buiten `data/` (gitignored).

### Aanvullende bevinding: zomertijdgaten in boiler_temp rond de oktoberwissel

Van de opdrachtgever (methode en cijfers in `docs/datacatalogus.md` §4.1): bij 125 van 206
respectievelijk 126 van 212 woningen met data ontbreekt rond de oktoberwissels 2021 en 2022 precies
het TWEEDE uur van het dubbelzinnige lokale tijdvenster (01:00-01:59 UTC); getoetst aan de
temperatuursprong rond het gat is dit een echt ontbrekend uur, geen verkeerd toegewezen dubbeling.
Geen correctie in de data. Nieuwe telling in het kwaliteitsrapport
(`kwaliteitsrapport._tel_dst_oktobergaten`, gecontroleerd op de test-na-fixes-run: 1 van 1 woning met
data had het gat, op beide datums).

### Aanvullende eis: literatuur verwerkt in docs/datacatalogus.md

Het Deltares-eindrapport (Pothof, Vreeken & Van Meerkerk, 13 september 2022) gelezen (28 pagina's, via
`pypdf`) en gebruikt om de in-/uitsluitcriteria, de steekproefopzet, de meetopstelling en de betekenis
van de resultatentabelkolommen (2R2C, `Q_d` met de 18-uursaanname, `Q_a` bij 75/65/20,
`sv_supply_wa_60T`) toe te voegen aan `docs/datacatalogus.md`, elk met paginanummer. Geparafraseerd
en met korte citaten (het rapport draagt "© Alle rechten voorbehouden"), geen tabellen of figuren
overgenomen. Tegenstrijdigheden tussen rapport en data expliciet genoemd: de `Ci`/`Ce`-eenheid
(rapport: Wh/°C; brontabelkop: J/C, factor 3600), het aantal rijen in `resultaten.parquet` (212,
tegenover 220 steekproefwoningen en 187 geslaagde modelkalibraties in het rapport), en de vroegste
`boiler_temp`-meting (2020-04-09, vóór het installatievenster januari-november 2021 dat het rapport
noemt). Bronnenlijst toegevoegd (`docs/datacatalogus.md` §10).

### Tests en testrun

**89 pytests groen** (was 64 aan het begin van deze sessie). Volledige suite: circa 7-13 s op deze
machine. Eén bekende, voorbestaande vlakheid: op Windows faalt af en toe willekeurig één van de
`test_run_*`-tests in `test_pijplijn.py` met een `PermissionError` bij het opruimen van een
`tmp_path`-map (een andere test elke keer, twee keer achter elkaar gedraaid met alleen groen
resultaat); dit is een bekend Windows/pytest-`tmp_path`-opruimprobleem (een bestandshandle die nog
heel even openstaat), geen regressie van deze sessie.

`--test --test-mb 50` gedraaid naar `data/test-na-fixes` (met `--docs-dir data/test-na-fixes-docs`,
NIET naar `docs/` zelf: de eerste poging schreef per ongeluk over het ECHTE `docs/data-quality.md`
van de volledige run heen, hersteld met `git checkout -- docs/data-quality.md` vóór er iets
gecommit werd). Resultaat: 2 woningen in `boiler_temp` (902.564 + 388.542 rijen) en 5 in
`thermostat_temp` (275.452 + 273.521 + 252.751 + 282.420 + 325.811 rijen), plus de kleine tabellen,
`dekking.parquet`, `docs/data-quality.md` (met de nieuwe DST-sectie) en `datapackage.json` (0
structuurfouten). Klaar in 9,0 s. `data/test-na-fixes(-docs)` blijft staan, buiten git, als
bewijsmateriaal (zelfde aanpak als `data/processed-test300`).
