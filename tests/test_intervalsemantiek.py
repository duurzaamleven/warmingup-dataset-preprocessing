# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de intervalsemantiek-toets (intervalsemantiek.py) op een synthetische woning."""

from __future__ import annotations

import numpy as np
import pandas as pd

from warmingup_preprocessing import intervalsemantiek as iv


def _woning(debiet: list[float], temp: list[float], tijdstippen=None) -> pd.DataFrame:
    n = len(debiet)
    if tijdstippen is None:
        tijdstippen = pd.date_range("2021-01-01", periods=n, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "tijdstip": tijdstippen,
            "temp_aanvoer__degC": temp,
            "debiet__dm3_s_1": debiet,
            "q_flag_debiet_sentinel__bool": False,
            "q_flag_debiet_bovengrens__bool": False,
            "q_flag_temp_aanvoer_bereik__bool": False,
        }
    )


def test_temperatuursprong_een_minuut_na_de_debietstart_geeft_vertraging_een():
    debiet = [0, 0, 0, 0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    temp = [20, 20, 20, 20, 20, 30, 31, 31, 31, 31]
    res = iv.zoek_pompstarts(_woning(debiet, temp))
    assert res["vertraging__min"].tolist() == [1]
    assert res["aaneengesloten__bool"].tolist() == [True]
    assert res["sprong__degC"].tolist() == [10.0]


def test_een_ontbrekende_temperatuur_wint_niet_van_de_echte_sprong():
    debiet = [0, 0, 0, 0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    temp = [20, 20, np.nan, 20, 20, 30, 31, 31, 31, 31]
    assert iv.zoek_pompstarts(_woning(debiet, temp))["vertraging__min"].tolist() == [1]
    # zonder correctie trekt numpy.argmax naar de eerste NaN (twee minuten voor de start (de NaN-delta))
    assert iv.zoek_pompstarts(_woning(debiet, temp), nan_bewust=False)["vertraging__min"].tolist() == [-2]


def test_een_gat_in_de_tijd_maakt_het_venster_niet_aaneengesloten():
    debiet = [0, 0, 0, 0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    temp = [20, 20, 20, 20, 20, 30, 31, 31, 31, 31]
    tijden = list(pd.date_range("2021-01-01", periods=10, freq="min", tz="UTC"))
    tijden[6:] = [t + pd.Timedelta(minutes=5) for t in tijden[6:]]
    res = iv.zoek_pompstarts(_woning(debiet, temp, tijden))
    assert res["aaneengesloten__bool"].tolist() == [False]


def test_gevlagde_rijen_tellen_niet_mee_en_zuivere_starts_eisen_een_duidelijke_sprong():
    debiet = [0, 0, 0, 0, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    temp = [20, 20, 20, 20, 20, 20.1, 20.1, 20.1, 20.1, 20.1]
    res = iv.zoek_pompstarts(_woning(debiet, temp))
    assert len(res) == 1
    assert iv._zuiver(res).empty  # sprong van 0,1 graad is ruis

    df = _woning(debiet, temp)
    df["q_flag_debiet_sentinel__bool"] = True
    assert iv.zoek_pompstarts(df).empty


def test_verdeling_geeft_aandelen_voor_op_en_na_de_start():
    d = iv._verdeling(pd.Series([-1, 0, 1, 1, 2]))
    assert d["n"] == 5 and d["mediaan"] == 1.0
    assert d["aandeel_voor"] == 0.2 and d["aandeel_nul"] == 0.2 and d["aandeel_na"] == 0.6
    assert d["aandeel_een"] == 0.4
    assert iv._verdeling(pd.Series([], dtype=float)) == {"n": 0}
