# Ontwerp: de preprocessing-pijplijn

Dit document beschrijft wat er in de WarmingUP-dataset *How Low Can You Go* zit, wat deze pijplijn
ervan maakt, en waarom. Het is afgeleid van eigen onderzoek naar de dataset (zie GEBRUIKSVOORWAARDEN.md
voor herkomst en licentie) en van een eerste profilering van het archief, maar staat verder op
zichzelf.

## 1. Wat erin gaat

Eén zip-archief, `data/raw/data-en-resultaten.zip` (1,8 GB, buiten git), met zes leden:

| bestand | rijen | korrel | compressie |
|---|---:|---|---|
| `boiler-temp.csv` | 243.041.542 | 1 minuut, per woning | Deflate |
| `thermostat-temp.csv` | 69.166.957 | gebeurtenisgestuurd, per woning | **Deflate64** |
| `boiler-24h-stats.csv` | 199.776 | etmaal, per woning, lokale tijd | Deflate |
| `mapping.csv` | 243 | sleuteltabel | Deflate |
| `resultaat-tabel-…xlsx` (blad `Sheet1`) | 212 | per woning, eenmalig | Deflate |
| `README.md` | 4 regels | | Deflate |

220 tot 223 woningen (het aantal loopt per bestand uiteen, zie §6), elk met een pseudoniem `WU0` t/m
`WU242`, stabiel over alle bestanden. Alles gaat per woning; er is geen enkele aggregatie over
woningen in de bron.

**Geverifieerd, niet aangenomen: beide grote bestanden staan volledig aaneengesloten per woning.**
Een streamende controle over de volledige `House`-kolom (23-09-2026) liet zien dat geen enkele
woning op twee plekken in het bestand voorkomt: 220 woningen in `boiler-temp.csv` (243.041.542
rijen, 208,6 s voor de controle) en 223 in `thermostat-temp.csv` (69.166.957 rijen, 62,7 s). Dat
bepaalt de schrijfstrategie, zie §4.

## 2. Wat eruit komt

`data/processed/` (gitignored, configureerbaar via `--uit` of de omgevingsvariabele in
`draai_volledig.cmd`):

| uitvoer | vorm | inhoud |
|---|---|---|
| `boiler_temp/home_id=<id>.parquet` | één bestand per woning, zstd | aanvoer-/retourtemperatuur, debiet, afgeleid vermogen, kwaliteitsvlaggen |
| `thermostat_temp/home_id=<id>.parquet` | één bestand per woning, zstd | setpoint- en binnentemperatuur, kwaliteitsvlaggen |
| `etmaal.parquet` | één tabel, alle woningen | gas, branderuren, waterdruk, kwaliteitsvlaggen |
| `mapping.parquet` | één tabel | de sleuteltabel (logger/serienummer/ketel-id) |
| `resultaten.parquet` | één tabel | de 2R2C-parameters, ontwerp- en geïnstalleerd vermogen, woningkenmerken |
| `info_metadata.parquet` | één tabel | de tekst van het `info`-blad van de resultatentabel, als herkomst |
| `dekking.parquet` | één tabel | dekkingsstatistiek per woning per bron (§6) |
| `_manifest.jsonl` | append-only log | welk onderdeel wanneer met welke sha256/rijenaantal is afgerond |
| `_voortgang.json` | overschreven JSON | voortgang per bronbestand, zie §9 |
| `_sortering.json` | overschreven JSON | uitkomst van de aaneengesloten-controle, gecachet |
| `datapackage.json` | machineleesbare beschrijving | Frictionless Data Package v1, uit de code gegenereerd (§7, `datapackage.py`) |

Plus `docs/data-quality.md`, door de pijplijn zelf geschreven (§7).

**Bestaande uitvoer van een oudere contractversie omzetten zonder herrun**: `python -m
warmingup_preprocessing.migreer --uit <map>` (`migreer.py`) leest de al geschreven Parquet-bestanden
terug, past de vormveranderingen sinds die contractversie toe (tz-omzetting, de dedupvlag,
`logger_id__str` als string), en herbouwt `dekking.parquet`, `docs/data-quality.md` en
`datapackage.json`. Hervatbaar en idempotent via hetzelfde `Manifest.is_voltooid`-mechanisme als de
hoofdpijplijn (zie §5); geen apart migratiestatusbestand nodig. Zie de moduledocstring van
`migreer.py`.

**Waarom per woning voor de twee grote bestanden, en één tabel voor de rest.** De twee grote
bestanden zijn samen 12,3 GB ontcomprimeerd; wie maar een paar woningen nodig heeft, moet niet de
volledige set hoeven inlezen om ze eruit te filteren. De drie kleine bestanden (etmaal, mapping,
resultaten) zijn samen goed voor een paar tientallen MB en horen als geheel gelezen te worden: een
opsplitsing per woning zou alleen bestandsoverhead toevoegen.

**Bestandsnaamconventie.** `home_id=<id>.parquet` naast elkaar in een platte map, niet
`home_id=<id>/deel.parquet`. Een enkel bestand per map heeft geen functie (de sleutel staat ook al
in de kolom `home_id__str` zelf) en maakt een woning onherleidbaar zodra het bestand van zijn map
losraakt.

## 3. Kolomvertaling

Conform `physiquant__unit`: eenheid na de dubbele underscore, `_cum` alleen voor een meterstand op
een moment. Er staat in deze dataset geen enkele meterstand: alles is een momentaanwaarde, een
pulsdebiet, of een al door de bron gedifferentieerde etmaalwaarde.

De ruwe kolomnamen zijn **geverifieerd tegen het echte archief**, niet overgenomen uit een
samenvatting. Twee dingen wijken af van wat je zou verwachten: de tapwaterkolom in
`boiler-24h-stats.csv` heet voluit `Gas Usage Domestic Hot Water (DHW) (m³)`, en de brandertijd voor
tapwater heet `Heater Active Duration DWH (hours)`, met een **tikfout in de bron zelf** (`DWH`, niet
`DHW`). Zie `kolommen.py` voor de volledige vertaaltabel per bestand.

Twee grootheden krijgen bewust de eenheid `__onbekend`: `model_training_rms`/`model_validation_rms`
en de twee `mean_bias_error`-kolommen in de resultatentabel. Geen van beide is in de bron
gedocumenteerd; aannemen dat het bijvoorbeeld graden Celsius is (plausibel, want het is een 2R2C-fit
op de binnentemperatuur) zou een gok als feit presenteren. Zie CLAUDE.md-regel 5: een getal zonder
herkomst is schuld, en dat geldt evengoed voor een eenheid zonder herkomst.

De kolom `blank col1` in de resultatentabel is in de bron volledig leeg (alle 212 rijen `NaN`,
geverifieerd) en wordt weggelaten in plaats van vertaald.

## 4. Twee schrijfstrategieën, gekozen op een geverifieerde eigenschap

`schrijvers.controleer_aaneengesloten` doet één streamende pas over alleen de `House`-kolom (dus
zonder de andere kolommen te parsen) en stelt vast of elke woning aaneengesloten staat. Is dat zo,
dan schrijft `schrijvers.schrijf_per_woning_gesorteerd` in één streamende pas: op elk moment
hoogstens één `ParquetWriter` open, geheugengebruik onafhankelijk van de bestandsgrootte. Is dat niet
zo, dan verdeelt `schrijvers.schrijf_per_woning_ongesorteerd` elke chunk over deelbestanden per
woning per chunk, en compacteert na de volledige pas per woning met een rijtellingcontrole (dat
patroon is elders in het KITE-ecosysteem eerder toegepast voor hetzelfde probleem, en hier
overgenomen: chunkbestanden op naam verwerken, per woning optellen, en bij een afwijkend rijaantal
niets weggooien).

De uitkomst van de controle wordt gecachet in `_sortering.json`, apart voor een volledige run en een
`--test`-run (een kleinere steekproef van het bestand kan een andere uitkomst geven dan het geheel,
en de twee mogen elkaars cache niet overschrijven). Beide bestanden zijn voor de volledige dataset
aaneengesloten (§1), dus de gesorteerde route is de route die de volledige run werkelijk neemt.

### 4.1 Twee lezers: pandas (oorspronkelijk) en pyarrow (standaard, sinds de snelheidsfix)

**Het probleem.** Een eerste volledige run haalde circa 15.000 rijen/s, terwijl de testrun (`--test
--test-mb 300`) circa 150.000 rijen/s liet zien (zie VOORTGANG.md). Een `cProfile`-run op
`schrijf_per_woning_gesorteerd` wees uit waarom: circa 64% van de tijd ging naar
`tijd.naar_utc_tijdstip` (`pandas.to_datetime(..., format="%Y-%m-%dT%H:%M:%SZ", utc=True)`, dat
ondanks het expliciete formaat op de trage `_array_strptime_with_fallback`-route terechtkwam) en
circa 37% naar `pandas.read_csv` zelf (de C-parser, met `na_values=["x"]`). Een microbenchmark op
1.000.000 tijdstempels (onder zware systeemlast) bevestigde dit: het huidige formaat 40 s,
`pandas.to_datetime(..., format="ISO8601")` 17 s, `pyarrow.compute.strptime` 7 s -- alledrie
identieke waarden, dus geen precisieverlies, alleen snelheid.

**De oplossing: `snelle_lezer.py`, een tweede lezer voor dezelfde twee grote bestanden.**
`pyarrow.csv.open_csv` leest streamend van dezelfde bytestream die `ZipBron.open_bron` toch al
levert (ook de Deflate64-stream van `thermostat-temp.csv`: die is voor `pyarrow` niet anders dan een
gewone leesbare `IO[bytes]`), met een bescheiden blokgrootte (32 MB, ontwerp-eis: het systeem heeft
naast het hoofdproces maar enkele honderden MB vrij) en EXPLICIETE kolomtypen
(`pijplijn.BOILER_TEMP_KOLOM_TYPES_PYARROW`/`THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW`): de `Time`-kolom
gaat rechtstreeks naar `timestamp(ns, UTC)` (pyarrow herkent het ISO-8601-`Z`-formaat zonder een
apart patroon), en `null_values` bevat voor `boiler-temp.csv` de tekstsentinel `"x"` naast pyarrow's
eigen standaard-NA-teksten (vrijwel gelijk aan die van pandas), met `strings_can_be_null=True` zodat
dat net zo werkt als `pandas.read_csv(..., na_values=["x"])` nu al doet.

**Bit-voor-bit dezelfde uitvoer, bewust zo ontworpen.** De nieuwe lezer vervangt UITSLUITEND het stuk
tussen "bytes uit de zip" en "een pandas-`DataFrame` met dezelfde kolomnamen en dtypes alsof
`pandas.read_csv` het gelezen had" (`snelle_lezer.batch_naar_pandas`, met `types_mapper=None`: geen
`pyarrow`-backed pandas-dtypes, want `sentinels.py` en `tijd.py` doen gewone `numpy`/`pandas`-
bewerkingen). Alles daarna -- hernoemen, `sentinels.flag_*`, `_cast_naar_schema` -- blijft
ongewijzigd. De tijdstip-conversie zelf verschuift van "per woninggroep, binnen `_transformeer_chunk`"
naar "één keer per chunk, vóór het groeperen" (voor de pandas-route) respectievelijk "al gebeurd
tijdens het CSV-lezen" (voor de pyarrow-route): beide zijn een pure elementgewijze bewerking, dus dat
levert bit-voor-bit dezelfde waarden op, alleen in minder, grotere stappen.

**Goedkoop hervatten: filteren vóór de pandas-conversie.** Bij een hervatte run staat het merendeel
van een chunk vaak al in het manifest. `snelle_lezer.filtreer_voltooide_woningen` gebruikt
`pyarrow.compute.is_in` rechtstreeks op de Arrow-`House`-kolom om die rijen weg te filteren VÓÓRDAT er
een pandas-`DataFrame` van gemaakt wordt: geen hernoemen, geen vlaggen, geen schrijfactie, en ook geen
pandas-conversie voor rijen die toch worden weggegooid. De decompressie en het CSV-tokenizen van die
rijen blijven wel nodig (geen van beide compressievormen ondersteunt seeken, zie §5), maar dat stuk is
met `pyarrow.csv` zelf ook al sneller dan de oude route.

**Kanttekening bij de blokgrootte en de `SorteerFout`-vangnet.** De schrijflus bewaakt zelf nog een
keer of een woning niet toch op twee plekken voorkomt (`SorteerFout`, zie §4): dat werkt alleen over
chunk-/blokgrenzen heen, niet BINNEN één chunk of Arrow-batch (`pandas.DataFrame.groupby` voegt
binnen één stuk data toch alle rijen van een woning samen, ongeacht hun volgorde). De blokgrootte van
32 MB is qua orde van grootte vergelijkbaar met de oude `CHUNKSIZE_STANDAARD` van 250.000 rijen (rond
de 10 MB), dus dit vangnet is met de nieuwe lezer niet wezenlijk grover geworden. Het blijft sowieso
een tweede, overtollige controle: de PRIMAIRE beslissing (welke route gekozen wordt) steunt op
`controleer_aaneengesloten`, dat het HELE bestand ziet.

**Lezer kiezen: `--lezer pandas|pyarrow`.** `pyarrow` is de standaard (`schrijvers.LEZER_STANDAARD`).
`--lezer pandas` behoudt de oorspronkelijke, langzamere route; die bestaat voortaan uitsluitend om de
gelijkheidstoets reproduceerbaar te houden (`tests/test_snelle_lezer_gelijkheid.py`, en handmatig: zie
hieronder). De ongesorteerde route (`schrijf_per_woning_ongesorteerd`) blijft pandas-only: de echte
bron raakt hem niet (zie de moduledocstring van `schrijvers.py`), dus de snelheidswinst is daar niet
nodig, en de fallback blijft zo eenvoudig mogelijk.

**Gelijkheidstoets tegen de echte bron (23-09-2026).** `--test --test-mb 50` gedraaid met beide
lezers, naar twee aparte mappen (`data/vergelijk-oud`, `data/vergelijk-nieuw`, buiten git, NIET
`data/processed`): 2 woningen in `boiler_temp` (waaronder de "x"-tekstsentinel, 113.208 keer in deze
steekproef, uitsluitend in de kolom die dat al droeg) en 5 in `thermostat_temp`, plus `etmaal`,
`mapping`, `resultaten`, `info_metadata` en `dekking`. Vergeleken met
`pyarrow.parquet.read_table(...).equals(...)`: **alle tabellen bit-voor-bit identiek**, schema en
waarden. Het aantal "x"-rijen per woning is bovendien onafhankelijk geverifieerd tegen een derde,
losse telling direct op de ruwe CSV-tekst (113.208, exact gelijk). Een tweede aanroep met dezelfde
`--test-mb 50` op dezelfde `data/vergelijk-nieuw`-map bevestigde het goedkope-hervat-pad: 3,4 s, geen
enkele woning opnieuw geschreven, rijaantallen ongewijzigd.

**Doorvoer, gemeten op dezelfde steekproef uit de echte bron, ONDER DE HUIDIGE SYSTEEMLAST** (de
volledige run liep tegelijk, op dezelfde ene kern; deze cijfers zijn dus een ondergrens, geen
laboratoriummeting):

| bronbestand | steekproef | pandas (oud) | pyarrow (nieuw) | versnelling |
|---|---:|---:|---:|---:|
| `boiler-temp.csv` | 150 MB, 3.880.525 rijen | 155,6 s -- 24.947 rijen/s | 50,9 s -- 76.280 rijen/s | 3,1x |
| `thermostat-temp.csv` (Deflate64) | 100 MB, 2.772.898 rijen | 248,2 s -- 11.172 rijen/s | 39,9 s -- 69.472 rijen/s | 6,2x |
| beide grote bestanden samen (CLI, `--test-mb 50`, incl. sorteringscontrole en kleine stappen) | 50 MB per bestand | 25,6 s (totaal) | 12,4 s (totaal) | 2,1x |

Zonder de concurrerende volledige run zou de nieuwe route waarschijnlijk nog sneller zijn (beide
metingen delen dezelfde ene kern); deze tabel is dus een voorzichtige schatting van de winst, niet de
bovengrens.

## 5. Hervatbaarheid

`_manifest.jsonl` is een append-only log: één regel per voltooid onderdeel (een woning voor de twee
grote bestanden, het geheel voor de kleine tabellen), met pad, sha256, rijenaantal en de
uitvoercontractversie. Een herstart leest dit bestand en slaat een onderdeel over zodra de manifestregel
klopt mét een bestaand bestand op schijf.

Twee lagen atomiciteit: elk stuk uitvoer gaat eerst naar `<pad>.tmp` en wordt pas na een geslaagde
schrijfactie hernoemd naar zijn definitieve naam; pas daarna komt er een manifestregel bij. Een
halverwege afgebroken run laat dus nooit een bestand met de definitieve naam achter dat toch
onvolledig is, en nooit een manifestregel voor iets dat niet echt op schijf staat.

**Hervatten bespaart transformatie- en schrijftijd, niet decompressietijd.** Geen van beide
compressievormen ondersteunt seeken naar een specifieke woning; een herstart leest het bronbestand
dus opnieuw vanaf het begin. Voor elke woning die het manifest al als voltooid kent, worden de
kolomvertaling, de plausibiliteitsvlaggen en de Parquet-schrijfactie overgeslagen; alleen het
CSV-parsen van die rijen gebeurt nog, om door te kunnen lezen naar de volgende (nog niet voltooide)
woning. Dat is een bewuste keuze: seeken zou een eigen indexbestand vergen dat bij elke
codewijziging opnieuw valide moet zijn, en de winst zit toch al vooral in het overslaan van het dure
werk, niet van de I/O.

`UITVOER_CONTRACT_VERSIE` (`manifest.py`) staat in elke manifestregel. Wijzigt de vorm of betekenis
van de uitvoer, dan hoort deze versie omhoog: een hervatting met een oude contractversie in het
manifest behandelt dat onderdeel als "nog te doen", nooit als "toevallig nog goed".

## 6. Tijdzone, intervalsemantiek, sentinels en dekking

**Twee tijdzones in de bron, één weergavezone in de uitvoer.** `boiler-temp.csv` en
`thermostat-temp.csv` dragen een `Z`-suffix (UTC). `boiler-24h-stats.csv` heeft een kolom die
letterlijk `Day (Europe/Amsterdam)` heet: een lokale kalenderdag. Deze pijplijn parseert de
tz-aware tijdstempels eerst naar UTC (`tijd.naar_utc_tijdstip`, de interne rekenbasis: sentinels,
dekking en de plausibiliteitsvlaggen werken allemaal op UTC) en zet ze pas als allerlaatste stap
vóór het schrijven om naar de weergavezone Europe/Amsterdam (`tijd.naar_weergave_tijdzone`,
`tz_convert`, geen `tz_localize`: het instant verandert niet, alleen de tz-metadata). Dit is een
aanvullende eis van de opdrachtgever (23-09-2026, analoog aan de Installatiemonitor-preprocessing),
onderbouwd doordat de bron de etmaalkolom zelf al als `Day (Europe/Amsterdam)` labelt, de steekproef
gericht is op de Nederlandse woningvoorraad, het KNMI-weerstation dat het eindrapport gebruikt
(Deelen) geografisch het dichtst bij de meeste onderzochte gebouwen ligt, en de vijf deelnemende
warmtebedrijven in Europees Nederland leveren (zie docs/datacatalogus.md §4 voor de volledige
onderbouwing met bronvermelding). Vóór contractversie `2026-09-23-derde-opzet` stond `tijdstip` in
UTC.

De etmaalkolom blijft een tekstuele kalenderdag (`datum__str`, geen `timestamp`) en wordt niet
stilzwijgend omgerekend, want dat zou de dag zelf laten verschuiven. `tijd.etmaalgrens_utc` rekent op
verzoek het UTC-venster van een lokale dag uit, met de juiste lengte (23 of 25 uur rond een
zomertijdovergang; dit heeft tijdens het bouwen een echte bug blootgelegd, zie de tests en de
code-commentaar in `tijd.py`); een vergelijking met een Europe/Amsterdam-tijdstempel werkt daar
automatisch overheen, want tijdzonevergelijking in pandas gaat altijd via het instant.

**Bevinding: zomertijdgaten in `boiler_temp` rond de oktoberwissel** (opdrachtgever, 23-09-2026, zie
docs/datacatalogus.md §4.1 voor de volledige methode en cijfers, en `kwaliteitsrapport.py` voor de
telling). Bij circa 60% van de woningen ontbreekt rond de overgang naar wintertijd (eind oktober)
precies het TWEEDE uur van het dubbelzinnige lokale tijdvenster; getoetst aan de hand van de
temperatuursprong rond het gat is dit een echt ontbrekend uur, geen verkeerd toegewezen dubbeling.
Geen correctie in de data: het uur is en blijft weg.

**Intervalsemantiek van het debiet: een expliciete, benoemde aanname.** Of een minuutwaarde in
`debiet__dm3_s_1` het voorafgaande of het volgende interval dekt, staat nergens gedocumenteerd en is
alleen uit de data zelf te toetsen. `tijd.AANNAME_DEBIET_INTERVAL_LABEL` legt dit vast als
`"onbekend"`, met naam en commentaar, in plaats van impliciet in een latere resample-stap. Deze
pijplijn doet zelf geen resampling of interval-integratie, dus de aanname raakt hier geen berekening;
ze staat er zodat een latere gebruiker die wél gaat integreren een expliciete keuze overneemt.
`intervalsemantiek.py` is een losse, met de hand te draaien toets: hij zoekt pompstarts (debiet van
nul naar positief) en meet de vertraging tot de sterkste temperatuursprong in een klein venster
eromheen, over de woningen van een uitvoermap. De uitkomst over alle woningen (03-10-2026) staat in
VOORTGANG.md en docs/datacatalogus.md §4: niet eenduidig, dus de aanname blijft `"onbekend"`.

**Sentinels en plausibiliteit: vlaggen, niet verwijderen.** Elke controle levert een boolean
kwaliteitskolom op; er wordt nooit een rij weggegooid. Twee uitzonderingen waarbij een sentinel wél
naar `NaN` gaat in de gewone kolom: de waterdruksentinel `-1` bar (de kolomnaam documenteert dit zelf
als "onbekend") en de debiet-sentinel `2^32-1` in de omgerekende kolom `debiet__dm3_s_1` (de rauwe
kolom `debiet_ruw__l_h` toont de sentinel gewoon). De afgeleide `q_afgifte__W` wordt `NaN` zodra één
van zijn drie invoerwaarden gevlagd is: een vermogen berekend uit een sentinel of een kortgesloten
sensor is geen extreme meting, het is rekenkundig onzin. Zie `sentinels.py` voor de volledige lijst
grenzen en de motivatie per grens.

**Een vierde sentinel, niet in het ontwerp gedocumenteerd, gevonden tijdens het bouwen.** De
letterlijke tekst `"x"` komt voor in plaats van een getal. Een volledige scan van alle rijen
(03-10-2026, `bronscan.py`, uitkomsten in docs/datacatalogus.md §6.1) liet zien: 1.622.716 keer in
`Boiler Water Supply Temperature (°C)` van `boiler-temp.csv` (in 9 van de 220 woningen, vrijwel
allemaal WU1 met 78,4% van zijn rijen en WU177 met 61,7%) en 881 keer in
`Boiler Water Return Temperature (°C)` (3 woningen, vrijwel allemaal WU177); in geen enkele andere
kolom van geen enkel bestand. Zonder maatregel liet `pandas.read_csv` de kolom voor een heel
ingelezen blok als tekst in plaats van als getal behandelen, wat verderop een harde fout gaf. Opgelost
met `na_values` aan de CSV-lezer (`zipbron.lees_csv_in_chunks`) en een eigen
`q_flag_temp_aanvoer_ontbrekend__bool` (en `q_flag_temp_retour_ontbrekend__bool`), losstaand van
"gemeten maar buiten het plausibele bereik" (`q_flag_temp_aanvoer_bereik__bool`): dat zijn twee
verschillende dingen om te melden. Dit is niet gemeld op de KITE-pagina of in enig begeleidend
document dat bij het archief zit. De andere bronbestanden hebben hun eigen tekst voor "ontbrekend":
`null` in `thermostat-temp.csv` (3.432 velden) en `NaN` in `boiler-24h-stats.csv` (23 rijen); beide
worden door de lezers al als lege waarde herkend.

**`T_retour > T_aanvoer` is expliciet géén kwaliteitsfout.** Bij een stilstaande pomp en een
afkoelende ketel kan de retour tijdelijk boven de aanvoer liggen; dat levert een negatief
`q_afgifte__W` op, en dat is correct, geen artefact. Er is dus bewust geen vlag voor deze situatie.

**Dekking per woning per bron (`dekking.py`).** Voor `boiler_temp`: aantal rijen gedeeld door het
aantal minuten in het eigen venster van die woning (eerste tot laatste tijdstip), plus het aantal
dubbele tijdstempels. Voor `thermostat_temp`: GEEN dekkingsfractie tegen een minuutraster, want de
metingen zijn gebeurtenisgestuurd en een ontbrekende minuut betekent hier "niets veranderd", niet
"geen meting"; in plaats daarvan het gemiddelde interval tussen twee opeenvolgende metingen.

## 7. Het kwaliteitsrapport

`docs/data-quality.md` wordt door `kwaliteitsrapport.py` geschreven, telkens aan het eind van een
volledige `run()`. Het telt per plausibiliteitsvlag hoe vaak hij `True` is (gestreamd over de
Parquet-rijgroepen, niet door alles in geheugen te laden) en vat de dekking samen. Bij een
`--test`-run staat er een expliciete waarschuwing bovenaan dat het rapport over een steekproef gaat.

## 8. Deflate64

`thermostat-temp.csv` staat in het archief met Deflate64 (`compress_type == 9`); Python's `zipfile`
kan dat niet openen. De gekozen oplossing is `inflate64` als afhankelijkheid (zoals al in
`pyproject.toml` vastgelegd vóórdat dit document geschreven werd), maar die levert alleen een
inflater, geen zip-integratie. `deflate64.py` legt die integratie zelf: de lokale bestandsheader in
de zip wordt gelezen om de exacte bytepositie van de gecomprimeerde data te vinden (die staat niet
op `ZipInfo.header_offset` zelf, daar zit nog een variabele-lengte header tussen), en vervolgens
worden precies `compress_size` bytes in blokken aan `inflate64.Inflater` gevoerd. Geverifieerd tegen
het echte archief: de eerste regels decomprimeren correct, de kolomkoppen kloppen, en een streamende
`pandas.read_csv` erop werkt zoals op een gewoon Deflate-lid.

Dit is de enige plek in de repo die `inflate64` gebruikt; de vijf andere leden gaan gewoon via
`zipfile.ZipFile.open`.

## 9. Het voortgangsbestand

`data/processed/_voortgang.json` wordt bij elke chunk bijgewerkt, met een garantie dat er nooit meer
dan 45 seconden tussen twee schrijfacties zit (ruim onder de eis van "minstens elke minuut"). Formaat:

```json
{
  "uitvoer_contract_versie": "2026-09-23-derde-opzet",
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

`bytes_gelezen__B` is ONTCOMPRIMEERD (dus vergelijkbaar met `bytes_totaal__B`, dat `file_size` uit de
zip-index is); voor Deflate64 is dat de output van `inflate64.Inflater`, voor gewone Deflate wat
`zipfile.ZipExtFile.read()` teruggeeft. `bytes_gelezen__B / bytes_totaal__B` is dus rechtstreeks een
voortgangsfractie, en samen met `laatst_bijgewerkt_op - gestart_op` een ETA. Zie ook README.md.

## 10. Eigen keuzes die niet letterlijk uit een specificatie volgen

Dit zijn de plekken waar deze pijplijn zelf iets heeft moeten beslissen, expliciet opgesomd:

1. **De plausibiliteitsgrens voor debiet (5.000 l/h)** is een orde-van-grootte-keuze, geen meting;
   zie `sentinels.FLOW_BOVENGRENS__l_h` voor de motivatie en het voorbehoud.
2. **`model_training_rms` e.d. krijgen `__onbekend` als eenheid** in plaats van een aangenomen `°C`
   (§3).
3. **`Order`/`resultaat_volgnummer__int`** uit de resultatentabel wordt meegenomen als kolom, ook al
   is het geen fysische grootheid: het is de enige kolom die de oorspronkelijke volgorde van de
   xlsx-rijen vastlegt, en weglaten zou die informatie stil laten verdwijnen.
4. **Het `info`-blad wordt als tekst-tabel bewaard** (`info_metadata.parquet`, één rij per niet-lege
   regel), niet geïnterpreteerd: het is herkomst, geen meetgrootheid, en interpretatie zou een
   aanname zijn die niet aan deze pijplijn is.
5. **Water Pressure-kolommen worden intern eerst als `__bar` weggeschreven en pas ná de
   sentinelvervanging naar `__Pa` omgerekend** (`sentinels.py`/`tabellen.py`): een kolomnaam die al
   `__Pa` zegt terwijl de waarde nog in bar staat, zou zelf een kleine foutbron zijn.
6. **De sorteringscontrole leest het hele bestand** (alleen de `House`-kolom, dus relatief snel) in
   plaats van een steekproef te nemen: een gemiste revisit verderop in het bestand zou een woning
   stilzwijgend over twee Parquet-bestanden verdelen, en dat risico is de extra minuten niet waard.
7. **`q_afgifte__W` rekent met vaste waterconstanten** (ρ = 998,2 kg/m³, cₚ = 4186 J/(kg·K), bij
   circa 20 °C) in plaats van temperatuurafhankelijke waarden: het verschil is voor deze toepassing
   verwaarloosbaar en een vaste waarde is herleidbaarder dan een verborgen tabel.

## 11. Wat deze pijplijn niet doet

- Geen resampling, geen interval-integratie, geen aggregatie over woningen.
- Geen conclusie over de intervalsemantiek van het debiet (§6): alleen een toets die rapporteert, geen
  automatische herschrijving van de aanname.
- Geen reconstructie van de 2R2C-parameters uit de ruwe minuutdata; de resultatentabel wordt
  overgenomen zoals ze is, met herkomst.
- Geen verwijdering van gevlagde rijen.
