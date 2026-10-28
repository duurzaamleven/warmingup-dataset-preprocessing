@echo off
rem Volledige scan van de ruwe bronbestanden op tekstwaarden en andere onbekende sentinels
rem (bronscan.py), los van een editor of chatsessie te draaien. Leest alleen; schrijft alleen
rem data\scan\*.json en data\bronscan.log. Streamend en zuinig (een blok van 16 MB tegelijk).
rem
rem RAW is de map met data-en-resultaten.zip (standaard data\raw). Zet RAW vooraf op de omgeving
rem als de zip elders staat, bijvoorbeeld op een netwerkschijf.

cd /d "%~dp0"
set PYTHONPATH=src
set PYTHONUNBUFFERED=1
set ARROW_DEFAULT_MEMORY_POOL=system
if not defined RAW set RAW=data\raw
if not exist data mkdir data
echo. >> data\bronscan.log
echo ==== start %DATE% %TIME% (raw: %RAW%) ==== >> data\bronscan.log
for %%B in (boiler-temp.csv thermostat-temp.csv boiler-24h-stats.csv "resultaat-tabel-WarmingUP_KITE openbare versie.xlsx") do (
  echo ---- %%~B %TIME% >> data\bronscan.log
  python -u -m warmingup_preprocessing.bronscan --raw-dir "%RAW%" --bestand "%%~B" --uit data\scan -v >> data\bronscan.log 2>&1
  echo ---- einde %%~B exitcode %ERRORLEVEL% %TIME% >> data\bronscan.log
)
echo ==== einde %DATE% %TIME% ==== >> data\bronscan.log
