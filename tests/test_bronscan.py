# SPDX-License-Identifier: EUPL-1.2
"""Tests voor de scan op tekstwaarden en sentinels (bronscan.py), op kleine synthetische CSV's."""

from __future__ import annotations

import io

import pytest

from warmingup_preprocessing import bronscan

KOP = "House,Time,Aanvoer,Retour,Flow\n"


def _scan(tekst: str, soorten=("woning", "tijd", "getal", "getal", "getal"), block_size: int = 1 << 20) -> dict:
    data = tekst.encode("utf-8")
    return bronscan.scan_stroom(lambda: io.BytesIO(data), soorten, "synthetisch.csv", block_size=block_size)


def test_telt_tekst_leeg_en_sentinels_per_kolom_en_per_woning():
    rijen = (
        "WU1,2021-01-01T00:00:00Z,20.5,19.0,0\n"
        "WU1,2021-01-01T00:01:00Z,x,19.1,4294967295\n"
        "WU1,2021-01-01T00:02:00Z,x,,12\n"
        "WU2,2021-01-01T00:00:00Z,-40,18.0,0\n"
        "WU2,2021-01-01T00:01:00Z,NaN,18.1,-1\n"
    )
    r = _scan(KOP + rijen)
    assert r["rijen"] == 5
    assert r["woningen"] == 2
    aanvoer, retour, flow = r["kolommen"][2], r["kolommen"][3], r["kolommen"][4]
    assert aanvoer["niet_numeriek"] == 3
    assert aanvoer["niet_numeriek_waarden"] == {"x": 2, "NaN": 1}
    assert aanvoer["sentinelwaarden"] == {"-40.0": 1}
    assert retour["leeg"] == 1 and retour["niet_numeriek"] == 0
    assert flow["sentinelwaarden"] == {"-1.0": 1, "4294967295.0": 1}
    assert flow["maximum"] == 4294967295.0 and flow["minimum"] == -1.0
    assert r["per_woning"]["WU1"]["x2"] == 2 and r["per_woning"]["WU1"]["rijen"] == 3
    assert r["per_woning"]["WU2"]["nn2"] == 1 and r["per_woning"]["WU2"]["x2"] == 0


def test_vormen_vervangen_cijfers_door_negen():
    r = _scan(KOP + "WU1,2021-01-01T00:00:00Z,12.5x,1,1\nWU1,2021-01-01T00:01:00Z,31.1x,1,1\n")
    assert r["kolommen"][2]["niet_numeriek_vormen"] == {"99.9x": 2}


def test_vreemde_tijdstempel_en_woningcode_vallen_op():
    r = _scan(KOP + "WU1,2021-01-01 00:00:00,1,1,1\nhuis7,2021-01-01T00:01:00Z,1,1,1\n")
    assert r["kolommen"][1]["niet_numeriek"] == 1
    assert r["kolommen"][0]["niet_numeriek"] == 1
    assert r["kolommen"][1]["minimum_tekst"] == "2021-01-01T00:01:00Z"


def test_rijen_met_verkeerd_aantal_velden_worden_geteld_niet_stil_genegeerd():
    r = _scan(KOP + "WU1,2021-01-01T00:00:00Z,1,1,1\nWU1,2021-01-01T00:01:00Z,1,1\n")
    assert r["rijen"] == 1
    assert r["rijen_met_afwijkend_aantal_velden"] == 1


def test_telling_is_onafhankelijk_van_de_blokgrootte():
    rijen = "".join(f"WU{i % 3},2021-01-01T00:{i % 60:02d}:00Z,{'x' if i % 7 == 0 else i},1,0\n" for i in range(3000))
    klein = _scan(KOP + rijen, block_size=4096)
    groot = _scan(KOP + rijen)
    for sleutel in ("rijen", "woningen", "per_woning"):
        assert klein[sleutel] == groot[sleutel]
    assert klein["kolommen"][2]["niet_numeriek"] == groot["kolommen"][2]["niet_numeriek"] == len(range(0, 3000, 7))


def test_verkeerd_aantal_kolommen_in_de_kop_is_een_fout():
    with pytest.raises(ValueError):
        _scan("a,b\n1,2\n")
