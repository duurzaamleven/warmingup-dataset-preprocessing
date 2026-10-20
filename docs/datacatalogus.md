# Datacatalogus: WarmingUP-dataset "How Low Can You Go" (voorbewerkte uitvoer)

Dit document beschrijft de UITVOER van deze repo: de getypeerde Parquet-tabellen die
`warmingup_preprocessing` van de ruwe WarmingUP-meetdata maakt. Het is bedoeld om in een
datacatalogus te zetten naast (een verwijzing naar) de dataset zelf.

**Deze repo is niet de data-eigenaar en de ruwe data staat hier niet in.** Data-eigenaar is
Deltares; licentie, meldplicht en herkomst van het archief staan in
[`GEBRUIKSVOORWAARDEN.md`](../GEBRUIKSVOORWAARDEN.md). Dit document beschrijft alleen wat de
pijplijn ervan maakt.

Alle kolomnamen volgen de conventie
[`physiquant__unit`](https://github.com/energietransitie/physiquant__unit): eenheid na de dubbele
underscore, `_cum` alleen voor een meterstand op een moment (komt in deze dataset niet voor).

Types, rijaantallen en schema's in dit document zijn afgelezen uit de echte volledige-run-uitvoer
(de uitvoermap, `--uit`, van de eerste volledige run, 23-09-2026, zie VOORTGANG.md; met
`pyarrow.parquet.ParquetFile`, zonder de data zelf in te lezen), niet uit het ontwerp of het geheugen
overgenomen.

## 1. Wat deze set is

Voorbewerkte meetdata van het WarmingUP-project **Acceptabele Verlaagde Aanvoertemperatuur** (*How
Low Can You Go*), uitgevoerd door **Deltares** met installatiebedrijf Feenstra en de
warmtebedrijven Vattenfall, HVC, SVP, Eneco en ENnatuurlijk; MMIP-projectnummer TEUE819001.

- **Aantal woningen per tabel** (ze lopen uiteen, zie §8): 220 in `boiler_temp`, 223 in
  `thermostat_temp`, 243 in `mapping` (sleuteltabel), 212 in `resultaten`.
- **Gemeten periode.** Het eindrapport (Pothof, Vreeken & Van Meerkerk, *Field measurements on lower
  radiator temperatures in existing buildings*, Deltares, 13 september 2022, p. 11) noemt het
  installatievenster van de NIEUWE instrumentatie (de debietmeter en de twee temperatuursensoren op
  aanvoer/retour): "*hydraulically balanced and fitted with new instrumentation between January 2021
  and November 2021*" (vertraagd door de coronapandemie). Dat venster is WANNEER de meting per woning
  begon te lopen, niet de volledige gemeten periode zelf (README.md: "anderhalf tot drie jaar" per
  woning). De volledige spanwijdte is af te leiden uit de uitvoer zelf (`dekking.parquet`,
  minimum/maximum van `eerste_tijdstip`/`laatste_tijdstip` over alle woningen samen, volledige run
  23-09-2026): `boiler_temp` loopt van 2020-04-09 tot 2023-08-10, `thermostat_temp` van 2019-01-01
  tot 2023-05-01 (beide destijds afgelezen in UTC; zie §4 voor de weergavezone). Dit is de
  spanwijdte over alle woningen samen; individuele woningen dekken een kortere periode daarbinnen.
  **Tegenstrijdigheid met het rapport, hier vermeld in plaats van stilzwijgend genegeerd:** de
  vroegste `boiler_temp`-meting (2020-04-09) ligt vóór het door het rapport genoemde
  installatievenster (januari-november 2021); mogelijke verklaringen zijn een pilotwoning vóór de
  hoofdcampagne of een afwijkende logger-configuratie, maar dat is niet vastgesteld. De
  `thermostat_temp`-data (vanaf 2019-01-01) komt uit Feenstra's AL BESTAANDE monitoringsysteem, niet
  uit de nieuwe instrumentatie (rapport, p. 10: "*We rely on the Feenstra monitoring of the
  thermostat-temperature sensor*"), en loopt dus logischerwijs vóór het installatievenster van de
  nieuwe sensoren terug.
- **Data-eigenaar, licentie en meldplicht:** zie [`GEBRUIKSVOORWAARDEN.md`](../GEBRUIKSVOORWAARDEN.md).
  Kort samengevat: Deltares is eigenaar, er wordt geen licentienaam genoemd, en gebruik moet gemeld
  worden op <kite@rvo.nl> vóórdat er iets naar buiten gaat.
- **Hoe je de brondata zelf verkrijgt:** eveneens in GEBRUIKSVOORWAARDEN.md (de open URL, bestandsgrootte
  en sha256 van het archief).

## 2. In- en uitsluitcriteria van het oorspronkelijke project

Noch het archief zelf, noch de KITE-pagina (zie GEBRUIKSVOORWAARDEN.md) documenteert dit; het
eindrapport (Pothof et al., 2022) wel, en dat is de bron voor deze paragraaf.

**Steekproefopzet.** Het doel was een representatieve steekproef van de Nederlandse woningvoorraad,
minstens 200 woningen, ingedeeld naar woningtype en bouwperiode (p. 8): vrijstaand, hoekwoning,
tussenwoning en appartement; bouwperiode vóór 1974 (vóór de isolatie-verbetering na de oliecrisis),
1974-1991 (tot strengere isolatie-eisen en computerondersteund ontwerp) en na 1991. De indeling volgt
de RVO-classificatie (Netherlands Enterprise Agency, *Voorbeeldwoningen 2011, bestaande bouw*, 2011)
en de steekproeftrekking volgt de methode van Coenen (*Accelerating the Dutch energy transition*,
2019). Tabel 1 van het rapport (p. 9) geeft de streefverdeling (CBS-cijfers 2016) naast de
gerealiseerde verdeling van 220 woningen; de gerealiseerde verdeling wijkt af van de streefverdeling
door de uitsluitcriteria hieronder (oude appartementen zijn ondervertegenwoordigd, tussen- en
hoekwoningen uit 1974-1991 juist oververtegenwoordigd).

**Uitsluitcriteria, letterlijk (p. 9):** "*Dwellings were excluded from our sample if they had an
additional heat source, hydraulically unbalanced floor heating, or lacked a plug connection near the
gas boiler for our monitoring equipment.*" Dus: een woning met een extra warmtebron (bijvoorbeeld een
open haard), hydraulisch onbalans vloerverwarming, of zonder stopcontact bij de gasketel voor de
meetapparatuur, viel af. Vóór de meting werden de verwarmingssystemen bovendien hydraulisch
gebalanceerd met thermostatische radiatorkranen in elke kamer (p. 9), zodat alle open radiatoren
vergelijkbare aanvoer-/retourtemperaturen kregen; dat is dus zelf al een ingreep, geen neutrale
meting van de oorspronkelijke situatie.

**Wat wél met zekerheid uit de data zelf volgt** (kolomnamen en de aanwezigheid van een
geïnstalleerd-radiatorvermogen in `resultaten.parquet`, zie §5.5): het gaat om **gasketelwoningen**
met een cv-ketel, een thermostaat en radiatoren; huizen zonder gasketel of zonder radiatorafgifte
horen per definitie niet in deze dataset.

**Representativiteit, met een voorbehoud van het rapport zelf.** Het rapport (p. 17-18, Tabel 5/6)
vergelijkt het specifieke gasverbruik voor ruimteverwarming van de steekproef met CBS- en
regionale cijfers en concludeert dat de steekproef **12% tot bijna 100% hoger** specifiek
gasverbruik heeft dan gemiddelde Nederlandse woningen, vooral in de nieuwste bouwperiode
(appartementen en woningen in de steekproef zijn daar relatief oud, gemiddelde bouwjaar 2000
respectievelijk 1998, terwijl de bouwperiode "na 1991" tot heden loopt); 2021 was bovendien een
iets kouder jaar (circa 5% meer graaddagen dan het 30-jaargemiddelde). De steekproef is dus gericht
op de Nederlandse woningvoorraad, maar niet zonder meer een neutrale afspiegeling ervan.

**Wat niet is vastgesteld:** individuele opt-out-gronden, leeftijd/samenstelling van de bewoners, en
de exacte werving (het rapport noemt alleen dat installatiebedrijf Feenstra, dat destijds circa
20.000 Intergas-gasketels monitorde, klanten zocht, en dat dat "*more difficult than anticipated*"
was door de coronapandemie, p. 25). Wie dat nodig heeft, moet bij Deltares/KITE navragen.

## 3. Meetopstelling

Uit README.md, de kolomnamen van het archief zelf (zie §5) en, voor de onderbouwing en details, het
eindrapport (Pothof et al., 2022, p. 9-11):

- **Eén pulsdebietmeter en twee temperatuursensoren** per woning, gemonteerd op de aanvoer- en
  retourleiding NAAR DE RADIATOREN, dicht bij de gasketel, bewust zo geplaatst dat de meting het
  tapwatercircuit niet raakt (p. 10: "*near the gas boiler to ensure that these measurements do not
  interfere with the domestic hot water preparation*"). Dit levert `Flow (l/h)` en
  `Boiler Water Supply/Return Temperature (°C)` in `boiler_temp` (§5.1).
- **Meetfrequentie van de ruwe data** (rapport, Tabel 2, p. 10, kolom "Frequency measure"; dit is de
  frequentie van de RUWE meting, niet van het verwerkte analysedataset in het rapport zelf, dat naar
  10-minuutgemiddelden downsamplet -- deze repo levert de ruwe, niet-gedownsamplete data door):
  debiet als pulstelling per liter (hier per minuut opgeteld/weergegeven), aanvoer-/retourtemperatuur
  per minuut, binnentemperatuur gebeurtenisgestuurd ("non-equidistant, based on a minimum deviation
  with an unknown minimum interval", p. 10).
- **Vóór de meetperiode: hydraulische balancering.** De installateur balanceerde elk verwarmingssysteem
  met thermostatische radiatorkranen in elke kamer, zodat alle open radiatoren vergelijkbare
  aanvoer-/retourtemperaturen kregen (p. 9); de meting start dus niet bij de oorspronkelijke,
  ongebalanceerde installatie.
- **Data-overdracht**: dagelijks via een GSM-verbinding (p. 10).
- **Ketellogging** (`boiler-24h-stats.csv`/`etmaal`), dagelijks samengevat, AFKOMSTIG UIT het
  bestaande Feenstra-monitoringsysteem (niet de nieuwe instrumentatie): gasverbruik apart voor
  ruimteverwarming en tapwater, brandertijd apart voor ruimteverwarming en tapwater, en
  cv-waterdruk (min/gemiddeld/max per dag). Het rapport waarschuwt expliciet dat het gasverbruik
  intern door de ketel wordt afgeleid uit de gemeten ventilatorfrequentie, en dat dit bij veel
  starts/stops minder nauwkeurig kan zijn (p. 10).
- **Thermostaatlogging** (`thermostat_temp`), eveneens uit het bestaande Feenstra-systeem,
  gebeurtenisgestuurd: gewenste (setpoint) en gemeten binnentemperatuur, van de thermostaat in de
  hoofdwoonruimte (p. 10).
- **Weerdata.** Het rapport gebruikt uurlijkse temperatuur- en zoninstralingsdata van het
  KNMI-weerstation **Deelen**, "*geographically closest to most studied buildings*" (p. 11),
  gedownsampled naar 10 minuten met lineaire interpolatie voor de analyse. **Deze weerdata is GEEN
  onderdeel van het archief dat deze repo verwerkt**; het wordt hier genoemd omdat het mede de
  keuze voor Europe/Amsterdam als weergavezone onderbouwt (§4).
- Per woning is bovendien het **opgenomen (geïnstalleerde) radiatorvermogen** bekend, opgenomen in
  de resultatentabel (§5.5), afgeleid uit radiatortype en -afmetingen die tijdens een fysiek
  huisbezoek zijn opgenomen (p. 15).

Sensormerk, montagehoogte, kalibratie en meetonzekerheid van de individuele sensoren zijn niet in het
eindrapport gespecificeerd (alleen de meetmethode: de "energy meter method"/geïntegreerde
co-heating-test van Farmer et al., 2016, uitgebreid met de aanbevelingen van Bauwens & Roels, 2014,
voor omgevingsdata, p. 9) en dus **niet vastgesteld** in wat deze repo weet.

## 4. Tijdconventies

- `boiler_temp` en `thermostat_temp`: tijdstip **tz-aware, weergavezone Europe/Amsterdam**
  (`timestamp[ns, tz=Europe/Amsterdam]`). De bron draagt UTC (`Z`-gemarkeerde ISO-8601-tijdstempels);
  deze pijplijn parseert dat eerst naar UTC (`tijd.naar_utc_tijdstip`, nog steeds de interne
  rekenbasis: alle sentinels/vlaggen/dekking werken op UTC) en zet het pas als allerlaatste stap vóór
  het schrijven om naar de weergavezone (`tijd.naar_weergave_tijdzone`, `tz_convert`, geen
  `tz_localize`): **het instant verandert niet, alleen de tz-metadata.**
  Onderbouwing voor Europe/Amsterdam als weergavezone (aanvullende eis van de opdrachtgever,
  23-09-2026, analoog aan de Installatiemonitor-preprocessing): de bron labelt de etmaaltabel zelf al
  als `Day (Europe/Amsterdam)`; de steekproef is gericht op de Nederlandse woningvoorraad (Pothof et
  al., 2022, p. 7-8, zie §2); het KNMI-weerstation dat het eindrapport gebruikt, Deelen, ligt
  "*geographically closest to most studied buildings*" (idem, p. 11); en de vijf deelnemende
  warmtebedrijven (Vattenfall, HVC, SVP, Eneco, ENnatuurlijk) leveren allemaal in Europees Nederland
  (idem, p. 2). Vóór "2026-09-23-derde-opzet" (zie §7) stond deze kolom in UTC.
- `etmaal`: de datumkolom (`datum__str`) blijft een **lokale kalenderdag** (`Europe/Amsterdam`), als
  tekst (`YYYY-MM-DD`), NIET omgerekend naar UTC; dat zou de dag zelf laten verschuiven. Wie hem
  tegen de minuutdata wil leggen, gebruikt `tijd.etmaalgrens_utc`, dat het juiste venster van 23 of
  25 uur rond een zomertijdovergang teruggeeft; een vergelijking met een Europe/Amsterdam-tijdstempel
  werkt daar automatisch overheen, want tijdzonevergelijking in pandas gaat altijd via het instant.
- **Open-intervalaanname bij het debiet.** Of een minuutwaarde in `debiet__dm3_s_1` het voorafgaande
  interval dekt (eindgelabeld) of het volgende (begingelabeld), is nergens door Deltares
  gedocumenteerd. `tijd.AANNAME_DEBIET_INTERVAL_LABEL` legt dit vast als de expliciete waarde
  `"onbekend"`, met naam, in plaats van er stilzwijgend een aan te nemen. Deze pijplijn doet zelf
  geen resampling of interval-integratie, dus de aanname raakt hier geen berekening.
- **Toets-uitkomst over alle woningen** (`intervalsemantiek.py`, gedraaid op 03-10-2026 over 219 woningen
  met samen 3.959.734 pompstarts; 3.362.398 "zuivere" starts met een aaneengesloten venster en een
  temperatuursprong van minstens 0,5 °C; WU175 heeft geen betrouwbaar debiet en dus geen starts):
  de temperatuursprong ligt bij 7,3% van de zuivere starts vóór de debietstart, bij 39,6% in dezelfde
  minuut, bij 32,6% een minuut erna en bij 20,6% twee of meer minuten erna (mediaan 1 minuut, p25 0,
  p75 1). Per woning is de mediaan 0 bij 94 woningen, 1 bij 123 en 2 bij 2, zonder samenhang met het
  loggertype. Dit past iets beter bij een eindgelabeld dan bij een begingelabeld debiet, maar geen van
  beide conventies past zuiver en op minuutresolutie is labeling niet te scheiden van de
  reactietijd van de sensor. `AANNAME_DEBIET_INTERVAL_LABEL` blijft daarom op `"onbekend"`; wie
  integreert, rekent de keuze het best als gevoeligheid door. Verdeling en methode: VOORTGANG.md.

### 4.1 Bevinding: zomertijdgaten in `boiler_temp` rond de oktoberwissel

Bevinding van de opdrachtgever, 23-09-2026 (methode hieronder samengevat; getallen ook geteld in
`docs/data-quality.md`, zie `kwaliteitsrapport._tel_dst_oktobergaten`). **Er is geen correctie in de
data aangebracht**; dit is een constatering, geen vaststaande verklaring, en het ontbrekende uur
wordt niet teruggezet.

- **Rond de oktoberwissels 2021-10-31 en 2022-10-30** (overgang naar wintertijd) ontbreekt bij 125
  van de 206 respectievelijk 126 van de 212 woningen met data in dat venster precies het TWEEDE uur
  van het dubbelzinnige lokale tijdvenster (02:00-02:59 CET, dus 01:00-01:59 UTC). De laatste meting
  vóór het gat is 02:59 CEST (00:59 UTC), de eerste erna 03:00 CET (02:00 UTC); in een steekproef van
  52 woningen-met-gat gold dit exact bij 50. **Let op, twee tellingen die niet gelijk zijn:** het
  kwaliteitsrapport (`data-quality.md`, geteld uit de volledige uitvoer met een venster van 00:30 tot
  03:30 UTC en een gat van minstens 50 minuten) komt op 117 van de 206 woningen (2021) en 117 van de
  212 (2022); de 125 en 126 hierboven zijn de telling van de opdrachtgever. Het verschil in methode
  is niet uitgezocht; de aantallen woningen met data (206 en 212) komen wel overeen.
- **Getoetst welke doorgang van het dubbelzinnige uur bewaard is gebleven**: de temperatuursprong van
  01:59 naar 02:00 CEST (de EERSTE doorgang, wél aanwezig) is normaal (mediaan 0,18 °C tegenover een
  normale 0,13 °C per minuut, 0% grote sprongen), terwijl de sprong over het gat heen (02:59 CEST ->
  03:00 CET) groter is (mediaan 0,30 °C, 24% grote sprongen), zoals bij een echt ontbrekend uur
  verwacht mag worden. Er lijkt dus niets fouts te zijn toegewezen; er is alleen een uur data
  verloren. Een verklaring die hierbij past: de loggers registreerden lokale tijd, en bij het
  omzetten naar UTC is het dubbelzinnige uur als zomertijd gelezen, waarna de tweede doorgang
  (wintertijd) verdween.
- **Rond de maartwissels 2021-2023**: geen gat en geen verhoogd aantal dubbele tijdstempels (circa 1
  per woning, gelijk aan het normale niveau) -- een niet-bestaand lokaal uur geeft bij UTC-opslag ook
  geen gat, dus dit klopt met de verwachting.
- **`thermostat_temp`**: geen verhoging van het aantal dubbele tijdstempels rond de wissels ten
  opzichte van dezelfde uren een week eerder (bijvoorbeeld 355 tegenover 460 in maart 2022); gaten
  zijn hier niet geteld, want deze tabel is gebeurtenisgestuurd (§6).
- **De 253.721 dubbele tijdstempels in `boiler_temp` (§6) komen NIET van de zomertijd**: slechts 729
  liggen binnen ±3 uur van een wisseling; ze pieken dagelijks rond 01-04 en 12-14 UTC, wat op een
  upload- of synchronisatieritme van de loggers kan wijzen, maar dat is niet vastgesteld.

## 5. Uitvoertabellen

Alle tabellen zijn Parquet, zstd-gecomprimeerd. Geen enkele gevlagde rij wordt verwijderd: elke
`q_flag_*__bool`-kolom is een boolean naast de gewone waarde, behalve de twee uitzonderingen die
expliciet worden benoemd (de druksentinel en de debiet-sentinel gaan in hun EIGEN kolom wél naar
`NaN`, zie §5.1 en §5.3).

### 5.1 `boiler_temp/home_id=<id>.parquet`

Eén bestand per woning (platte map, geen submappen), zstd. **220 bestanden, 243.041.542 rijen totaal**
(geteld uit de echte Parquet-metadata, volledige run 23-09-2026), minuutdata.

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `home_id__str` | string | | | pseudoniem van de woning (`WU0`..`WU242`) | `House` | |
| `tijdstip` | timestamp(ns, UTC) | | 1 minuut | tijdstip van de meting, UTC | `Time` | 253.721 dubbele tijdstempels in de volledige set, zie §6; NIET ontdubbeld |
| `temp_aanvoer__degC` | float32 | °C | 1 minuut | aanvoertemperatuur naar de radiatoren | `Boiler Water Supply Temperature (°C)` | tekstsentinel `"x"` in de bron wordt hier `NaN` (zie `q_flag_temp_aanvoer_ontbrekend__bool`) |
| `temp_retour__degC` | float32 | °C | 1 minuut | retourtemperatuur van de radiatoren | `Boiler Water Return Temperature (°C)` | |
| `debiet_ruw__l_h` | float64 | l/h | 1 minuut | rauw debiet, ongewijzigd inclusief sentinel | `Flow (l/h)` | sentinel `4294967295` (2³²−1, "onbekend") blijft hier zichtbaar als getal |
| `debiet__dm3_s_1` | float32 | dm³/s | 1 minuut | debiet omgerekend (`debiet_ruw__l_h / 3600`) | afgeleid van `Flow (l/h)` | sentinel wordt hier wél `NaN` (uitzondering op "vlaggen, niet verwijderen") |
| `q_afgifte__W` | float32 | W | 1 minuut | afgeleid afgiftevermogen, zie formule onder de tabel | afgeleid | `NaN` zodra één van de drie invoerwaarden onbetrouwbaar is (zie hieronder) |
| `q_flag_debiet_sentinel__bool` | bool | | | True wanneer `debiet_ruw__l_h == 4294967295` (2³²−1) | | |
| `q_flag_debiet_bovengrens__bool` | bool | | | True wanneer `debiet_ruw__l_h > 5000` l/h én niet de sentinel | | grens `FLOW_BOVENGRENS__l_h`, een orde-van-grootte-keuze, geen meting (§8) |
| `q_flag_temp_aanvoer_ontbrekend__bool` | bool | | | True wanneer `temp_aanvoer__degC` ontbreekt (`NaN`, inclusief de tekst `"x"` in de bron) | | apart van "buiten bereik" |
| `q_flag_temp_retour_ontbrekend__bool` | bool | | | True wanneer `temp_retour__degC` ontbreekt (`NaN`) | | |
| `q_flag_temp_aanvoer_bereik__bool` | bool | | | True wanneer `temp_aanvoer__degC` een GETAL is buiten [0, 100] °C | | `NaN` telt hier niet mee, dat is de vorige vlag |
| `q_flag_temp_retour_bereik__bool` | bool | | | True wanneer `temp_retour__degC` een GETAL is buiten [0, 100] °C | | |

**Formules.**

```
debiet__dm3_s_1 = debiet_ruw__l_h / 3600          (na sentinelvervanging naar NaN)
q_afgifte__W    = (debiet__dm3_s_1 / 1000) * 998,2 * 4186 * (temp_aanvoer__degC - temp_retour__degC)
```

met ρ = 998,2 kg/m³ en cₚ = 4186 J/(kg·K), vaste waarden bij circa 20 °C (geen
temperatuurafhankelijke correctie, zie §8). `q_afgifte__W` wordt `NaN` zodra minstens één van
`q_flag_debiet_sentinel__bool`, `q_flag_debiet_bovengrens__bool`,
`q_flag_temp_aanvoer_ontbrekend__bool`, `q_flag_temp_retour_ontbrekend__bool`,
`q_flag_temp_aanvoer_bereik__bool` of `q_flag_temp_retour_bereik__bool` True is. **Let op:**
`temp_retour__degC > temp_aanvoer__degC` is bewust GEEN vlag; bij een stilstaande pomp en een
afkoelende ketel kan de retour tijdelijk boven de aanvoer liggen, wat een correct negatief
`q_afgifte__W` oplevert.

### 5.2 `thermostat_temp/home_id=<id>.parquet`

Eén bestand per woning, zstd. **223 bestanden, 69.166.957 rijen totaal**, gebeurtenisgestuurd (niet
equidistant): een ontbrekende minuut betekent hier "niets veranderd", niet "geen meting".

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `home_id__str` | string | | | pseudoniem van de woning | `House` | |
| `tijdstip` | timestamp(ns, UTC) | | gebeurtenisgestuurd | tijdstip van de gebeurtenis, UTC | `Time` | mediaan gemiddeld interval 255 s (§6); ook hier dubbele tijdstempels voorkomen (§6), NIET ontdubbeld |
| `temp_setpoint__degC` | float32 | °C | gebeurtenisgestuurd | gewenste (ingestelde) temperatuur | `Thermostat Desired Temperature (°C)` | |
| `temp_binnen__degC` | float32 | °C | gebeurtenisgestuurd | gemeten binnentemperatuur | `Thermostat Measured Temperature (°C)` | |
| `q_flag_temp_setpoint_bereik__bool` | bool | | | True wanneer `temp_setpoint__degC` een GETAL is buiten [5, 35] °C | | geen aparte "ontbrekend"-vlag voor deze tabel |
| `q_flag_temp_binnen_bereik__bool` | bool | | | True wanneer `temp_binnen__degC` een GETAL is buiten [0, 40] °C | | |

Geen afgeleide kolommen in deze tabel.

### 5.3 `etmaal.parquet`

Eén tabel, alle woningen samen (niet per woning opgesplitst: ontwerpkeuze, zie
`ontwerp-preprocessing.md` §2). **199.776 rijen** (volledig gelezen, geverifieerd via
`pq.ParquetFile(...).metadata.num_rows`).

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `home_id__str` | string | | | pseudoniem van de woning | `House` | |
| `datum__str` | string | | etmaal | lokale kalenderdag, `Europe/Amsterdam`, ISO-8601-tekst | `Day (Europe/Amsterdam)` | GEEN `timestamp`, bewust niet naar UTC omgerekend (§4) |
| `g_tapwater__m3` | float32 | m³ | etmaal | gasverbruik tapwater | `Gas Usage Domestic Hot Water (DHW) (m³)` | letterlijke bronkolomnaam, incl. "(DHW)" |
| `g_ruimteverwarming__m3` | float32 | m³ | etmaal | gasverbruik ruimteverwarming | `Gas Usage Central Heating (CH) (m³)` | |
| `t_brander_tapwater__h` | float32 | h | etmaal | brandertijd tapwater | `Heater Active Duration DWH (hours)` | **letterlijke tikfout in de bron: `DWH`, niet `DHW`** |
| `t_brander_verwarming__h` | float32 | h | etmaal | brandertijd ruimteverwarming | `Heater Active Duration CH (hours)` | |
| `p_cv_min__Pa` | float32 | Pa | etmaal (dagminimum) | minimale cv-waterdruk | `Water Pressure CH Min (Bar -1=unknown)` | intern eerst `__bar`, pas ná sentinelvervanging naar Pa (× 1e5) |
| `p_cv_gem__Pa` | float32 | Pa | etmaal (daggemiddelde) | gemiddelde cv-waterdruk | `Water Pressure CH Avg (Bar -1=unknown)` | |
| `p_cv_max__Pa` | float32 | Pa | etmaal (dagmaximum) | maximale cv-waterdruk | `Water Pressure CH Max (Bar -1=unknown)` | |
| `q_flag_gas_ruimteverwarming_bereik__bool` | bool | | | True wanneer `g_ruimteverwarming__m3` een GETAL is buiten [0, 50] m³ | | |
| `q_flag_gas_tapwater_bereik__bool` | bool | | | True wanneer `g_tapwater__m3` een GETAL is buiten [0, 10] m³ | | |
| `q_flag_brander_verwarming_bereik__bool` | bool | | | True wanneer `t_brander_verwarming__h` een GETAL is buiten [0, 24] h | | |
| `q_flag_brander_tapwater_bereik__bool` | bool | | | True wanneer `t_brander_tapwater__h` een GETAL is buiten [0, 24] h | | |
| `q_flag_druk_min_onbekend__bool` | bool | | | True wanneer de bronwaarde van `p_cv_min` gelijk was aan `-1` bar | | de kolomnaam documenteert dit zelf als "unknown" |
| `q_flag_druk_gem_onbekend__bool` | bool | | | True wanneer de bronwaarde van `p_cv_gem` gelijk was aan `-1` bar | | |
| `q_flag_druk_max_onbekend__bool` | bool | | | True wanneer de bronwaarde van `p_cv_max` gelijk was aan `-1` bar | | |

**Formule en uitzondering op "vlaggen, niet verwijderen":** de druksentinel `-1` bar wordt, ANDERS
dan de gas- en branderuurkolommen, WEL naar `NaN` vervangen (in de gewone kolom, niet alleen
gevlagd), vóórdat de omrekening naar Pa plaatsvindt (`p_cv_*__Pa = p_cv_*__bar × 1e5`); zo blijft
`NaN` gewoon `NaN` in plaats van een absurde `-100.000 Pa`.

### 5.4 `mapping.parquet`

Eén tabel, sleuteltabel. **243 rijen** (volledig gelezen).

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `home_id__str` | string | | eenmalig | pseudoniem van de woning | `house` | |
| `logger_id__str` | string | | eenmalig | logger-identificatie | `logger_id` | |
| `serial_no__str` | string | | eenmalig | serienummer van de logger | `serial_no` | |
| `heater_id__str` | string | | eenmalig | ketel-identificatie | `heater_id` | |

Geen kwaliteitsvlaggen, geen afgeleide kolommen: dit is een letterlijke, hernoemde kopie. Zie §8
voor het verschil in aantal woningen ten opzichte van `boiler_temp`/`thermostat_temp`.

### 5.5 `resultaten.parquet`

Eén tabel, per woning eenmalig: de 2R2C-modelparameters, ontwerp- en geïnstalleerd vermogen,
woningkenmerken. **212 rijen** (volledig gelezen).

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `resultaat_volgnummer__int` | int64 | | eenmalig | oorspronkelijke rijvolgorde in de bron-xlsx | `Order` | geen fysische grootheid, bewust bewaard als herkomst van de volgorde (§8) |
| `home_id__str` | string | | eenmalig | pseudoniem van de woning | `woning_id` | |
| `logger_id__str` | string | | eenmalig | logger-identificatie | `logger_id` | vóór contractversie "2026-09-23-tweede-opzet" was dit `int64` ondanks de `__str`-naam (§8); expliciet gecast met `kolommen.naar_string_zonder_punt0` |
| `serial_no__str` | string | | eenmalig | serienummer van de logger | `serial_no` | |
| `model_training_fout__onbekend` | double | **onbekend** | eenmalig | modelfout, trainingsdeel | `model_training_rms` | eenheid bewust `__onbekend`, niet gedocumenteerd door Deltares (§8) |
| `model_validatie_fout__onbekend` | double | **onbekend** | eenmalig | modelfout, validatiedeel | `model_validation_rms` | |
| `model_training_bias__onbekend` | double | **onbekend** | eenmalig | modelbias, trainingsdeel | `model_training_mean_bias_error` | |
| `model_validatie_bias__onbekend` | double | **onbekend** | eenmalig | modelbias, validatiedeel | `model_validation_mean_bias_error` | |
| `p_ontwerp__W` | double | W | eenmalig | ontwerp-warmtevraag bij ontwerpcondities (`steady_state_heat_supply, Q_d`) | `steady_state_heat_supply, Q_d [W]` | zie de 18-uursaanname hieronder |
| `c_binnen__J_K_1` | double | J/K (**zie discrepantie hieronder**) | eenmalig | thermische massa binnenschil (2R2C) | `C_i [J/C]` | |
| `r_binnen_schil__K_W_1` | double | K/W | eenmalig | warmteweerstand binnen-schil (2R2C) | `R_ie [C/W]` | |
| `a_raam_effectief__m2` | double | m² | eenmalig | effectief raamoppervlak (zoninval) | `A_w [m2]` | |
| `c_schil__J_K_1` | double | J/K (**zie discrepantie hieronder**) | eenmalig | thermische massa schil (2R2C) | `C_e [J/C]` | |
| `r_schil_buiten__K_W_1` | double | K/W | eenmalig | warmteweerstand schil-buiten (2R2C) | `R_ea [C/W]` | |
| `temp_aanvoer_min__degC` | double | °C | eenmalig | gereduceerde ontwerp-aanvoertemperatuur (fit) | `sv_supply_wa_60T` | vermoedelijk `Ts,d` uit het eindrapport, zie hieronder |
| `temp_retour_min__degC` | double | °C | eenmalig | bijbehorende ontwerp-retourtemperatuur (fit) | `sv_return_wa_60T` | vermoedelijk `Tr,d`, zie hieronder |
| `woningtype__cat` | string | | eenmalig | woningtype (categorie) | `Woning_type` | waarden o.a. hoekwoning, tussenwoning, appartement, twee-onder-een-kap, vrijstaand |
| `bouwjaar_klasse__cat` | string | | eenmalig | bouwjaarklasse | `bouwjaar_bins` | |
| `bouwjaar_klasse_eindrapport__cat` | string | | eenmalig | bouwjaarklasse zoals in het eindrapport | `BJ_Cat` | grovere indeling dan `bouwjaar_klasse__cat` |
| `oppervlak_klasse__cat` | string | | eenmalig | gebruiksoppervlakteklasse | `Gebruiksoppervlak_bin` | |
| `g_jaarverbruik_indicatief__m3` | double | m³ | eenmalig | indicatief jaarlijks gasverbruik | `indicatief_gas [m3]` | |
| `p_afgifte_geinstalleerd__W` | double | W | eenmalig | geïnstalleerd radiatorvermogen | `Total installed power, Q_a (kW)` | bron in kW, × 1000 omgerekend naar W |
| `overdimensionering__frac` | double | - | eenmalig | verhouding ontwerp- op geïnstalleerd vermogen | `dimless heat power, Q_d/Q_a [-]` | `Q_d / Q_a` |

Geen kwaliteitsvlaggen: deze tabel is een letterlijke, hernoemde kopie van de resultaten-xlsx,
zonder eigen plausibiliteitscontrole (ontwerp-preprocessing.md §10). De brontabel bevatte ook een
kolom `blank col1`, in de bron volledig leeg (alle 212 rijen `NaN`, geverifieerd); die wordt
weggelaten in plaats van vertaald.

**Betekenis van de modelkolommen, volgens het eindrapport (Pothof et al., 2022).** Deze tabel komt
uit dezelfde modellering die het eindrapport beschrijft; onderstaande toelichting is bedoeld om de
kolomnamen te koppelen aan wat het rapport meet en rekent, niet als een claim dat de exacte
getallen in deze xlsx-tabel identiek zijn aan wat in het rapport gepubliceerd is.

- **2R2C-model** (`c_binnen__J_K_1`, `r_binnen_schil__K_W_1`, `a_raam_effectief__m2`,
  `c_schil__J_K_1`, `r_schil_buiten__K_W_1`): een grijze-doos-gebouwmodel met twee thermische
  massa's (binnenschil `Ci`, schil `Ce`) en twee weerstanden (binnen-schil `Rie`, schil-buiten
  `Rea`), gekalibreerd per woning op de gemeten binnentemperatuur, met een effectief raamoppervlak
  `Aw` voor zoninval (rapport §"Modelling approach", p. 11-12, vergelijking 1-2; naar Bacher &
  Madsen, 2011). Gekalibreerd op de twee koudste 10-daagse periodes uit de meetdata, gevalideerd op
  een derde (p. 12). Het rapport meldt dat de kalibratie voor 187 van de 220 woningen slaagde (p.
  18); deze tabel heeft **212 rijen**, een aantal dat noch met 220 (de steekproef) noch met 187 (de
  geslaagde kalibraties) overeenkomt. Niet verklaard in wat deze repo weet; genoemd in §8.
- **`p_ontwerp__W` (Q_d), de 18-uursaanname.** Ontwerpcondities zijn een daggemiddelde
  buitentemperatuur van -10 °C zonder zoninstraling en een binnentemperatuur van +20 °C (p. 13). De
  ontwerp-warmtevraag zelf volgt rechtstreeks uit het gekalibreerde RC-model (een daggemiddeld
  vermogen); het rapport maakt vervolgens een EXPLICIETE, benoemde aanname dat dit vermogen in 18 vol
  belaste uren op de ontwerpdag geleverd kan worden (in plaats van 24), "*to account for modelling
  uncertainties and possible domestic hot water (DHW) supply to a daily buffer from the same
  installation*" (p. 13). `p_ontwerp__W` is dus niet het daggemiddelde vermogen zelf, maar het
  vermogen bij die 18-uursaanname.
- **`p_afgifte_geinstalleerd__W` (Q_a), de 75/65/20-conditie.** Het geïnstalleerde
  radiatorvermogen is berekend bij de Nederlandse standaard-ontwerpconditie aanvoer/retour/binnen =
  75/65/20 °C (p. 15), uit radiatortype en -afmetingen die tijdens een huisbezoek zijn opgenomen, met
  vaste correlaties per radiatortype (paneel 10/11/20/21/22/33, "Design", kolom; convectoren op 0
  W/m² gezet omdat ze nauwelijks voorkwamen in de steekproef, p. 15-16).
- **`overdimensionering__frac` (η = Q_d/Q_a)**: de verhouding tussen de ontwerp-warmtevraag (bij de
  18-uursaanname) en het geïnstalleerde vermogen (bij 75/65/20); het rapport noemt dit de
  "dimensionless design heat output", de inverse van de oversizingsfactor (p. 16, vergelijking 8), en
  concludeert dat dit getal beter correleert met de haalbare gereduceerde aanvoertemperatuur dan
  woningtype of bouwjaar (p. 22).
- **`temp_aanvoer_min__degC`/`temp_retour_min__degC` (vermoedelijk `sv_supply_wa_60T`/
  `sv_return_wa_60T` = `Ts,d`/`Tr,d`).** Dit is een AANNAME van deze catalogus, geen letterlijke
  bevestiging uit het rapport (de variabelenamen `sv_supply_wa_60T`/`sv_return_wa_60T` komen niet zo
  in de tekst van het rapport voor; het lijkt op Deltares' eigen interne analysecode-naamgeving,
  "sv" mogelijk voor "supply value", "wa" voor "weighted average", "60T" voor de 60-minuten-
  (uurlijkse) aggregatie). De gereduceerde ontwerp-aanvoer-/retourtemperatuur wordt bepaald uit het
  25e-percentiel van de UURLIJKSE, debiet-gewogen gemiddelde radiator-ΔT bij het ontwerpvermogen
  ("*Each data point in Figure 5 shows an hourly average value of heat output ... and flow-weighted
  average radiator ΔTLMTD*", p. 14), waarna `Ts,d`/`Tr,d` volgt uit vergelijking 5-6 (p. 15). De
  naamgeving (uurlijks gewogen gemiddelde) past bij die berekening; dit is dus een aannemelijke, geen
  zekere koppeling.
- **`model_*_fout__onbekend`/`model_*_bias__onbekend`**: blijven bewust `__onbekend` (CLAUDE.md-regel
  5): het rapport beschrijft wel de kalibratie-/validatiesplitsing (twee 10-daagse periodes trainen,
  één valideren, p. 12) maar noemt geen expliciete eenheid voor deze twee foutmaten in de xlsx-tabel
  zelf; aannemen dat het dezelfde eenheid is als de gemodelleerde binnentemperatuur (°C) is
  aannemelijk maar niet bevestigd, dus wordt het niet als feit gepresenteerd.

**Tegenstrijdigheid tussen rapport en data, hier expliciet vermeld.** De nomenclatuurtabel van het
rapport (p. 3) geeft `Ci`/`Ce` de eenheid **Wh/°C**; de xlsx-kolomkoppen van de brondata zelf zeggen
letterlijk **J/C** (dus J/K), een factor 3600 verschil (1 Wh/K = 3600 J/K). Deze repo neemt de
LETTERLIJKE brontabelkop over (`c_binnen__J_K_1`/`c_schil__J_K_1`, eenheid J/K), zoals bij elke
andere kolom; welke conventie de daadwerkelijk opgeslagen GETALLEN volgen, is met de middelen van
deze repo niet te verifiëren. Wie hiermee rekent, moet dit zelf controleren (bijvoorbeeld door de
grootte-orde van een paar `Ci`-waarden te vergelijken met een fysisch plausibele thermische massa
voor een woninginterieur).

### 5.6 `info_metadata.parquet`

Eén tabel: het `info`-blad van de resultatentabel, als tekstuele herkomst, niet geïnterpreteerd.
**17 rijen** (volledig gelezen).

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `regel__int` | int64 | | | regelnummer in het oorspronkelijke `info`-blad | (rijindex van het `info`-blad) | |
| `tekst__str` | string | | | tekst van de regel, celwaarden samengevoegd met `" \| "` | (celwaarden van het `info`-blad) | geen vertaling, geen interpretatie; dit is herkomst, geen meetgrootheid |

### 5.7 `dekking.parquet`

Eén tabel: dekkingsstatistiek per woning per bron. **443 rijen** (220 `boiler_temp` + 223
`thermostat_temp`, volledig gelezen).

| kolom | type | eenheid | interval | beschrijving | bronkolom | opmerking |
|---|---|---|---|---|---|---|
| `home_id__str` | string | | | pseudoniem van de woning | (afgeleid van de bestandsnaam) | |
| `bron__cat` | string | | | `"boiler_temp"` of `"thermostat_temp"` | | |
| `rijen__int` | int64 | | | aantal rijen van deze woning in deze bron | | |
| `eerste_tijdstip` | timestamp(ns, UTC) | | | eerste tijdstip in het venster van deze woning | | |
| `laatste_tijdstip` | timestamp(ns, UTC) | | | laatste tijdstip in het venster van deze woning | | |
| `dubbele_tijdstippen__int` | int64 | | | aantal dubbele tijdstempels binnen deze woning/bron | | zie §6; telt alleen, verwijdert niets |
| `dekking_fractie__frac` | double | - | | alleen voor `boiler_temp`: `rijen / minuten-in-venster` | | `NaN` voor `thermostat_temp` |
| `gemiddeld_interval__s` | double | s | | alleen voor `thermostat_temp`: gemiddeld interval tussen opeenvolgende metingen | | `NaN` voor `boiler_temp` |

**Formules.**

```
dekking_fractie__frac (boiler_temp)        = rijen / ((laatste_tijdstip - eerste_tijdstip) in minuten + 1)
gemiddeld_interval__s (thermostat_temp)    = (laatste_tijdstip - eerste_tijdstip) in seconden / (rijen - 1)
```

Voor `thermostat_temp` is er bewust GEEN dekkingsfractie tegen een minuutraster: de metingen zijn
gebeurtenisgestuurd, dus een "gat" betekent hier "niets veranderd", niet "geen meting".

## 6. Kwaliteit, en de dubbele tijdstempels

Cijfers uit [`data-quality.md`](data-quality.md) (door de pijplijn zelf geschreven, volledige run
23-09-2026, na de migratie naar `uitvoer_contract_versie` `2026-09-23-derde-opzet`):

**`boiler_temp`** (243.041.542 rijen): `q_flag_debiet_sentinel__bool` 2.565× (0,001%),
`q_flag_debiet_bovengrens__bool` 149.602× (0,062%), `q_flag_temp_aanvoer_ontbrekend__bool`
1.622.716× (0,668%, vrijwel allemaal de tekstsentinel `"x"`), `q_flag_temp_retour_ontbrekend__bool`
881×, `q_flag_temp_aanvoer_bereik__bool` 90.662× (0,037%), `q_flag_temp_retour_bereik__bool` 2.442×.
Dekking: 220 woningen, mediane dekkingsfractie 0,996 (p10 0,962).

**`thermostat_temp`** (69.166.957 rijen): `q_flag_temp_setpoint_bereik__bool` 660×,
`q_flag_temp_binnen_bereik__bool` 347×. Dekking: 223 woningen, mediaan gemiddeld interval 255 s.

**`etmaal`** (199.776 rijen): de vier bereikvlaggen elk 150 à 260× (0,08 à 0,13%), de drie
druk-onbekend-vlaggen elk 2× (twee dagen met een sentinelwaarde).

**De dubbele tijdstempels.** `q_flag_tijdstip_dubbel__bool` in `boiler_temp` en `thermostat_temp` is
True vanaf de tweede keer dat een tijdstip voor een woning voorkomt (`sentinels.flag_tijdstip_dubbel`,
sinds contractversie `2026-09-23-tweede-opzet`): **253.721 rijen in `boiler_temp`** en **2.368.296 rijen
in `thermostat_temp`** (3,4%), gelijk aan de som van `dubbele_tijdstippen__int` in `dekking.parquet`.
**Geen deduplicatie**: de rijen blijven ongewijzigd en dubbel in `boiler_temp/home_id=*.parquet` en
`thermostat_temp/home_id=*.parquet` staan. `dekking.py` leest de vlagkolom als bron van waarheid voor
`dubbele_tijdstippen__int` (`dekking._dubbele_tijdstippen`). Wie op `tijdstip` groepeert of resampled,
moet zelf met deze dubbelingen rekening houden; dat gebeurt hier niet automatisch. Zie §4.1 voor een
bevinding over een deel van deze dubbelingen (niet gerelateerd aan de zomertijd, op één specifieke
categorie na).

### 6.1 Volledige scan van de bronbestanden op tekstwaarden en onbekende sentinels

Gemeten op 03-10-2026 met `python -m warmingup_preprocessing.bronscan` (`bronscan.py`), over ELKE rij
van ELKE kolom van de vier CSV-bestanden in `data-en-resultaten.zip` en over de resultatentabel, dus
geen steekproef. De bron is als tekst gelezen; een veld telt als "niet numeriek" als het niet leeg is
en geen getal, en voor de tijd-, dag- en woningkolom als het niet de verwachte vorm heeft (ISO-8601
met `Z`, `JJJJ-MM-DD`, `WU<n>`). Geen enkel bestand heeft een rij met een afwijkend aantal velden. De
kolommen `House`/`house`, `Time` en `Day` hebben nergens een afwijkende vorm.

| bestand | kolom | niet-numerieke waarden | getalbereik | bekende en denkbare sentinelwaarden als getal |
|---|---|---|---|---|
| `boiler-temp.csv` (243.041.542 rijen, 220 woningen) | aanvoertemperatuur | `x`: 1.622.716 (0,67%), in 9 woningen | -40,0 tot 139,98 | -40: 9, -1: 29, 99: 25 |
| | retourtemperatuur | `x`: 881, in 3 woningen | -0,01 tot 139,88 | geen |
| | debiet (l/h) | geen | 0 tot 4.294.967.295 | 4.294.967.295 (2^32-1): 2.565 |
| `thermostat-temp.csv` (69.166.957 rijen, 223 woningen) | gewenste temperatuur | `null`: 1.683, in 188 woningen | -0,01 tot 192,4 | geen |
| | gemeten temperatuur | `null`: 1.749, in 193 woningen | -319,6 tot 325,55 | geen |
| `boiler-24h-stats.csv` (199.776 rijen, 223 woningen) | de vier gas- en branderuurkolommen | `NaN`: 23 per kolom, in dezelfde 12 woningen | gas tapwater -429.229,8 tot 429.326,6 m³; gas verwarming -89.363,2 tot 89.607,3 m³; branderuren -265.763,7 tot 132.750,2 h (tapwater) en -55.366,3 tot 27.707,1 h (verwarming) | geen |
| | de drie waterdrukkolommen | geen | -1 tot 3,65 bar | -1: 2 per kolom |
| `mapping.csv` (243 rijen) | `logger_id`, `serial_no`, `heater_id` | geen (wel leeg: 20, 3 en 24 keer) | n.v.t. | n.v.t. |

Wat dit zegt:

- **De tekst `x` komt niet alleen in de aanvoertemperatuur voor.** Hij staat ook 881 keer in de
  retourtemperatuur, vrijwel allemaal in woning WU177 (867; verder WU44 11 keer en WU32 3 keer). In het
  debiet, de thermostaat- en de etmaalkolommen komt hij niet voor.
- **De `x` in de aanvoertemperatuur zit vrijwel volledig in twee woningen**: WU1 (996.748 van 1.272.082
  rijen, 78,4%) en WU177 (564.514 van 915.381, 61,7%). Daarna volgen WU67 (3,3%), WU14 (1,2%) en WU118
  (0,2%); vier woningen hebben er 1 tot 16 (WU216: 16, WU44: 11, WU32: 3, WU52: 1), en 211 van de
  220 woningen hebben er geen. Het eerder gemelde "0% tot ruim 13% per woning" kwam uit
  een steekproef van het begin van het bestand; over alle rijen is het maximum 78,4% (WU1).
- **Het totaal klopt met het kwaliteitsrapport**: 1.622.716 `x` in de aanvoer en 881 in de retour zijn
  precies `q_flag_temp_aanvoer_ontbrekend__bool` en `q_flag_temp_retour_ontbrekend__bool` in
  `data-quality.md`. Er is dus geen tweede, ongevlagde vorm van een ontbrekende temperatuur.
- **In `thermostat_temp` is een ontbrekende waarde de tekst `null`** (3.432 velden, over de twee
  temperatuurkolommen samen). De lezer maakt er een lege waarde (`null` in Parquet) van, zonder aparte
  `ontbrekend`-vlag zoals bij `boiler_temp`: de lege waarde zelf is hier het signaal.
- **In `etmaal` is een ontbrekende waarde de tekst `NaN`**, in vier kolommen tegelijk, in 12 woningen
  (WU14 10 keer, WU113 3 keer, de rest 1 keer). Ook die wordt een lege waarde in Parquet.
- **Geen nieuwe getalsentinels gevonden.** Van de gezochte codes (-1, -40, -99, -999, -9999, 99, 999,
  9999, 99999, 255, 65535, 32767, -32768, 2^31-1, 2^32-1, 2^32, 10^9, 10^10) komen alleen de al bekende
  voor: de debietsentinel 2^32-1 en de waterdruk -1. De aanvoertemperatuur heeft er ook -40 (9 keer, de
  kortgesloten sensor), -1 (29 keer; buiten het bereik, dus gevlagd) en 99 (25 keer; binnen het bereik
  0 tot 100 °C, dus niet gevlagd en niet aantoonbaar een sentinel). Dat zijn waarden die de vlaggen in
  `sentinels.py` al afvangen of die als meting kunnen gelden.
- **Fysiek onmogelijke getallen komen veel voor**: gasverbruik per etmaal van ruim 429.000 m³, een
  gemeten binnentemperatuur van -319,6 °C, een aanvoertemperatuur van 139,98 °C. Die zijn het werk van
  de bereikvlaggen (`data-quality.md`), niet van een sentinel, en blijven staan in de data.
- **De resultatentabel** (212 rijen) heeft in geen enkele numerieke kolom een tekstcel. Wel valt op dat
  enkele modelparameters op een rond getal staan dat op een grens van de fit lijkt: `C_i [J/C]` is
  999.999.999,99 in 5 van de 198 gevulde rijen (en 999.999.996 in een zesde), `A_w [m2]` is 0 in 12 en
  kleiner dan 0,001 in 22 van de 198 rijen en 999,99999 in een. Dat is een waarneming; of het echte
  grenzen van de optimalisatie zijn, is niet vastgesteld, en de waarden zijn ongewijzigd overgenomen.

## 7. Hoe te laden

Eén woning uit `boiler_temp`:

```python
import pyarrow.parquet as pq

df = pq.read_table("data/processed/boiler_temp/home_id=WU0.parquet").to_pandas()
```

Alle woningen van `boiler_temp` in één keer (via het `home_id`-partitioneringspatroon in de
bestandsnaam, dus met `pyarrow.dataset` in plaats van los inlezen):

```python
import pyarrow.dataset as ds

dataset = ds.dataset("data/processed/boiler_temp", format="parquet", partitioning=None)
tabel = dataset.to_table(filter=ds.field("home_id__str") == "WU0")  # of zonder filter: alles
```

De kleine tabellen (`etmaal.parquet`, `mapping.parquet`, `resultaten.parquet`,
`info_metadata.parquet`, `dekking.parquet`) zijn elk klein genoeg om in één keer te lezen:

```python
import pandas as pd

resultaten = pd.read_parquet("data/processed/resultaten.parquet")
```

De kleine tabellen zijn gewone Parquet-bestanden zonder woningsleutel in het pad; `datapackage.json`
(zie §9) beschrijft alle zeven tabellen machineleesbaar, inclusief het onderscheid tussen de
patroon-vorm van het pad (generiek) en de expliciete bestandenlijst (na een concrete run).

**Uitvoercontractversie:** `2026-09-23-derde-opzet` (`manifest.UITVOER_CONTRACT_VERSIE`, staat ook
in elke regel van `_manifest.jsonl` en in `_voortgang.json`). Deze versie hoort omhoog te gaan zodra
de vorm of betekenis van de uitvoer verandert; sinds `2026-09-23-eerste-opzet` (de versie van de
eerste volledige run) is dat twee keer gebeurd: `q_flag_tijdstip_dubbel__bool` plus
`logger_id__str` als string (`2026-09-23-tweede-opzet`), en Europe/Amsterdam als weergavezone in
plaats van UTC (`2026-09-23-derde-opzet`, §4). Een bestaande uitvoermap van vóór deze wijzigingen
hoeft niet opnieuw uit de brondata opgebouwd te worden: `python -m warmingup_preprocessing.migreer
--uit <map>` migreert hem in-place (zie de moduledocstring van `migreer.py`).

## 8. Bekende beperkingen en open vragen

- **Dubbele tijdstempels worden gevlagd, niet verwijderd** (§6): `q_flag_tijdstip_dubbel__bool`
  (sinds `2026-09-23-tweede-opzet`) markeert elke rij vanaf de tweede keer dat een tijdstip
  voorkomt; er wordt nog steeds niets ontdubbeld.
- **`etmaal` heeft ook een niet-unieke sleutel**, een bevinding bij het bouwen van `datapackage.json`
  (23-09-2026): 5.856 van de 199.776 rijen hebben een dubbele combinatie van `home_id__str` en
  `datum__str`. Geen vlag hiervoor (in tegenstelling tot de tijdstip-dubbeling in `boiler_temp`/
  `thermostat_temp`); `datapackage.json` laat `primaryKey` voor `etmaal` daarom weg, met deze reden.
- **`__onbekend` als eenheid** voor `model_training_fout__onbekend`,
  `model_validatie_fout__onbekend`, `model_training_bias__onbekend`, `model_validatie_bias__onbekend`
  in `resultaten.parquet`: Deltares/het eindrapport documenteert de eenheid van deze vier kolommen
  niet expliciet (§5.5); aannemen dat het bijvoorbeeld graden is, zou een gok als feit presenteren.
- **`FLOW_BOVENGRENS__l_h = 5.000`** (de plausibiliteitsgrens voor debiet in `boiler_temp`) is een
  orde-van-grootte-keuze van deze pijplijn, geen gemeten of door Deltares opgegeven grens.
- **`Ci`/`Ce`-eenheid: rapport en brondata spreken elkaar tegen** (§5.5): het eindrapport noemt
  Wh/°C, de xlsx-kolomkop zelf zegt J/C (J/K) -- een factor 3600. Deze repo neemt de letterlijke
  bronkolomkop over; welke conventie de GETALLEN volgen is niet geverifieerd.
- **`resultaten.parquet` heeft 212 rijen**, wat noch met de steekproefomvang (220, eindrapport p. 7)
  noch met het aantal geslaagde modelkalibraties (187, eindrapport p. 18) overeenkomt (§5.5); niet
  verklaard in wat deze repo weet.
- **Aantal woningen loopt per tabel uiteen** (220 in `boiler_temp`, 223 in `thermostat_temp`, 243 in
  `mapping`, 212 in `resultaten`): deels te verklaren uit de 212-vs-220-vs-187-discrepantie
  hierboven, verder niet volledig verklaard (ontwerp-preprocessing.md §1).
- **De tekstsentinel `"x"`** in `Boiler Water Supply Temperature (°C)` (1.622.716 keer, in 9 van de 220
  woningen, vrijwel allemaal in WU1 en WU177; ook 881 keer in de retourtemperatuur, §6.1) is door deze
  repo zelf ontdekt tijdens het bouwen; het staat nergens in de KITE-pagina of in een begeleidend
  document van het archief, en is (voor zover bekend in deze repo) niet bij Deltares/KITE gemeld.
- **De intervalsemantiek van het debiet blijft `"onbekend"`** (§4): de toets over alle woningen geeft
  geen eenduidige uitkomst; vaststellen kan alleen met informatie van buiten de data (hoe de logger
  debiet en temperatuur tijdstempelt).
- **De vroegste `boiler_temp`-meting (2020-04-09) ligt vóór het installatievenster van de nieuwe
  instrumentatie dat het eindrapport noemt** (januari-november 2021, §1); niet verklaard.
- **De zomertijdgaten in `boiler_temp`** (§4.1) zijn een bevinding, geen vaststaande verklaring: de
  meest waarschijnlijke verklaring (lokale tijd verkeerd geïnterpreteerd bij de UTC-omzetting in de
  brondata zelf) is aannemelijk gemaakt, niet bewezen.
- **Sensormerk, -type, montagehoogte, kalibratie en meetonzekerheid van de individuele sensoren zijn
  niet vastgesteld** in deze repo (§3); het eindrapport beschrijft de meetmethode maar niet de
  sensorspecificaties.

## 9. Datapackage (machineleesbare beschrijving)

`datapackage.json` (repo-root, en aan het eind van elke run naast de uitvoer geschreven) is een
machineleesbare beschrijving van deze zeven tabellen volgens de
[Frictionless Data Package-standaard](https://specs.frictionlessdata.io/data-package/): per tabel een
Table Schema (kolomnamen, types, beschrijvingen, en waar zinvol een primaire sleutel of de reden
waarom die ontbreekt), plus licentie- en herkomstinformatie. Het wordt UIT DE CODE gegenereerd
(`warmingup_preprocessing.datapackage`, uit dezelfde Parquet-schema's die de pijplijn zelf gebruikt),
niet met de hand bijgehouden, en is te regenereren met
`python -m warmingup_preprocessing.datapackage`. Zie de moduledocstring van `datapackage.py` voor de
precieze keuzes (onder andere over het pad van de per-woning-tabellen).

## 10. Bronnen

- Pothof, I., Vreeken, T., & Van Meerkerk, M. (2022, 13 september). *Field measurements on lower
  radiator temperatures in existing buildings* (manuscript voor Energy and Buildings). Deltares,
  projectnummer 11205149. © Alle rechten voorbehouden; geciteerd met bronvermelding conform
  GEBRUIKSVOORWAARDEN.md, niet overgenomen als tabel of figuur.
- KITE (Kennis- en Dataplatform Individuele Technieken), RVO. Projectpagina *How Low Can You Go*,
  community Kennisdelen RVO. Zie GEBRUIKSVOORWAARDEN.md voor de letterlijke citaten over licentie en
  meldplicht.
- Het `info`-blad van de resultaten-xlsx (opgenomen als `info_metadata.parquet` in de uitvoer van
  deze pijplijn).
- Netherlands Enterprise Agency (RVO). (2011). *Voorbeeldwoningen 2011, bestaande bouw.*
- Coenen, M. M. G. (2019). *Accelerating the Dutch energy transition: lowering operating
  temperatures of heat distribution systems in the built environment.*
