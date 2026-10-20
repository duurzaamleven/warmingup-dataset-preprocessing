# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from warmingup_preprocessing import dekking
from warmingup_preprocessing.pijplijn import BOILER_TEMP_SCHEMA, THERMOSTAT_TEMP_SCHEMA


def _schrijf_boiler_temp_bestand(pad: Path, dubbel_vlag: list[bool]) -> None:
    n = len(dubbel_vlag)
    tijden = pd.date_range("2021-01-01", periods=n, freq="min", tz="UTC")
    df = pd.DataFrame(
        {
            "home_id__str": ["WU0"] * n,
            "tijdstip": tijden,
            "temp_aanvoer__degC": [40.0] * n,
            "temp_retour__degC": [30.0] * n,
            "debiet_ruw__l_h": [300.0] * n,
            "debiet__dm3_s_1": [300.0 / 3600.0] * n,
            "q_afgifte__W": [100.0] * n,
            "q_flag_debiet_sentinel__bool": [False] * n,
            "q_flag_debiet_bovengrens__bool": [False] * n,
            "q_flag_temp_aanvoer_ontbrekend__bool": [False] * n,
            "q_flag_temp_retour_ontbrekend__bool": [False] * n,
            "q_flag_temp_aanvoer_bereik__bool": [False] * n,
            "q_flag_temp_retour_bereik__bool": [False] * n,
            "q_flag_tijdstip_dubbel__bool": dubbel_vlag,
        }
    )
    tabel = pa.Table.from_pandas(df, preserve_index=False).select(BOILER_TEMP_SCHEMA.names).cast(BOILER_TEMP_SCHEMA)
    pad.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(tabel, pad, compression="zstd")


def test_dekking_telt_dubbele_tijdstippen_uit_de_vlagkolom(tmp_path: Path):
    """De telling in dekking.parquet moet uit dezelfde bron komen als de per-rij-vlag: geen tweede,
    onafhankelijke berekening die uit de pas kan lopen (zie dekking._dubbele_tijdstippen)."""
    uit_dir = tmp_path
    _schrijf_boiler_temp_bestand(
        uit_dir / "boiler_temp" / "home_id=WU0.parquet",
        [False, False, True, False, True, True],  # 3 dubbelingen
    )
    df = dekking.bouw_dekking(uit_dir)
    assert len(df) == 1
    assert df.iloc[0]["dubbele_tijdstippen__int"] == 3
    assert df.iloc[0]["rijen__int"] == 6


def test_dekking_valt_terug_op_sort_based_telling_zonder_vlagkolom(tmp_path: Path):
    """Oudere uitvoer (vóór deze vlag bestond) heeft de kolom niet; dekking.py moet dan nog steeds
    werken, met de eerdere, wiskundig gelijke berekeningswijze."""
    n = 4
    tijden = list(pd.date_range("2021-01-01", periods=n, freq="min", tz="UTC")) + [
        pd.Timestamp("2021-01-01", tz="UTC")
    ]  # expliciete dubbeling van de eerste minuut, geen vlagkolom aanwezig
    df = pd.DataFrame({"home_id__str": ["WU0"] * len(tijden), "tijdstip": tijden})
    pad = tmp_path / "boiler_temp" / "home_id=WU0.parquet"
    pad.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(pad)
    resultaat = dekking.bouw_dekking(tmp_path)
    assert resultaat.iloc[0]["dubbele_tijdstippen__int"] == 1
