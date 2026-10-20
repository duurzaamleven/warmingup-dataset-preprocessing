# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pandas as pd

from warmingup_preprocessing import kwaliteitsrapport


def _schrijf_boiler_temp_tijden(pad: Path, tijden: list[str]) -> None:
    df = pd.DataFrame(
        {
            "home_id__str": ["WU0"] * len(tijden),
            "tijdstip": pd.to_datetime(tijden, utc=True).tz_convert("Europe/Amsterdam"),
        }
    )
    pad.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(pad)


def test_tel_dst_oktobergaten_vindt_het_ontbrekende_tweede_uur(tmp_path: Path):
    # 2021-10-31: normale minuutdata tot en met 00:59 UTC (02:59 CEST), dan een gat tot 02:00 UTC
    # (03:00 CET): het tweede uur (01:00-01:59 UTC) ontbreekt.
    tijden = [f"2021-10-31T{u:02d}:{m:02d}:00Z" for u in (0,) for m in range(60)]
    tijden += ["2021-10-31T02:00:00Z", "2021-10-31T02:01:00Z"]
    pad = tmp_path / "boiler_temp" / "home_id=WU0.parquet"
    _schrijf_boiler_temp_tijden(pad, tijden)

    resultaat = kwaliteitsrapport._tel_dst_oktobergaten(tmp_path)
    assert resultaat["2021-10-31"]["woningen_met_data"] == 1
    assert resultaat["2021-10-31"]["woningen_met_gat"] == 1
    # De andere datum heeft geen bestand met data in dat venster.
    assert resultaat["2022-10-30"]["woningen_met_data"] == 0


def test_tel_dst_oktobergaten_geen_gat_bij_doorlopende_data(tmp_path: Path):
    tijden = [f"2021-10-31T{u:02d}:{m:02d}:00Z" for u in (0, 1, 2, 3) for m in range(60)]
    pad = tmp_path / "boiler_temp" / "home_id=WU0.parquet"
    _schrijf_boiler_temp_tijden(pad, tijden)

    resultaat = kwaliteitsrapport._tel_dst_oktobergaten(tmp_path)
    assert resultaat["2021-10-31"]["woningen_met_data"] == 1
    assert resultaat["2021-10-31"]["woningen_met_gat"] == 0


def test_tel_dst_oktobergaten_geen_map_geeft_leeg_resultaat(tmp_path: Path):
    assert kwaliteitsrapport._tel_dst_oktobergaten(tmp_path) == {}
