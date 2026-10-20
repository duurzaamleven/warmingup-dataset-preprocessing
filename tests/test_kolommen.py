# SPDX-License-Identifier: EUPL-1.2
import pandas as pd

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


def test_naar_string_zonder_punt0_int64():
    kolom = pd.Series([20000001, 20000002], dtype="int64")
    resultaat = kolommen.naar_string_zonder_punt0(kolom)
    assert resultaat.tolist() == ["20000001", "20000002"]


def test_naar_string_zonder_punt0_float64_met_ontbrekende_waarde():
    # pandas.read_excel geeft float64 zodra één cel in een numerieke kolom leeg is; een kale
    # .astype(str) zou hier "20000001.0" opleveren, zie kolommen.naar_string_zonder_punt0.
    kolom = pd.Series([20000001.0, float("nan"), 20000003.0], dtype="float64")
    resultaat = kolommen.naar_string_zonder_punt0(kolom)
    assert resultaat.iloc[0] == "20000001"
    assert pd.isna(resultaat.iloc[1])
    assert resultaat.iloc[2] == "20000003"


def test_naar_string_zonder_punt0_al_tekst_blijft_ongewijzigd():
    kolom = pd.Series(["20000001", "20000002"], dtype=object)
    resultaat = kolommen.naar_string_zonder_punt0(kolom)
    assert resultaat.tolist() == ["20000001", "20000002"]
