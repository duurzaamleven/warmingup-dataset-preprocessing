# SPDX-License-Identifier: EUPL-1.2
from pathlib import Path

import pandas as pd
import pytest

from warmingup_preprocessing import kolommen, schrijvers, sentinels, tijd
from warmingup_preprocessing import zipbron as zipbron_mod
from warmingup_preprocessing.manifest import Manifest
from warmingup_preprocessing.pijplijn import (
    BOILER_TEMP_KOLOM_TYPES_PYARROW,
    BOILER_TEMP_SCHEMA,
    THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW,
    THERMOSTAT_TEMP_SCHEMA,
)

#: Beide lezers moeten hetzelfde gedrag vertonen (ontwerp-preprocessing.md §8); de meeste tests in dit
#: bestand draaien daarom voor allebei. De echte bit-voor-bit-gelijkheidstoets, met "x", lege velden,
#: sentinels en een zomertijddag, staat in ``test_snelle_lezer_gelijkheid.py``.
LEZERS = ("pandas", "pyarrow")


@pytest.mark.parametrize("lezer", LEZERS)
def test_controleer_aaneengesloten_true(test_zip_gesorteerd: Path, lezer):
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        assert schrijvers.controleer_aaneengesloten(bron, zipbron_mod.BOILER_TEMP, lezer=lezer) is True


@pytest.mark.parametrize("lezer", LEZERS)
def test_controleer_aaneengesloten_false(test_zip_ongesorteerd: Path, lezer):
    with zipbron_mod.ZipBron(test_zip_ongesorteerd) as bron:
        assert schrijvers.controleer_aaneengesloten(bron, zipbron_mod.BOILER_TEMP, lezer=lezer) is False


def _schrijf_boiler_temp(bron, uit_dir: Path, manifest: Manifest, functie, lezer: str = "pandas", block_size: int = 1 << 20):
    kwargs = dict(
        bron=bron,
        bestandsnaam=zipbron_mod.BOILER_TEMP,
        kolommen_map=kolommen.BOILER_TEMP_KOLOMMEN,
        tijdstip_naar_utc=tijd.naar_utc_tijdstip,
        flag_fn=sentinels.flag_boiler_temp,
        schema=BOILER_TEMP_SCHEMA,
        uit_dir=uit_dir,
        onderdeel="boiler_temp",
        manifest=manifest,
        chunksize=7,  # klein, om chunkgrenzen midden in een woning te forceren (pandas-route)
        dtype_ruw={"House": str},
    )
    if functie is schrijvers.schrijf_per_woning_gesorteerd:
        # schrijf_per_woning_ongesorteerd blijft pandas-only (zie schrijvers.py); alleen de
        # gesorteerde route kent de lezer-keuze.
        kwargs.update(
            lezer=lezer,
            kolom_types_pyarrow=BOILER_TEMP_KOLOM_TYPES_PYARROW if lezer == "pyarrow" else None,
            block_size=block_size,
        )
    return functie(**kwargs)


@pytest.mark.parametrize("lezer", LEZERS)
def test_schrijf_per_woning_gesorteerd(test_zip_gesorteerd: Path, tmp_path: Path, lezer):
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        manifest = Manifest(uit_dir)
        resultaat = _schrijf_boiler_temp(bron, uit_dir, manifest, schrijvers.schrijf_per_woning_gesorteerd, lezer)

    assert set(resultaat.keys()) == {"WU0", "WU1", "WU2"}
    for home, n in resultaat.items():
        pad = uit_dir / "boiler_temp" / f"home_id={home}.parquet"
        assert pad.is_file()
        df = pd.read_parquet(pad)
        assert len(df) == n
        assert (df["home_id__str"] == home).all()
        assert manifest.is_voltooid("boiler_temp", home, uit_dir)


@pytest.mark.parametrize("lezer", LEZERS)
def test_schrijf_per_woning_gesorteerd_hervat(test_zip_gesorteerd: Path, tmp_path: Path, lezer):
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        manifest = Manifest(uit_dir)
        eerste = _schrijf_boiler_temp(bron, uit_dir, manifest, schrijvers.schrijf_per_woning_gesorteerd, lezer)
    assert len(eerste) == 3

    # Tweede aanroep met een VERS Manifest-object (zoals bij een herstart) dat het bestaande
    # manifestbestand inleest: alle drie de woningen moeten nu overgeslagen worden.
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        manifest2 = Manifest(uit_dir)
        tweede = _schrijf_boiler_temp(bron, uit_dir, manifest2, schrijvers.schrijf_per_woning_gesorteerd, lezer)
    assert tweede == {}


@pytest.mark.parametrize("lezer", LEZERS)
def test_schrijf_per_woning_gesorteerd_faalt_op_ongesorteerde_bron(test_zip_ongesorteerd: Path, tmp_path: Path, lezer):
    uit_dir = tmp_path / "uit"
    # Klein blok/kleine chunksize, om chunk-/batchgrenzen midden in de verweving te forceren: zonder
    # dit past het hele (kleine) testbestand in één stuk, en zou de interleaving binnen dat ene stuk
    # onzichtbaar zijn (``groupby`` voegt sowieso alle rijen van een woning samen, ongeacht hun
    # volgorde; de SorteerFout-detectie werkt alleen over stuk-grenzen heen, zie ``schrijvers.py``).
    block_size = 150 if lezer == "pyarrow" else 1 << 20
    with zipbron_mod.ZipBron(test_zip_ongesorteerd) as bron:
        manifest = Manifest(uit_dir)
        with pytest.raises(schrijvers.SorteerFout):
            _schrijf_boiler_temp(bron, uit_dir, manifest, schrijvers.schrijf_per_woning_gesorteerd, lezer, block_size)


def test_schrijf_per_woning_ongesorteerd(test_zip_ongesorteerd: Path, tmp_path: Path):
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(test_zip_ongesorteerd) as bron:
        manifest = Manifest(uit_dir)
        resultaat = _schrijf_boiler_temp(bron, uit_dir, manifest, schrijvers.schrijf_per_woning_ongesorteerd)

    assert set(resultaat.keys()) == {"WU0", "WU1"}
    for home, n in resultaat.items():
        pad = uit_dir / "boiler_temp" / f"home_id={home}.parquet"
        df = pd.read_parquet(pad)
        assert len(df) == n
        assert manifest.is_voltooid("boiler_temp", home, uit_dir)
    # De tijdelijke deelbestanden zijn opgeruimd na het compacteren.
    assert not (uit_dir / "_tijdelijk" / "boiler_temp").exists()


def test_schrijf_per_woning_ongesorteerd_hervat(test_zip_ongesorteerd: Path, tmp_path: Path):
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(test_zip_ongesorteerd) as bron:
        manifest = Manifest(uit_dir)
        eerste = _schrijf_boiler_temp(bron, uit_dir, manifest, schrijvers.schrijf_per_woning_ongesorteerd)
    assert len(eerste) == 2

    with zipbron_mod.ZipBron(test_zip_ongesorteerd) as bron:
        manifest2 = Manifest(uit_dir)
        tweede = _schrijf_boiler_temp(bron, uit_dir, manifest2, schrijvers.schrijf_per_woning_ongesorteerd)
    assert tweede == {}


@pytest.mark.parametrize("lezer", LEZERS)
def test_rijen_gelezen_blijft_niet_0_bij_hervatting_met_alleen_voltooide_woningen(
    test_zip_gesorteerd: Path, tmp_path: Path, lezer
):
    """Regressietoets voor VOORTGANG.md, "Eerste volledige run", punt 1: bij lezer="pyarrow" bleef
    rijen_gelezen in _voortgang.json op 0 staan zolang een hervatte run alleen al voltooide woningen
    aan het overslaan was, omdat de Arrow-batches die daardoor volledig wegvielen nooit ge-yield
    werden en de rijenteller alleen ge-yielde chunks optelde. Hier: eerst volledig schrijven, dan
    met een VERS Manifest (dus alle drie de woningen al "af") opnieuw aanroepen en controleren dat
    de op_voortgang-callback toch het volledige, ongefilterde aantal bronrijen rapporteert."""
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        manifest = Manifest(uit_dir)
        _schrijf_boiler_temp(bron, uit_dir, manifest, schrijvers.schrijf_per_woning_gesorteerd, lezer)

    gerapporteerde_rijen: list[int] = []

    def _op_voortgang(bytes_gelezen: int, rijen_gelezen: int) -> None:
        gerapporteerde_rijen.append(rijen_gelezen)

    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        manifest2 = Manifest(uit_dir)
        kwargs = dict(
            bron=bron,
            bestandsnaam=zipbron_mod.BOILER_TEMP,
            kolommen_map=kolommen.BOILER_TEMP_KOLOMMEN,
            tijdstip_naar_utc=tijd.naar_utc_tijdstip,
            flag_fn=sentinels.flag_boiler_temp,
            schema=BOILER_TEMP_SCHEMA,
            uit_dir=uit_dir,
            onderdeel="boiler_temp",
            manifest=manifest2,
            chunksize=7,
            dtype_ruw={"House": str},
            op_voortgang=_op_voortgang,
            lezer=lezer,
        )
        if lezer == "pyarrow":
            kwargs["kolom_types_pyarrow"] = BOILER_TEMP_KOLOM_TYPES_PYARROW
            kwargs["block_size"] = 200  # klein: meerdere Arrow-batches, ook al vallen ze allemaal weg
        resultaat = schrijvers.schrijf_per_woning_gesorteerd(**kwargs)

    assert resultaat == {}  # alle drie de woningen al voltooid: niets nieuws geschreven
    assert gerapporteerde_rijen, "op_voortgang is niet aangeroepen"
    # 3 woningen x 15 rijen (zie test_zip_gesorteerd in conftest.py) = 45 bronrijen; de teller moet
    # dat volledige, RUWE aantal bereiken, niet op 0 blijven staan.
    assert max(gerapporteerde_rijen) == 45


@pytest.mark.parametrize("lezer", LEZERS)
def test_thermostat_temp_gesorteerd(test_zip_gesorteerd: Path, tmp_path: Path, lezer):
    uit_dir = tmp_path / "uit"
    with zipbron_mod.ZipBron(test_zip_gesorteerd) as bron:
        manifest = Manifest(uit_dir)
        resultaat = schrijvers.schrijf_per_woning_gesorteerd(
            bron=bron,
            bestandsnaam=zipbron_mod.THERMOSTAT_TEMP,
            kolommen_map=kolommen.THERMOSTAT_TEMP_KOLOMMEN,
            tijdstip_naar_utc=tijd.naar_utc_tijdstip,
            flag_fn=sentinels.flag_thermostat_temp,
            schema=THERMOSTAT_TEMP_SCHEMA,
            uit_dir=uit_dir,
            onderdeel="thermostat_temp",
            manifest=manifest,
            dtype_ruw={"House": str},
            lezer=lezer,
            kolom_types_pyarrow=THERMOSTAT_TEMP_KOLOM_TYPES_PYARROW if lezer == "pyarrow" else None,
        )
    assert set(resultaat.keys()) == {"WU0", "WU1", "WU2"}
