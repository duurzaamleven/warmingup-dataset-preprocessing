@echo off
rem Intervalsemantiek-toets (intervalsemantiek.py) over ALLE woningen van een bestaande uitvoermap, los van
rem een editor of chatsessie te draaien. Leest alleen uit de uitvoermap; schrijft naar data\intervalsemantiek
rem en data\intervalsemantiek.log.
rem
rem Zet UITVOER op de uitvoermap (een volledige run). Zonder UITVOER stopt dit script.

cd /d "%~dp0"
set PYTHONPATH=src
set PYTHONUNBUFFERED=1
set ARROW_DEFAULT_MEMORY_POOL=system
if not defined UITVOER (
  echo UITVOER is niet gezet; niets gedaan. >> data\intervalsemantiek.log
  exit /b 2
)
if not exist data mkdir data
echo. >> data\intervalsemantiek.log
echo ==== start %DATE% %TIME% (uitvoer: %UITVOER%) ==== >> data\intervalsemantiek.log
python -u -m warmingup_preprocessing.intervalsemantiek --uit "%UITVOER%" --steekproef 0 --max-starts 0 --csv-dir data\intervalsemantiek -v >> data\intervalsemantiek.log 2>&1
echo ==== einde %DATE% %TIME% (exitcode %ERRORLEVEL%) ==== >> data\intervalsemantiek.log
