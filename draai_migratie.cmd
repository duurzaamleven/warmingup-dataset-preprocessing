@echo off
rem Migreert een bestaande uitvoermap naar de huidige uitvoercontractversie (migreer.py), zonder de
rem brondata opnieuw te lezen. Hervatbaar en idempotent: opnieuw starten slaat over wat al gemigreerd
rem is. Bedoeld om via de Windows-taakplanner te starten, los van een editor of chatsessie.
rem
rem Zet UITVOER op de uitvoermap die gemigreerd moet worden. Zonder UITVOER stopt dit script, zodat
rem het nooit per ongeluk een andere map aanraakt dan bedoeld.

cd /d "%~dp0"
set PYTHONPATH=src
set PYTHONUNBUFFERED=1
set ARROW_DEFAULT_MEMORY_POOL=system
if not defined UITVOER (
  echo UITVOER is niet gezet; niets gedaan. >> data\migratie.log
  exit /b 2
)
if not exist data mkdir data
echo. >> data\migratie.log
echo ==== start %DATE% %TIME% (uitvoer: %UITVOER%) ==== >> data\migratie.log
python -u -m warmingup_preprocessing.migreer --uit "%UITVOER%" -v >> data\migratie.log 2>&1
echo ==== einde %DATE% %TIME% (exitcode %ERRORLEVEL%) ==== >> data\migratie.log
