# Datakwaliteit

Dit bestand wordt door de pijplijn zelf geschreven (`warmingup_preprocessing.kwaliteitsrapport`), niet met de hand bijgehouden. Het telt per plausibiliteitsvlag hoe vaak hij True is (`sentinels.py`); geen enkele gevlagde rij is verwijderd, zie ontwerp-preprocessing.md §6.

Uitvoercontractversie: `2026-09-23-derde-opzet`.

## `boiler_temp` (minuutdata aanvoer/retour/debiet)

Totaal aantal rijen: 243.041.542

| vlag | aantal | aandeel |
|---|---:|---:|
| `q_flag_debiet_sentinel__bool` | 2.565 | 0.001% |
| `q_flag_debiet_bovengrens__bool` | 149.602 | 0.062% |
| `q_flag_temp_aanvoer_ontbrekend__bool` | 1.622.716 | 0.668% |
| `q_flag_temp_retour_ontbrekend__bool` | 881 | 0.000% |
| `q_flag_temp_aanvoer_bereik__bool` | 90.662 | 0.037% |
| `q_flag_temp_retour_bereik__bool` | 2.442 | 0.001% |
| `q_flag_tijdstip_dubbel__bool` | 253.721 | 0.104% |

## `thermostat_temp` (setpoint/binnentemperatuur)

Totaal aantal rijen: 69.166.957

| vlag | aantal | aandeel |
|---|---:|---:|
| `q_flag_temp_setpoint_bereik__bool` | 660 | 0.001% |
| `q_flag_temp_binnen_bereik__bool` | 347 | 0.001% |
| `q_flag_tijdstip_dubbel__bool` | 2.368.296 | 3.424% |

## `etmaal` (boiler-24h-stats)

Totaal aantal rijen: 199.776

| vlag | aantal | aandeel |
|---|---:|---:|
| `q_flag_gas_ruimteverwarming_bereik__bool` | 162 | 0.081% |
| `q_flag_gas_tapwater_bereik__bool` | 262 | 0.131% |
| `q_flag_brander_verwarming_bereik__bool` | 153 | 0.077% |
| `q_flag_brander_tapwater_bereik__bool` | 251 | 0.126% |
| `q_flag_druk_min_onbekend__bool` | 2 | 0.001% |
| `q_flag_druk_gem_onbekend__bool` | 2 | 0.001% |
| `q_flag_druk_max_onbekend__bool` | 2 | 0.001% |

## Dekking per woning

### boiler_temp

Aantal woningen met uitvoer: 220.
Dekkingsfractie (rijen / minuten in eigen venster): mediaan 0.996. p10 0.962. Totaal aantal dubbele tijdstempels: 253.721.

### thermostat_temp

Aantal woningen met uitvoer: 223.
Mediaan van het gemiddelde meetinterval per woning: 255 s.

## Zomertijdgaten rond de oktoberwissel (boiler_temp)

Bevinding van de opdrachtgever (23-09-2026, zie docs/datacatalogus.md §4 voor de methode): bij een deel van de woningen ontbreekt rond de overgang naar wintertijd precies het TWEEDE uur van het dubbelzinnige lokale tijdvenster. Dit telt alleen; er is GEEN correctie in de data, het ontbrekende uur is echt weg.

| datum (lokale wisseling) | woningen met data in het venster | woningen met een gat >= 50 min |
|---|---:|---:|
| 2021-10-31 | 206 | 117 |
| 2022-10-30 | 212 | 117 |

