# SPDX-License-Identifier: EUPL-1.2
import pandas as pd

from warmingup_preprocessing import tijd


def test_naar_utc_tijdstip():
    kolom = pd.Series(["2021-01-01T00:00:00Z", "2021-06-15T12:30:00Z"])
    resultaat = tijd.naar_utc_tijdstip(kolom)
    assert str(resultaat.dt.tz) == "UTC"
    assert resultaat.iloc[0] == pd.Timestamp("2021-01-01T00:00:00", tz="UTC")


def test_naar_utc_tijdstip_faalt_hard_op_onparseerbare_waarde():
    kolom = pd.Series(["2021-01-01T00:00:00Z", "niet-een-tijdstip"])
    try:
        tijd.naar_utc_tijdstip(kolom)
        assert False, "had moeten falen"
    except ValueError:
        pass


def test_naar_weergave_tijdzone_verandert_instant_niet():
    """Aanvullende eis van de opdrachtgever (23-09-2026): de uitvoer draagt Europe/Amsterdam als
    weergavezone; het instant zelf mag daarbij niet veranderen (zie tijd.TIJDZONE_WEERGAVE)."""
    utc = tijd.naar_utc_tijdstip(pd.Series(["2021-01-01T00:00:00Z", "2021-07-01T12:00:00Z"]))
    weergave = tijd.naar_weergave_tijdzone(utc)
    assert str(weergave.dt.tz) == "Europe/Amsterdam"
    # Zelfde instant: gelijk aan de oorspronkelijke UTC-waarde (pandas vergelijkt tz-aware
    # tijdstempels altijd op het instant, ongeacht de tz-metadata).
    assert (weergave == utc).all()
    # Wintertijd: lokaal is UTC+1, dus het lokale uur ligt 1 hoger dan het UTC-uur.
    assert weergave.iloc[0].hour == 1
    # Zomertijd (1 juli): lokaal is UTC+2.
    assert weergave.iloc[1].hour == 14


def test_naar_lokale_datum_blijft_tekst():
    kolom = pd.Series(["2021-01-01", "2021-06-15"])
    resultaat = tijd.naar_lokale_datum(kolom)
    assert list(resultaat) == ["2021-01-01", "2021-06-15"]


def test_etmaalgrens_utc_wintertijd():
    # Lokale middernacht in de winter is UTC+1, dus 23:00 UTC de dag ervoor.
    begin, eind = tijd.etmaalgrens_utc("2021-01-15")
    assert begin == pd.Timestamp("2021-01-14T23:00:00", tz="UTC")
    assert (eind - begin) == pd.Timedelta(hours=24)


def test_etmaalgrens_utc_zomertijdovergang_is_23_uur():
    # De overgang naar zomertijd 2021 was in de nacht van 27 op 28 maart.
    begin, eind = tijd.etmaalgrens_utc("2021-03-28")
    assert (eind - begin) == pd.Timedelta(hours=23)


def test_etmaalgrens_utc_wintertijdovergang_is_25_uur():
    # De overgang naar wintertijd 2021 was in de nacht van 30 op 31 oktober.
    begin, eind = tijd.etmaalgrens_utc("2021-10-31")
    assert (eind - begin) == pd.Timedelta(hours=25)
