# SPDX-License-Identifier: EUPL-1.2
from warmingup_preprocessing import kolommen


def test_boiler_temp_kolommen_compleet():
    assert kolommen.BOILER_TEMP_KOLOMMEN["House"] == "home_id__str"
    assert kolommen.BOILER_TEMP_KOLOMMEN["Flow (l/h)"] == "debiet_ruw__l_h"


def test_boiler_24h_kolommen_bevat_tikfout_uit_de_bron():
    # De bron zelf schrijft "DWH" i.p.v. "DHW" voor de branderduur tapwater; dit is geen aanname
    # maar een letterlijk citaat van de header, zie kolommen.py.
    assert "Heater Active Duration DWH (hours)" in kolommen.BOILER_24H_STATS_KOLOMMEN
    assert kolommen.BOILER_24H_STATS_KOLOMMEN["Heater Active Duration DWH (hours)"] == "t_brander_tapwater__h"


def test_debiet_conversie():
    assert kolommen.debiet_l_h_naar_dm3_s(3600) == 1.0


def test_bar_naar_pa():
    assert kolommen.bar_naar_pa(1.0) == 1e5


def test_resultaten_kolommen_zonder_lege_kolom():
    assert kolommen.RESULTATEN_GENEGEERDE_KOLOM not in kolommen.RESULTATEN_KOLOMMEN.values()


def test_resultaten_kolommen_zonder_logger_en_serienummer():
    # Versie van 27-10-2026 van de bron: deze kolommen bestaan niet meer in Sheet1.
    assert "logger_id" not in kolommen.RESULTATEN_KOLOMMEN
    assert "serial_no" not in kolommen.RESULTATEN_KOLOMMEN
