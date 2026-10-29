# SPDX-License-Identifier: EUPL-1.2
"""De kleine, in-memory tabellen: etmaalstatistiek, resultatentabel, info-metadata
(ontwerp-preprocessing.md §2). ``boiler-24h-stats.csv`` is met ~200.000 rijen en 11 MB streamend
gelezen maar in één geheel weggeschreven; de andere twee passen ruim in het geheugen (212 rijen en
enkele tientallen regels).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from . import kolommen, sentinels, tijd
from . import zipbron as zipbron_mod

ETMAAL_SCHEMA = pa.schema(
    [
        ("home_id__str", pa.string()),
        ("datum__str", pa.string()),
        ("g_tapwater__m3", pa.float32()),
        ("g_ruimteverwarming__m3", pa.float32()),
        ("t_brander_tapwater__h", pa.float32()),
        ("t_brander_verwarming__h", pa.float32()),
        ("p_cv_min__Pa", pa.float32()),
        ("p_cv_gem__Pa", pa.float32()),
        ("p_cv_max__Pa", pa.float32()),
        ("q_flag_gas_ruimteverwarming_bereik__bool", pa.bool_()),
        ("q_flag_gas_tapwater_bereik__bool", pa.bool_()),
        ("q_flag_brander_verwarming_bereik__bool", pa.bool_()),
        ("q_flag_brander_tapwater_bereik__bool", pa.bool_()),
        ("q_flag_druk_min_onbekend__bool", pa.bool_()),
        ("q_flag_druk_gem_onbekend__bool", pa.bool_()),
        ("q_flag_druk_max_onbekend__bool", pa.bool_()),
    ]
)


def _transformeer_etmaal_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    chunk = chunk.rename(columns=kolommen.BOILER_24H_STATS_KOLOMMEN)
    chunk["datum__str"] = tijd.naar_lokale_datum(chunk["datum__str"])
    chunk = sentinels.flag_boiler_24h_stats(chunk)
    for kolom in ("p_cv_min__bar", "p_cv_gem__bar", "p_cv_max__bar"):
        nieuw = kolom.replace("__bar", "__Pa")
        chunk[nieuw] = kolommen.bar_naar_pa(chunk[kolom]).astype("float32")
    for kolom in ("g_tapwater__m3", "g_ruimteverwarming__m3", "t_brander_tapwater__h", "t_brander_verwarming__h"):
        chunk[kolom] = chunk[kolom].astype("float32")
    return chunk


def bouw_etmaal(
    bron,
    uit_pad: Path,
    chunksize: int = 100_000,
    max_bytes: int | None = None,
    op_voortgang=None,
) -> int:
    """Schrijf ``boiler-24h-stats.csv`` streamend naar ``uit_pad`` (één Parquet-bestand, geen
    per-woning-opsplitsing: dit is met ~200.000 rijen klein genoeg, en het is per definitie een
    tabel met alle woningen samen, ontwerp §2)."""
    tmp = uit_pad.with_suffix(uit_pad.suffix + ".tmp")
    rijen_totaal = 0
    with bron.open_bron(zipbron_mod.BOILER_24H_STATS, max_bytes=max_bytes, op_voortgang=op_voortgang) as stream:
        writer: pq.ParquetWriter | None = None
        try:
            for chunk in zipbron_mod.lees_csv_in_chunks(stream, chunksize=chunksize):
                chunk = _transformeer_etmaal_chunk(chunk)
                tabel = pa.Table.from_pandas(chunk, preserve_index=False).select(ETMAAL_SCHEMA.names).cast(ETMAAL_SCHEMA)
                if writer is None:
                    writer = pq.ParquetWriter(tmp, ETMAAL_SCHEMA, compression="zstd")
                writer.write_table(tabel)
                rijen_totaal += len(chunk)
        finally:
            if writer is not None:
                writer.close()
    if rijen_totaal == 0:
        # --test met een heel kleine max_bytes kan in theorie 0 rijen opleveren; schrijf dan toch
        # een geldig leeg bestand met het juiste schema, zodat downstream-code niet struikelt.
        pq.write_table(pa.Table.from_arrays([[] for _ in ETMAAL_SCHEMA], schema=ETMAAL_SCHEMA), tmp, compression="zstd")
    tmp.replace(uit_pad)
    return rijen_totaal


#: Referentieschema's voor de twee kleine tabellen hieronder, gebruikt door ``datapackage.py`` (niet
#: door het schrijfpad zelf: ``bouw_resultaten``/``bouw_info_metadata`` laten
#: ``schrijf_parquet_atomisch`` het Parquet-type nog steeds uit de pandas-dtypes afleiden, zoals
#: altijd). Getypeerd naar wat de echte volledige-run-uitvoer daadwerkelijk heeft (geverifieerd op de
#: uitvoermap van de eerste volledige run, 23-09-2026, met ``pyarrow.parquet.ParquetFile``):
#: ``pandas.to_parquet`` schrijft een tekstkolom als
#: ``large_string``; hier ``pa.string()`` gebruikt (Frictionless/Table Schema kennen het onderscheid
#: sowieso niet, beide zijn daar gewoon "string"), zodat dit bestand niet zelf een Arrow-specifieke
#: keuze hoeft te documenteren die niets met de kolombetekenis te maken heeft.
RESULTATEN_SCHEMA = pa.schema(
    [
        ("resultaat_volgnummer__int", pa.int64()),
        ("home_id__str", pa.string()),
        ("model_training_fout__onbekend", pa.float64()),
        ("model_validatie_fout__onbekend", pa.float64()),
        ("model_training_bias__onbekend", pa.float64()),
        ("model_validatie_bias__onbekend", pa.float64()),
        ("p_ontwerp__W", pa.float64()),
        ("c_binnen__J_K_1", pa.float64()),
        ("r_binnen_schil__K_W_1", pa.float64()),
        ("a_raam_effectief__m2", pa.float64()),
        ("c_schil__J_K_1", pa.float64()),
        ("r_schil_buiten__K_W_1", pa.float64()),
        ("temp_aanvoer_min__degC", pa.float64()),
        ("temp_retour_min__degC", pa.float64()),
        ("woningtype__cat", pa.string()),
        ("bouwjaar_klasse__cat", pa.string()),
        ("bouwjaar_klasse_eindrapport__cat", pa.string()),
        ("oppervlak_klasse__cat", pa.string()),
        ("g_jaarverbruik_indicatief__m3", pa.float64()),
        ("p_afgifte_geinstalleerd__W", pa.float64()),
        ("overdimensionering__frac", pa.float64()),
    ]
)

INFO_METADATA_SCHEMA = pa.schema(
    [
        ("regel__int", pa.int64()),
        ("tekst__str", pa.string()),
    ]
)


def bouw_resultaten(bron) -> pd.DataFrame:
    """De resultatentabel (blad ``Sheet1``): 2R2C-parameters, ontwerpvermogen, geïnstalleerd
    radiatorvermogen, woningkenmerken (ontwerp-preprocessing.md §2)."""
    ruw = bron.lees_resultaten_ruw()
    ruw = ruw.drop(columns=[kolommen.RESULTATEN_GENEGEERDE_KOLOM], errors="ignore")
    for kolom in kolommen.RESULTATEN_KW_NAAR_W:
        if kolom in ruw.columns:
            ruw[kolom] = ruw[kolom] * 1000.0
    df = ruw.rename(columns=kolommen.RESULTATEN_KOLOMMEN)
    aanwezig = [c for c in kolommen.RESULTATEN_KOLOMMEN.values() if c in df.columns]
    return df[aanwezig]


def bouw_info_metadata(bron) -> pd.DataFrame:
    """Het ``info``-blad van de resultatentabel, als kleine tekstuele metadata-tabel: één rij per
    niet-lege regel, met de tekst zoals hij in de bron staat (geen interpretatie, geen vertaling:
    dit is provenance, geen meetgrootheid)."""
    ruw = bron.lees_info_blad_ruw()
    rijen = []
    for idx, row in ruw.iterrows():
        waarden = [str(v) for v in row.tolist() if pd.notna(v)]
        if waarden:
            rijen.append({"regel__int": idx, "tekst__str": " | ".join(waarden)})
    return pd.DataFrame(rijen, columns=["regel__int", "tekst__str"])
