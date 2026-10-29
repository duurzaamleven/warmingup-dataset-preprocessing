# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pytest

from warmingup_preprocessing import kolommen, tabellen
from warmingup_preprocessing import zipbron as zipbron_mod


def test_resultaten_heeft_precies_de_kolommen_van_het_referentieschema(test_zip_gesorteerd: Path):
    """Versie van 27-10-2026 van de bron: Sheet1 heeft geen logger- en serienummers meer. Elke
    bronkolom (behalve de lege) moet vertaald in resultaten.parquet staan, en niets anders."""
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        resultaten = tabellen.bouw_resultaten(bron)

    assert list(resultaten.columns) == tabellen.RESULTATEN_SCHEMA.names
    assert list(resultaten.columns) == list(kolommen.RESULTATEN_KOLOMMEN.values())
    assert len(resultaten) == 3
    assert resultaten["p_afgifte_geinstalleerd__W"].iloc[0] == pytest.approx(10_000.0)


def test_zip_zonder_mapping_is_een_geldige_bron(test_zip_gesorteerd: Path):
    assert "mapping.csv" not in zipbron_mod.VERPLICHTE_LEDEN
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        assert not hasattr(bron, "lees_mapping")
