# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pandas as pd

from warmingup_preprocessing import tabellen
from warmingup_preprocessing import zipbron as zipbron_mod


def test_resultaten_logger_id_is_string_zonder_punt0(test_zip_gesorteerd: Path):
    """logger_id__str moet in resultaten.parquet net als in mapping.parquet een string zijn, zonder
    ".0"-artefact (pandas.read_excel infereert deze kolom als getal); geverifieerd op de echte
    volledige-run-uitvoer dat resultaten.parquet hier eerder int64 had, zie VOORTGANG.md."""
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        resultaten = tabellen.bouw_resultaten(bron)
        mapping = tabellen.bouw_mapping(bron)

    assert resultaten["logger_id__str"].dtype == object or pd.api.types.is_string_dtype(resultaten["logger_id__str"])
    assert mapping["logger_id__str"].dtype == object or pd.api.types.is_string_dtype(mapping["logger_id__str"])
    for waarde in resultaten["logger_id__str"]:
        assert isinstance(waarde, str)
        assert not waarde.endswith(".0")
