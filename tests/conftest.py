# Shared test setup: sample records and a clean test database
# Created: 07/10/2026
# pytest loads this file automatically: every fixture here can be used by any test, without importing it.

import json
import os
from pathlib import Path

import psycopg
import pytest

# Paths built from this file's location, so the tests work from any folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SQL_DIR = PROJECT_ROOT / "sql"

# Where the database tests run. NEVER the real database:
# locally a separate "fuel_prices_test" database, in CI a temporary PostgreSQL started by GitHub Actions.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://postgres@localhost:5432/fuel_prices_test")


# Builds fake API records. Defaults give a valid record; each test overrides only the field it cares about,
# so the test shows exactly what it's checking (e.g. make_record(marca="PRIO")).
def make_record(posto_id=1, fuel="Gasóleo simples", preco="1,500 €", marca="GALP", nome="Posto A",
                latitude=38.7, longitude=-9.2, data_atualizacao="2026-10-04 09:10"):
    """One API record (station x fuel), shaped exactly like DGEG's response."""
    return {
        "Id": posto_id, "Nome": nome, "TipoPosto": "Outro", "Municipio": "Odivelas", "Preco": preco,
        "Marca": marca, "Combustivel": fuel, "DataAtualizacao": data_atualizacao, "Distrito": "Lisboa",
        "Morada": "Rua X", "Localidade": "Famões", "CodPostal": "1685-000",
        "Latitude": latitude, "Longitude": longitude, "Quantidade": 1,
    }


# Fixture = setup that pytest runs before a test and passes in as an argument (here: def test_x(api_page)).
@pytest.fixture
def api_page():
    """A real sample of the API's response (5 records of one station), saved as a file."""
    # A saved file instead of a live call: tests stay fast, offline, and always see the same data
    return json.loads((FIXTURES / "api_page.json").read_text(encoding="utf-8"))


# scope="session": runs once for the whole test run, not once per test.
# If it skips, pytest remembers it, and every test that needs the database is skipped instantly.
@pytest.fixture(scope="session")
def test_database_url():
    """Checks once per run that the test database is reachable; if not, every database test is skipped at once."""
    # Safety net: refuse to wipe anything that doesn't look like a test database
    dbname = psycopg.conninfo.conninfo_to_dict(TEST_DATABASE_URL).get("dbname", "")
    if not dbname.endswith("_test"):
        pytest.exit(f"TEST_DATABASE_URL must point to a database ending in '_test' (got '{dbname}')", returncode=1)

    try:
        # connect_timeout: skip quickly instead of hanging when no database is running
        psycopg.connect(TEST_DATABASE_URL, connect_timeout=3).close()
    except psycopg.OperationalError as e:
        # Skip, not fail: a missing local database isn't a bug in the code
        pytest.skip(f"No test database available ({e.__class__.__name__}). See README: Running the tests.")
    return TEST_DATABASE_URL


@pytest.fixture
def db(test_database_url):
    """
    A test database with a fresh, empty star schema for every test.
    Returns the connection string to pass to load_postgres(..., conninfo=db).
    """
    # Drop and recreate everything before each test, so no test depends on data left by another.
    # autocommit: each statement is applied immediately (DROP/CREATE outside a transaction).
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        conn.execute("DROP VIEW IF EXISTS vw_precos")
        conn.execute(
            "DROP TABLE IF EXISTS fact_precos, dim_postos, dim_combustivel, dim_data, stg_precos, pipeline_runs CASCADE"
        )
        # Same SQL files as production, so the tests check the real schema, not a copy of it
        conn.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
        conn.execute((SQL_DIR / "views.sql").read_text(encoding="utf-8"))
    return test_database_url


# Small helper so assertions can read the database in one line
def query(conninfo, sql, params=None):
    """Runs a query and returns all rows (helper for assertions)."""
    with psycopg.connect(conninfo) as conn:
        return conn.execute(sql, params).fetchall()
