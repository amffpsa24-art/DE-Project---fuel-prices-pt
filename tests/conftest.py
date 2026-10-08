# Shared test setup: sample records and a clean test database
# Created: 07/10/2026

import json
import os
from pathlib import Path

import psycopg
import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SQL_DIR = PROJECT_ROOT / "sql"

# Where the database tests run. NEVER the real database:
# locally a separate "fuel_prices_test" database, in CI a temporary PostgreSQL started by GitHub Actions.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/fuel_prices_test")


def make_record(posto_id=1, fuel="Gasóleo simples", preco="1,500 €", marca="GALP", nome="Posto A",
                latitude=38.7, longitude=-9.2, data_atualizacao="2026-10-04 09:10"):
    """One API record (station x fuel), shaped exactly like DGEG's response."""
    return {
        "Id": posto_id, "Nome": nome, "TipoPosto": "Outro", "Municipio": "Odivelas", "Preco": preco,
        "Marca": marca, "Combustivel": fuel, "DataAtualizacao": data_atualizacao, "Distrito": "Lisboa",
        "Morada": "Rua X", "Localidade": "Famões", "CodPostal": "1685-000",
        "Latitude": latitude, "Longitude": longitude, "Quantidade": 1,
    }


@pytest.fixture
def api_page():
    """A real sample of the API's response (5 records of one station), saved as a file."""
    return json.loads((FIXTURES / "api_page.json").read_text(encoding="utf-8"))


@pytest.fixture
def db():
    """
    A test database with a fresh, empty star schema for every test.
    Returns the connection string to pass to load_postgres(..., conninfo=db).
    """
    # Safety net: refuse to wipe anything that doesn't look like a test database
    dbname = psycopg.conninfo.conninfo_to_dict(TEST_DATABASE_URL).get("dbname", "")
    if not dbname.endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL must point to a database ending in '_test' (got '{dbname}')", returncode=1)

    try:
        conn = psycopg.connect(TEST_DATABASE_URL, autocommit=True)
    except psycopg.OperationalError as e:
        pytest.skip(f"No test database available ({e.__class__.__name__}). See README: Running the tests.")

    with conn:
        conn.execute("DROP VIEW IF EXISTS vw_precos")
        conn.execute("DROP TABLE IF EXISTS fact_precos, dim_postos, dim_combustivel, dim_data, stg_precos CASCADE")
        conn.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
        conn.execute((SQL_DIR / "views.sql").read_text(encoding="utf-8"))
    return TEST_DATABASE_URL


def query(conninfo, sql, params=None):
    """Runs a query and returns all rows (helper for assertions)."""
    with psycopg.connect(conninfo) as conn:
        return conn.execute(sql, params).fetchall()