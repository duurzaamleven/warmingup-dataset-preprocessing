# SPDX-License-Identifier: EUPL-1.2
"""Losse toets voor de intervalsemantiek van het debiet (ontwerp-preprocessing.md §6).

**De vraag.** Een minuutwaarde in ``debiet__dm3_s_1`` komt uit een pulstelling en dekt dus een
interval: het voorafgaande of het volgende. Dat staat nergens gedocumenteerd. **Toetsbaar**: bij het
aanslaan van de pomp (debiet springt van nul naar positief) loopt het debiet één minuut voor of
achter op de temperatuursprong in ``temp_aanvoer__degC``, afhankelijk van de labeling.

**Wat dit script doet, en wat het niet doet.** Het meet, per pompstart, de vertraging tussen het
moment waarop het debiet van nul naar positief springt en het moment waarop ``temp_aanvoer__degC``
zijn sterkste stijging binnen een klein venster daaromheen heeft. Het RAPPORTEERT de verdeling van
die vertraging, per woning en in totaal; het HERSCHRIJFT ``tijd.py`` niet automatisch.
``tijd.AANNAME_DEBIET_INTERVAL_LABEL`` blijft een bewuste, met de hand aan te passen constante (zie
die module): deze pijplijn doet zelf geen resampling of integratie die van deze aanname afhangt.

Naast alle pompstarts rapporteert het ook de "zuivere" starts: die waarvan het venster uit echt
opeenvolgende minuten bestaat (gevlagde rijen worden voor het zoeken weggelaten, en de bron heeft
gaten en dubbele tijdstempels) en waarvan de sterkste stijging minstens ``DUIDELIJKE_SPRONG__degC``
is (een kleinere stijging is ruis en zegt niets over de labeling).

Gebruik: eerst de hoofdpijplijn draaien zodat er per-woningbestanden onder ``boiler_temp/`` staan,
dan (alleen lezen in ``--uit``):

    python -m warmingup_preprocessing.intervalsemantiek --uit data/processed --steekproef 0 --max-starts 0
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

#: Hoeveel minuten rond een pompstart bekeken worden om de sterkste temperatuurstijging te vinden.
VENSTER__min = 3

#: Een temperatuursprong telt als "duidelijk" vanaf dit verschil tussen twee opeenvolgende minuten. Starts
#: waarvan de sterkste stijging in het venster kleiner is, zeggen niets over de labeling (ruis). Een
#: keuze van deze toets, geen meting.
DUIDELIJKE_SPRONG__degC = 0.5

#: Kolommen die de toets uit een woningbestand nodig heeft; de rest hoeft niet in het geheugen.
_KOLOMMEN = (
    "tijdstip",
    "temp_aanvoer__degC",
    "debiet__dm3_s_1",
    "q_flag_debiet_sentinel__bool",
    "q_flag_debiet_bovengrens__bool",
    "q_flag_temp_aanvoer_bereik__bool",
)


def zoek_pompstarts(df: pd.DataFrame, max_starts: int | None = None, nan_bewust: bool = True) -> pd.DataFrame:
    """De kern van de toets op een al ingelezen, op tijd gesorteerde woningtabel.

    Rijen met een gevlagd debiet of een gevlagde aanvoertemperatuur vallen eerst weg; een pompstart is
    daarna een rij waar het debiet van (ongeveer) nul naar positief springt. Per start één rij met

    * ``vertraging__min``: de minuut van de sterkste temperatuurstijging in het venster min de
      startminuut van het debiet (kan negatief zijn);
    * ``sprong__degC``: die sterkste stijging zelf;
    * ``aaneengesloten__bool``: of de rijen in het venster echt opeenvolgende minuten zijn.

    ``nan_bewust``: een ontbrekende aanvoertemperatuur (de tekst ``x`` in de bron) wordt overgeslagen
    bij het zoeken van de sterkste stijging. Zonder dit wijst ``numpy.argmax`` bij een ``NaN`` in het
    venster de eerste ``NaN`` aan als "sterkste stijging", wat de vertraging naar de plek van het gat
    trekt. Alleen ``nan_bewust=False`` reproduceert de eerste meting op 7 woningen.
    """
    betrouwbaar = ~(
        df["q_flag_debiet_sentinel__bool"]
        | df["q_flag_debiet_bovengrens__bool"]
        | df["q_flag_temp_aanvoer_bereik__bool"]
    )
    df = df.loc[betrouwbaar].reset_index(drop=True)
    was_stil = df["debiet__dm3_s_1"].shift(1).fillna(0) <= 1e-6
    draait_nu = df["debiet__dm3_s_1"] > 1e-6
    starts = df.index[was_stil & draait_nu]
    if max_starts is not None:
        starts = starts[:max_starts]
    temp = df["temp_aanvoer__degC"].to_numpy(dtype="float64")
    minuten = ((df["tijdstip"] - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(minutes=1)).to_numpy()
    rijen = []
    for idx in starts:
        lo = max(0, idx - VENSTER__min)
        hi = min(len(temp), idx + VENSTER__min + 1)
        if hi - lo < 2:
            continue
        deltas = np.diff(temp[lo:hi])
        if nan_bewust:
            if np.isnan(deltas).all():
                continue
            i = int(np.nanargmax(deltas))
        else:
            i = int(np.argmax(deltas))
        # lo + i is de MINUUT VOOR de sterkste stijging; de sprong zelf ligt dus op lo + i + 1.
        # Vertraging = (sprongminuut) - (startminuut van het debiet).
        rijen.append(
            {
                "vertraging__min": (lo + i + 1) - int(idx),
                "sprong__degC": float(deltas[i]),
                "aaneengesloten__bool": bool(minuten[hi - 1] - minuten[lo] == hi - 1 - lo),
            }
        )
    return pd.DataFrame(rijen, columns=["vertraging__min", "sprong__degC", "aaneengesloten__bool"])


def meet_pompstarts_voor_woning(pad: Path, max_starts: int | None = None, nan_bewust: bool = True) -> pd.DataFrame:
    """Lees één woningbestand (``boiler_temp``) en geef per pompstart een rij terug (zie
    :func:`zoek_pompstarts`)."""
    df = pd.read_parquet(pad, columns=list(_KOLOMMEN)).sort_values("tijdstip", kind="stable").reset_index(drop=True)
    return zoek_pompstarts(df, max_starts, nan_bewust)


def meet_vertraging_voor_woning(pad: Path, max_starts: int | None = 200) -> list[int]:
    """De vertragingen (minuten) voor ten hoogste ``max_starts`` pompstarts van één woning."""
    return meet_pompstarts_voor_woning(pad, max_starts=max_starts)["vertraging__min"].tolist()


def _zuiver(starts: pd.DataFrame) -> pd.DataFrame:
    return starts[starts["aaneengesloten__bool"] & (starts["sprong__degC"] >= DUIDELIJKE_SPRONG__degC)]


def _verdeling(vertragingen: pd.Series) -> dict[str, float]:
    """Kerncijfers van een rij vertragingen: aantal, kwartielen en aandelen voor/op/na de start."""
    n = len(vertragingen)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "p25": float(vertragingen.quantile(0.25)),
        "mediaan": float(vertragingen.median()),
        "p75": float(vertragingen.quantile(0.75)),
        "aandeel_voor": float((vertragingen < 0).mean()),
        "aandeel_nul": float((vertragingen == 0).mean()),
        "aandeel_een": float((vertragingen == 1).mean()),
        "aandeel_na": float((vertragingen > 0).mean()),
    }


def toets_interval_labeling(
    uit_dir: Path,
    steekproef: int | None = 10,
    max_starts_per_woning: int | None = 200,
    nan_bewust: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Voer de toets uit op de eerste ``steekproef`` woningen (``None``: alle) en geef terug

    1. een tabel per woning: pompstarts en de verdeling van de vertraging, over alle starts
       (``alle_*``) en over de zuivere starts (``zuiver_*``);
    2. alle pompstarts van alle woningen, lang: ``home_id__str``, ``vertraging__min``,
       ``sprong__degC``, ``aaneengesloten__bool``.
    """
    boiler_map = Path(uit_dir) / "boiler_temp"
    bestanden = sorted(boiler_map.glob("home_id=*.parquet"))
    if steekproef is not None:
        bestanden = bestanden[:steekproef]
    if not bestanden:
        raise FileNotFoundError(f"Geen per-woningbestanden onder {boiler_map}; draai eerst de hoofdpijplijn.")

    rijen = []
    alle: list[pd.DataFrame] = []
    for pad in bestanden:
        home_id = pad.stem.split("=", 1)[-1]
        starts = meet_pompstarts_voor_woning(pad, max_starts=max_starts_per_woning, nan_bewust=nan_bewust)
        starts.insert(0, "home_id__str", home_id)
        alle.append(starts)
        zuiver = _zuiver(starts)
        rij: dict = {"home_id__str": home_id}
        rij.update({f"alle_{k}": v for k, v in _verdeling(starts["vertraging__min"]).items()})
        rij.update({f"zuiver_{k}": v for k, v in _verdeling(zuiver["vertraging__min"]).items()})
        rijen.append(rij)
        log.info("%s: %d pompstart(s), %d zuiver", home_id, len(starts), len(zuiver))

    per_woning = pd.DataFrame(rijen)
    alle_starts = pd.concat(alle, ignore_index=True)
    if alle_starts.empty:
        log.warning("Intervalsemantiek-toets: geen bruikbare pompstarts gevonden in de steekproef.")
    return per_woning, alle_starts


def samenvatting_tekst(per_woning: pd.DataFrame, alle_starts: pd.DataFrame) -> str:
    """Leesbare samenvatting: het totaal en de spreiding van de mediaan over de woningen.

    Negatieve vertraging: de temperatuursprong komt VOOR de geregistreerde debietstart (wijst op
    eindgelabeld debiet); positief: erna (begingelabeld); rond nul: geen van beide duidelijk, of
    momentaan.
    """
    regels = []
    for naam, reeks in (("alle starts", alle_starts), ("zuivere starts", _zuiver(alle_starts))):
        d = _verdeling(reeks["vertraging__min"])
        if d["n"] == 0:
            continue
        histogram = reeks["vertraging__min"].value_counts().sort_index()
        regels.append(
            f"{naam}: {d['n']} pompstart(s) over {reeks['home_id__str'].nunique()} woning(en); "
            f"mediaan {d['mediaan']:.1f} min (p25 {d['p25']:.1f}, p75 {d['p75']:.1f}); "
            f"voor de debietstart {d['aandeel_voor']:.1%}, gelijktijdig {d['aandeel_nul']:.1%}, "
            f"erna {d['aandeel_na']:.1%} (waarvan precies 1 min {d['aandeel_een']:.1%})."
        )
        regels.append("  histogram (vertraging: aantal): " + ", ".join(f"{int(k)}: {v}" for k, v in histogram.items()))
    for voorvoegsel, naam in (("alle", "alle starts"), ("zuiver", "zuivere starts")):
        med = per_woning[f"{voorvoegsel}_mediaan"].dropna()
        if med.empty:
            continue
        regels.append(
            f"mediaan per woning, {naam} ({len(med)} woningen): min {med.min():.1f}, "
            f"p10 {med.quantile(.1):.1f}, p25 {med.quantile(.25):.1f}, mediaan {med.median():.1f}, "
            f"p75 {med.quantile(.75):.1f}, p90 {med.quantile(.9):.1f}, max {med.max():.1f}; "
            f"woningen met mediaan <0: {(med < 0).sum()}, =0: {(med == 0).sum()}, "
            f"=1: {(med == 1).sum()}, >1: {(med > 1).sum()}."
        )
    return "\n".join(regels)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--uit", type=Path, default=Path("data/processed"))
    p.add_argument("--steekproef", type=int, default=10, help="Aantal woningen om te toetsen; 0 betekent alle")
    p.add_argument("--max-starts", type=int, default=200, help="Maximaal aantal pompstarts per woning; 0 betekent alle")
    p.add_argument(
        "--zonder-nan-correctie",
        action="store_true",
        help="Reproduceer de eerste meting (numpy.argmax laat een NaN in het venster winnen)",
    )
    p.add_argument("--csv-dir", type=Path, default=None, help="Schrijf de per-woningtabel en alle pompstarts als CSV hierheen")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(message)s")
    per_woning, alle_starts = toets_interval_labeling(
        args.uit,
        steekproef=args.steekproef or None,
        max_starts_per_woning=args.max_starts or None,
        nan_bewust=not args.zonder_nan_correctie,
    )
    if args.csv_dir is not None:
        args.csv_dir.mkdir(parents=True, exist_ok=True)
        per_woning.to_csv(args.csv_dir / "intervalsemantiek-per-woning.csv", index=False)
        alle_starts.to_csv(args.csv_dir / "intervalsemantiek-pompstarts.csv", index=False)
    with pd.option_context("display.max_rows", None, "display.width", 200):
        print(per_woning.to_string(index=False))
    print(samenvatting_tekst(per_woning, alle_starts))


if __name__ == "__main__":
    main()
