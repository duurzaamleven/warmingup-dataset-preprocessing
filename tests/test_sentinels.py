# SPDX-License-Identifier: EUPL-1.2
import math

import pandas as pd

from warmingup_preprocessing import sentinels


def _boiler_temp_df():
    return pd.DataFrame(
        {
            "home_id__str": ["WU0"] * 5,
            "tijdstip": pd.date_range("2021-01-01", periods=5, freq="min", tz="UTC"),
            "temp_aanvoer__degC": [40.0, -40.0, 150.0, 45.0, 40.0],
            "temp_retour__degC": [30.0, 30.0, 30.0, 30.0, 31.0],
            "debiet_ruw__l_h": [300, 300, 300, sentinels.FLOW_SENTINEL__l_h, 100_000],
        }
    )


def test_flag_boiler_temp_sentinel():
    df = sentinels.flag_boiler_temp(_boiler_temp_df())
    assert df["q_flag_debiet_sentinel__bool"].tolist() == [False, False, False, True, False]
    assert math.isnan(df.loc[3, "debiet__dm3_s_1"])
    assert math.isnan(df.loc[3, "q_afgifte__W"])


def test_flag_boiler_temp_bovengrens():
    df = sentinels.flag_boiler_temp(_boiler_temp_df())
    assert df["q_flag_debiet_bovengrens__bool"].tolist() == [False, False, False, False, True]
    assert math.isnan(df.loc[4, "q_afgifte__W"])


def test_flag_boiler_temp_temperatuurbereik():
    df = sentinels.flag_boiler_temp(_boiler_temp_df())
    assert df["q_flag_temp_aanvoer_bereik__bool"].tolist() == [False, True, True, False, False]
    assert math.isnan(df.loc[1, "q_afgifte__W"])
    assert math.isnan(df.loc[2, "q_afgifte__W"])


def test_flag_boiler_temp_geldige_rij_krijgt_q_afgifte():
    df = sentinels.flag_boiler_temp(_boiler_temp_df())
    assert not math.isnan(df.loc[0, "q_afgifte__W"])
    verwacht = (300 / 3600.0 / 1000.0) * 998.2 * 4186.0 * (40.0 - 30.0)
    assert abs(df.loc[0, "q_afgifte__W"] - verwacht) < 1.0


def test_retour_boven_aanvoer_is_geen_fout():
    """ontwerp-preprocessing.md §6: T_retour > T_aanvoer is bij lage/nul-debiet geen kwaliteitsfout."""
    df = pd.DataFrame(
        {
            "home_id__str": ["WU0"],
            "tijdstip": pd.date_range("2021-01-01", periods=1, tz="UTC"),
            "temp_aanvoer__degC": [30.0],
            "temp_retour__degC": [35.0],
            "debiet_ruw__l_h": [50],  # laag, niet nul: bij nul debiet is q_afgifte sowieso 0
        }
    )
    df = sentinels.flag_boiler_temp(df)
    assert not df.loc[0, "q_flag_temp_aanvoer_bereik__bool"]
    assert not df.loc[0, "q_flag_temp_retour_bereik__bool"]
    assert df.loc[0, "q_afgifte__W"] < 0  # negatief, en dat is hier correct, geen fout


def test_flag_thermostat_temp():
    df = pd.DataFrame(
        {
            "home_id__str": ["WU0"] * 3,
            "tijdstip": pd.date_range("2021-01-01", periods=3, freq="h", tz="UTC"),
            "temp_setpoint__degC": [19.0, 192.4, 20.0],
            "temp_binnen__degC": [20.0, -319.6, 21.0],
        }
    )
    df = sentinels.flag_thermostat_temp(df)
    assert df["q_flag_temp_setpoint_bereik__bool"].tolist() == [False, True, False]
    assert df["q_flag_temp_binnen_bereik__bool"].tolist() == [False, True, False]


def test_flag_tijdstip_dubbel_binnen_een_aanroep():
    tijdstip = pd.Series(
        pd.to_datetime(["2021-01-01T00:00", "2021-01-01T00:01", "2021-01-01T00:00", "2021-01-01T00:02"]).astype("int64")
    )
    gezien: set[int] = set()
    vlag = sentinels.flag_tijdstip_dubbel(tijdstip, gezien)
    assert vlag.tolist() == [False, False, True, False]
    assert len(gezien) == 3


def test_flag_tijdstip_dubbel_over_meerdere_aanroepen_heen():
    """De set moet bijgewerkt blijven over aanroepen (chunks) heen, ook als een dubbeling pas in
    een LATERE aanroep terugkomt en niet op de vorige rij volgt (de bron is niet op tijd gesorteerd
    binnen een woning, zie de moduledocstring van flag_tijdstip_dubbel)."""
    gezien: set[int] = set()
    eerste_chunk = pd.Series(pd.to_datetime(["2021-01-01T00:00", "2021-01-01T00:05"]).astype("int64"))
    tweede_chunk = pd.Series(pd.to_datetime(["2021-01-01T00:10", "2021-01-01T00:00"]).astype("int64"))  # terugspringend
    vlag1 = sentinels.flag_tijdstip_dubbel(eerste_chunk, gezien)
    vlag2 = sentinels.flag_tijdstip_dubbel(tweede_chunk, gezien)
    assert vlag1.tolist() == [False, False]
    assert vlag2.tolist() == [False, True]  # de laatste rij herhaalt het allereerste tijdstip


def test_flag_tijdstip_dubbel_drie_keer_hetzelfde():
    gezien: set[int] = set()
    tijdstip = pd.Series(pd.to_datetime(["2021-01-01T00:00"] * 3).astype("int64"))
    vlag = sentinels.flag_tijdstip_dubbel(tijdstip, gezien)
    assert vlag.tolist() == [False, True, True]


def test_flag_boiler_24h_stats_druksentinel_wordt_nan():
    df = pd.DataFrame(
        {
            "home_id__str": ["WU0"] * 2,
            "datum__str": ["2021-01-01", "2021-01-02"],
            "g_tapwater__m3": [0.5, 0.6],
            "g_ruimteverwarming__m3": [3.0, -89363.0],
            "t_brander_tapwater__h": [0.2, 0.3],
            "t_brander_verwarming__h": [1.0, 1.1],
            "p_cv_min__bar": [1.5, -1.0],
            "p_cv_gem__bar": [1.6, -1.0],
            "p_cv_max__bar": [1.7, -1.0],
        }
    )
    df = sentinels.flag_boiler_24h_stats(df)
    assert df["q_flag_druk_min_onbekend__bool"].tolist() == [False, True]
    assert math.isnan(df.loc[1, "p_cv_min__bar"])
    assert df["q_flag_gas_ruimteverwarming_bereik__bool"].tolist() == [False, True]
    # De rauwe (implausibele) waarde blijft staan, alleen gevlagd, geen sentinel-vervanging:
    assert df.loc[1, "g_ruimteverwarming__m3"] == -89363.0
