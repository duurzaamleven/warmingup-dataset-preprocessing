# SPDX-License-Identifier: EUPL-1.2
"""De enige test die tegen de ECHTE data draait, en de enige plek waar dat gerechtvaardigd is: de
Deflate64-route (``deflate64.py``) kan niet met een synthetische fixture getest worden, omdat
``inflate64`` geen ondersteunde manier biedt om zelf een geldig Deflate64-zip-lid te SCHRIJVEN op een
manier die door willekeurige lezers (waaronder onze eigen ``Deflate64Stream``) als zodanig herkend
wordt. Zie ontwerp-preprocessing.md §7 voor de bredere afweging.

Slaat zichzelf over als ``data/raw/`` (of het archief) ontbreekt, zodat deze test niet breekt op een
machine zonder de (1,8 GB) ruwe dataset."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from warmingup_preprocessing import zipbron as zipbron_mod
from warmingup_preprocessing.deflate64 import open_deflate64

RAW_ZIP = Path("data/raw/data-en-resultaten.zip")

pytestmark = pytest.mark.skipif(not RAW_ZIP.is_file(), reason="data/raw/data-en-resultaten.zip ontbreekt")


def test_thermostat_temp_is_deflate64_in_het_echte_archief():
    with zipbron_mod.ZipBron(RAW_ZIP) as bron:
        info = bron.info(zipbron_mod.THERMOSTAT_TEMP)
        assert info.compress_type == 9


def test_deflate64_leest_eerste_regels_correct():
    with open_deflate64(RAW_ZIP, zipbron_mod.THERMOSTAT_TEMP) as f:
        chunk = next(pd.read_csv(f, chunksize=1000))
    assert list(chunk.columns) == [
        "House", "Time", "Thermostat Desired Temperature (°C)", "Thermostat Measured Temperature (°C)",
    ]
    assert chunk.iloc[0]["House"] == "WU0"
    assert len(chunk) == 1000


def test_deflate64_via_zipbron_open_bron_met_max_bytes():
    with zipbron_mod.ZipBron(RAW_ZIP) as bron:
        with bron.open_bron(zipbron_mod.THERMOSTAT_TEMP, max_bytes=200_000) as stream:
            chunk = next(pd.read_csv(stream, chunksize=10_000))
    assert len(chunk) > 0
    assert (chunk["House"] == "WU0").all()
