# SPDX-License-Identifier: EUPL-1.2
"""Integratietests voor ``q_flag_tijdstip_dubbel__bool``: dubbele tijdstempels worden gevlagd, niet
verwijderd, en de detectie klopt ook als een dubbeling niet op de vorige rij volgt maar verderop in
het bestand terugkomt (de bron is niet op tijd gesorteerd binnen een woning, zie
``sentinels.flag_tijdstip_dubbel``). Kleine chunk-/blokgroottes forceren dat zo'n dubbeling over een
chunk-/batchgrens heen valt, zodat dit niet per ongeluk alleen "toevallig" binnen één chunk werkt.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd
import pytest

from tests.conftest import bouw_test_zip
from warmingup_preprocessing import kolommen, schrijvers, sentinels, tijd
from warmingup_preprocessing import zipbron as zipbron_mod
from warmingup_preprocessing.manifest import Manifest
from warmingup_preprocessing.pijplijn import BOILER_TEMP_KOLOM_TYPES_PYARROW, BOILER_TEMP_SCHEMA

BOILER_TEMP_KOP = "House,Time,Boiler Water Supply Temperature (°C),Boiler Water Return Temperature (°C),Flow (l/h)"

#: Bewust NIET op tijd gesorteerd: t0 komt na t3 nog een keer terug (3 rijen later), t1 na t4 nog een
#: keer (4 rijen later). Verwachte vlag: [False, False, False, True, False, True, False].
_TIJDEN = [
    "2021-01-01T00:00:00Z",  # t0, eerste keer -> False
    "2021-01-01T00:01:00Z",  # t1, eerste keer -> False
    "2021-01-01T00:02:00Z",  # t2, eerste keer -> False
    "2021-01-01T00:00:00Z",  # t0 opnieuw        -> True
    "2021-01-01T00:03:00Z",  # t3, eerste keer -> False
    "2021-01-01T00:01:00Z",  # t1 opnieuw        -> True
    "2021-01-01T00:04:00Z",  # t4, eerste keer -> False
]
_VERWACHTE_VLAG = [False, False, False, True, False, True, False]


def _regels(home: str) -> list[str]:
    return [f"{home},{t},40.00,30.00,300" for t in _TIJDEN]


@pytest.fixture
def zip_met_teruggesprongen_tijdstempels(tmp_path: Path) -> Path:
    basis = bouw_test_zip(tmp_path / "basis.zip", ["WU0", "WU1"], rijen_per_woning=5)
    with zipfile.ZipFile(basis) as z:
        leden = {naam: z.read(naam) for naam in z.namelist()}
    inhoud = BOILER_TEMP_KOP + "\n" + "\n".join(_regels("WU0") + _regels("WU1")) + "\n"
    leden["boiler-temp.csv"] = inhoud.encode("utf-8")
    pad = tmp_path / "teruggesprongen.zip"
    with zipfile.ZipFile(pad, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for naam, data in leden.items():
            z.writestr(naam, data)
    return pad


@pytest.mark.parametrize("lezer", ["pandas", "pyarrow"])
def test_dubbele_tijdstempels_over_chunkgrenzen_heen_gesorteerde_route(
    zip_met_teruggesprongen_tijdstempels: Path, tmp_path: Path, lezer
):
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(zip_met_teruggesprongen_tijdstempels) as bron:
        manifest = Manifest(uit_dir)
        schrijvers.schrijf_per_woning_gesorteerd(
            bron=bron,
            bestandsnaam=zipbron_mod.BOILER_TEMP,
            kolommen_map=kolommen.BOILER_TEMP_KOLOMMEN,
            tijdstip_naar_utc=tijd.naar_utc_tijdstip,
            flag_fn=sentinels.flag_boiler_temp,
            schema=BOILER_TEMP_SCHEMA,
            uit_dir=uit_dir,
            onderdeel="boiler_temp",
            manifest=manifest,
            chunksize=2,  # klein: forceert dat de dubbeling (3 en 4 rijen verderop) een chunkgrens kruist
            dtype_ruw={"House": str},
            lezer=lezer,
            kolom_types_pyarrow=BOILER_TEMP_KOLOM_TYPES_PYARROW if lezer == "pyarrow" else None,
            block_size=200 if lezer == "pyarrow" else schrijvers.snelle_lezer.BLOCK_SIZE_STANDAARD,
        )

    for home in ("WU0", "WU1"):
        df = pd.read_parquet(uit_dir / "boiler_temp" / f"home_id={home}.parquet")
        assert df["q_flag_tijdstip_dubbel__bool"].tolist() == _VERWACHTE_VLAG, (home, lezer)
        # De rijen zelf blijven staan (vlaggen, niet verwijderen): 7 rijen, niet 5.
        assert len(df) == len(_TIJDEN)
        # Weergavezone Europe/Amsterdam, maar het instant moet exact het bronmoment blijven (zie
        # tijd.naar_weergave_tijdzone: tz_convert verandert het instant niet).
        assert str(df["tijdstip"].dt.tz) == "Europe/Amsterdam"
        assert df["tijdstip"].iloc[0] == pd.Timestamp(_TIJDEN[0])


def test_dubbele_tijdstempels_ongesorteerde_route(tmp_path: Path):
    """De ongesorteerde (scatter/compacteer) route verwerkt de twee woningen dooreengeweven; de
    dedupdetectie moet toch per woning, in bronvolgorde, de juiste rijen vlaggen."""
    homes = ["WU0", "WU1"]
    basis = bouw_test_zip(tmp_path / "basis.zip", homes, rijen_per_woning=5)
    with zipfile.ZipFile(basis) as z:
        leden = {naam: z.read(naam) for naam in z.namelist()}

    # Verweef WU0 en WU1 regel voor regel (expliciet NIET aaneengesloten), zodat de ongesorteerde
    # route gekozen wordt.
    regels_wu0 = _regels("WU0")
    regels_wu1 = _regels("WU1")
    verweven = [r for paar in zip(regels_wu0, regels_wu1) for r in paar]
    inhoud = BOILER_TEMP_KOP + "\n" + "\n".join(verweven) + "\n"
    leden["boiler-temp.csv"] = inhoud.encode("utf-8")
    pad = tmp_path / "verweven.zip"
    with zipfile.ZipFile(pad, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for naam, data in leden.items():
            z.writestr(naam, data)

    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(pad) as bron:
        manifest = Manifest(uit_dir)
        assert schrijvers.controleer_aaneengesloten(bron, zipbron_mod.BOILER_TEMP) is False

    with zipbron_mod.ZipBron(pad) as bron:
        manifest = Manifest(uit_dir)
        schrijvers.schrijf_per_woning_ongesorteerd(
            bron=bron,
            bestandsnaam=zipbron_mod.BOILER_TEMP,
            kolommen_map=kolommen.BOILER_TEMP_KOLOMMEN,
            tijdstip_naar_utc=tijd.naar_utc_tijdstip,
            flag_fn=sentinels.flag_boiler_temp,
            schema=BOILER_TEMP_SCHEMA,
            uit_dir=uit_dir,
            onderdeel="boiler_temp",
            manifest=manifest,
            chunksize=3,  # klein: meerdere chunks, elke chunk bevat beide woningen dooreen
            dtype_ruw={"House": str},
        )

    for home in homes:
        df = pd.read_parquet(uit_dir / "boiler_temp" / f"home_id={home}.parquet")
        assert df["q_flag_tijdstip_dubbel__bool"].tolist() == _VERWACHTE_VLAG, home
        assert len(df) == len(_TIJDEN)
