# SPDX-License-Identifier: EUPL-1.2
"""datapackage.json wordt UIT DE CODE gebouwd (datapackage.py); deze test bewaakt dat het niet uit
de pas kan lopen met de Parquet-schema's die de code zelf gebruikt: elk veld in een schema moet in
het bijbehorende datapackage-resource staan, en omgekeerd."""

from __future__ import annotations

import json

import pytest

from warmingup_preprocessing import datapackage, dekking, tabellen
from warmingup_preprocessing.pijplijn import BOILER_TEMP_SCHEMA, THERMOSTAT_TEMP_SCHEMA

_SCHEMAS = {
    "boiler_temp": BOILER_TEMP_SCHEMA,
    "thermostat_temp": THERMOSTAT_TEMP_SCHEMA,
    "etmaal": tabellen.ETMAAL_SCHEMA,
    "resultaten": tabellen.RESULTATEN_SCHEMA,
    "info_metadata": tabellen.INFO_METADATA_SCHEMA,
    "dekking": dekking.DEKKING_SCHEMA,
}


def test_datapackage_bouwt_zonder_fouten():
    pakket = datapackage.bouw_datapackage()
    assert pakket["resources"]
    json.dumps(pakket)  # moet JSON-serialiseerbaar zijn


def test_elke_resource_heeft_precies_de_velden_van_zijn_schema():
    pakket = datapackage.bouw_datapackage()
    resources = {r["name"]: r for r in pakket["resources"]}
    assert set(resources) == set(_SCHEMAS)

    for naam, schema in _SCHEMAS.items():
        schema_velden = set(schema.names)
        package_velden = {v["name"] for v in resources[naam]["schema"]["fields"]}
        assert schema_velden == package_velden, (
            f"{naam}: schema en datapackage lopen uit de pas.\n"
            f"alleen in schema: {schema_velden - package_velden}\n"
            f"alleen in datapackage: {package_velden - schema_velden}"
        )


def test_elk_veld_heeft_een_beschrijving():
    pakket = datapackage.bouw_datapackage()
    for resource in pakket["resources"]:
        for veld in resource["schema"]["fields"]:
            assert veld.get("description"), f"{resource['name']}.{veld['name']} heeft geen description"


def test_geen_primary_key_op_boiler_temp_thermostat_temp_en_etmaal():
    """Deze drie hebben een (home_id, tijdstip)-achtige sleutel die NIET uniek is; zie
    datapackage._GEEN_PRIMARY_KEY_REDEN. Fout weglaten van deze reden zou een valse indruk van
    uniciteit geven."""
    pakket = datapackage.bouw_datapackage()
    resources = {r["name"]: r for r in pakket["resources"]}
    for naam in ("boiler_temp", "thermostat_temp", "etmaal"):
        assert "primaryKey" not in resources[naam]["schema"]
        assert resources[naam]["primaryKeyOmittedReason"]


def test_primary_key_op_de_drie_unieke_tabellen():
    pakket = datapackage.bouw_datapackage()
    resources = {r["name"]: r for r in pakket["resources"]}
    for naam in ("resultaten", "info_metadata", "dekking"):
        assert resources[naam]["schema"]["primaryKey"]


def test_boiler_temp_pad_is_patroon_zonder_concrete_bestandenlijst():
    pakket = datapackage.bouw_datapackage()
    resources = {r["name"]: r for r in pakket["resources"]}
    assert resources["boiler_temp"]["path"] == "boiler_temp/home_id=*.parquet"


def test_boiler_temp_pad_blijft_patroon_ook_met_een_echte_bestandenlijst():
    """Data Package's multipart-vorm ("plak deze bestanden aan elkaar") is ongeldig voor Parquet
    (elk bestand heeft zijn eigen header/footer); frictionless wijst een array-``path`` op deze
    resource dan ook af, zie de moduledocstring van datapackage.py. Het aantal komt in de titel."""
    pakket = datapackage.bouw_datapackage(
        boiler_temp_bestanden=["boiler_temp/home_id=WU1.parquet", "boiler_temp/home_id=WU0.parquet"],
    )
    resources = {r["name"]: r for r in pakket["resources"]}
    assert resources["boiler_temp"]["path"] == "boiler_temp/home_id=*.parquet"
    assert "2 bestanden" in resources["boiler_temp"]["title"]


def test_licentie_verwijst_naar_gebruiksvoorwaarden_geen_open_licentienaam():
    pakket = datapackage.bouw_datapackage()
    licentie = pakket["licenses"][0]
    assert licentie["path"] == "GEBRUIKSVOORWAARDEN.md"
    # Geen standaard open-licentie-identifier als 'name' (dat zou een licentie suggereren die er niet
    # is); de tekstuele uitleg in 'title' MAG die namen wel noemen om juist uit te leggen dat ze NIET
    # van toepassing zijn.
    assert licentie["name"] not in ("cc-by-4.0", "cc0-1.0", "odbl-1.0", "mit")


def test_version_is_de_uitvoer_contract_versie():
    from warmingup_preprocessing.manifest import UITVOER_CONTRACT_VERSIE

    pakket = datapackage.bouw_datapackage()
    assert pakket["version"] == UITVOER_CONTRACT_VERSIE


def test_frictionless_structurele_validatie():
    """Structurele validatie (het JSON Schema-profiel van Data Package v1), zonder de Parquet-data
    zelf te lezen. Slaat zichzelf over als frictionless niet geïnstalleerd is (optionele
    dev-afhankelijkheid, zie pyproject.toml)."""
    frictionless = pytest.importorskip("frictionless")
    pakket = datapackage.bouw_datapackage(
        boiler_temp_bestanden=["boiler_temp/home_id=WU0.parquet"],
        thermostat_temp_bestanden=["thermostat_temp/home_id=WU0.parquet"],
    )
    fouten = list(frictionless.Package.metadata_validate(pakket))
    assert fouten == []
