@echo off
rem De volledige preprocessing, onbeheerd en hervatbaar (ontwerp-preprocessing.md).
rem
rem Bedoeld om via de Windows-taakplanner gestart te worden, niet vanuit een terminal: de
rem taakplanner koppelt het proces los van de sessie die het start, zodat het sluiten van de editor
rem of van een chatsessie de run niet meeneemt. Een achtergrondproces uit een terminal zit in een
rem job object en gaat wel mee.
rem
rem De run is hervatbaar: een woning/tabel waarvan het definitieve bestand al in _manifest.jsonl
rem staat, wordt overgeslagen. Opnieuw starten kost dus niets wat al af is.
rem
rem Deze repo REGISTREERT of START deze taak niet zelf; zie taak-volledig.xml voor het commando.

cd /d "%~dp0"
set PYTHONPATH=src
set PYTHONUNBUFFERED=1
rem De standaard arrow-geheugenpool geeft vrijgegeven blokken niet aan het systeem terug. Bij een
rem run die honderden chunks achter elkaar alloceert en weer loslaat groeit de commit charge daardoor
rem mee met het aantal chunks in plaats van met de grootste chunk (zelfde observatie als bij de
rem DPH-preprocessing). Het is een instelling en geen ontwerp, en hij staat daarom hier en niet in de
rem code.
set ARROW_DEFAULT_MEMORY_POOL=system

rem Uitvoerpad: lokale configuratie, geen onderdeel van deze repo. Zet UITVOER vooraf op de
rem omgeving waar dit script draait (bijvoorbeeld een netwerkschijf, als C: krap is en andere
rem machines de tabellen van daar moeten lezen); zonder die omgevingsvariabele valt dit terug op een
rem lokale map.
if not defined UITVOER set UITVOER=data\processed
rem Invoer: de map met data-en-resultaten.zip (of het zip-bestand zelf). Zet RAW vooraf op de
rem omgeving als de zip elders staat; standaard data\raw. Staan er in die map meer zips, dan moet
rem er precies een "resultaten" in de naam hebben, anders stopt de run met een foutmelding.
if not defined RAW set RAW=data\raw

if not exist data mkdir data
echo. >> data\volledig-run.log
echo ==== start %DATE% %TIME% (raw: %RAW%, uitvoer: %UITVOER%) ==== >> data\volledig-run.log
python -u -m warmingup_preprocessing --raw-dir "%RAW%" --uit "%UITVOER%" -v >> data\volledig-run.log 2>&1
echo ==== einde %DATE% %TIME% (exitcode %ERRORLEVEL%) ==== >> data\volledig-run.log
