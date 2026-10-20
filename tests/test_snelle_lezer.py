# SPDX-License-Identifier: EUPL-1.2
"""Unit tests voor snelle_lezer.py-helpers die niet per se de echte bron nodig hebben (voor de
gelijkheidstoets tegen de pandas-route: zie test_snelle_lezer_gelijkheid.py)."""

from __future__ import annotations

import pyarrow as pa

from warmingup_preprocessing import snelle_lezer


def test_kolom_naar_runs_reduceert_aaneengesloten_herhalingen():
    kolom = pa.array(["A", "A", "A", "B", "B", "C", "A"])
    assert snelle_lezer._kolom_naar_runs(kolom) == ["A", "B", "C", "A"]


def test_kolom_naar_runs_geen_herhalingen():
    kolom = pa.array(["A", "B", "C"])
    assert snelle_lezer._kolom_naar_runs(kolom) == ["A", "B", "C"]


def test_kolom_naar_runs_alles_hetzelfde():
    kolom = pa.array(["A"] * 1000)
    assert snelle_lezer._kolom_naar_runs(kolom) == ["A"]


def test_kolom_naar_runs_leeg():
    kolom = pa.array([], type=pa.string())
    assert snelle_lezer._kolom_naar_runs(kolom) == []


def test_kolom_naar_runs_één_waarde():
    kolom = pa.array(["A"])
    assert snelle_lezer._kolom_naar_runs(kolom) == ["A"]
