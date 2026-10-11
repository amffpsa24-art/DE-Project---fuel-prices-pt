# ============================================
# Database tests: staging -> star schema, idempotency and SCD Type 2
# ============================================
# Created: 07/10/2026
# These run against a separate test database (see conftest.py), never the real one.
# Every test that takes `db` starts with empty tables, so tests can run in any order.

from datetime import date

import psycopg
import pytest

import etl.load as load_module
from etl.load import load_postgres, save_raw_csv
from etl.transform import transform
from tests.conftest import make_record, query

# Two consecutive snapshot days, to simulate the pipeline running on day 1 and then day 2
DIA_1, DIA_2 = date(2026, 10, 4), date(2026, 10, 5)


def counts(db):
    """Number of rows in every star schema table."""
    tabelas = ["dim_data", "dim_combustivel", "dim_postos", "fact_precos"]
    return {t: query(db, f"SELECT COUNT(*) FROM {t}")[0][0] for t in tabelas}


def test_load_fills_every_table(db):
    # 2 stations, 2 fuels, 3 prices (station 1 sells both fuels)
    df = transform([
        make_record(posto_id=1, fuel="Gasóleo simples"),
        make_record(posto_id=1, fuel="Gasolina simples 95"),
        make_record(posto_id=2, fuel="Gasóleo simples", nome="Posto B"),
    ])
    load_postgres(df, DIA_1, conninfo=db)

    # Each dimension stores each thing once; the fact table has one row per station x fuel
    assert counts(db) == {"dim_data": 1, "dim_combustivel": 2, "dim_postos": 2, "fact_precos": 3}


def test_loading_the_same_day_twice_creates_no_duplicates(db):
    # Idempotency: rerunning the same day must leave the database exactly as it was
    df = transform([make_record(posto_id=1), make_record(posto_id=2, nome="Posto B")])
    load_postgres(df, DIA_1, conninfo=db)
    antes = counts(db)

    load_postgres(df, DIA_1, conninfo=db)   # e.g. a retried GitHub Actions run

    assert counts(db) == antes


def test_prices_are_stored_exactly(db):
    load_postgres(transform([make_record(preco="1,164 €")]), DIA_1, conninfo=db)

    (preco,) = query(db, "SELECT preco FROM fact_precos")[0]
    assert str(preco) == "1.164"     # NUMERIC keeps exact decimals, no 1.16399999...


# SCD Type 2: when a station's details change, keep the old version and add a new one, instead of overwriting
def test_a_brand_change_creates_a_new_version_and_keeps_history(db):
    load_postgres(transform([make_record(posto_id=1, marca="GALP")]), DIA_1, conninfo=db)
    load_postgres(transform([make_record(posto_id=1, marca="PRIO")]), DIA_2, conninfo=db)

    versoes = query(db, "SELECT marca, valido_de, valido_ate, atual FROM dim_postos WHERE posto_id = 1 ORDER BY valido_de")
    assert versoes == [
        ("GALP", DIA_1, date(2026, 10, 4), False),   # closed the day before the change was seen
        ("PRIO", DIA_2, date(9999, 12, 31), True),   # 9999-12-31 = "still valid", the current version
    ]
    # Each price keeps the brand the station had that day
    marcas = query(db, "SELECT data, marca FROM vw_precos ORDER BY data")
    assert marcas == [(DIA_1, "GALP"), (DIA_2, "PRIO")]


def test_unchanged_station_keeps_a_single_version(db):
    # The opposite case: nothing changed, so no new version (otherwise dim_postos would grow every day)
    for dia in (DIA_1, DIA_2):
        load_postgres(transform([make_record(posto_id=1)]), dia, conninfo=db)

    assert query(db, "SELECT COUNT(*) FROM dim_postos")[0][0] == 1
    assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 2   # but still one price per day


def test_missing_coordinates_do_not_count_as_a_change(db):
    # Missing on both days = no change, so no new version
    for dia in (DIA_1, DIA_2):
        load_postgres(transform([make_record(posto_id=1, latitude=None, longitude=None)]), dia, conninfo=db)

    assert query(db, "SELECT COUNT(*) FROM dim_postos")[0][0] == 1


def test_coordinates_added_later_count_as_a_change(db):
    # Missing -> known IS a change. A plain "<>" comparison would miss it, because in SQL
    # anything compared with NULL is "unknown", not "different". That's why the load uses IS DISTINCT FROM.
    load_postgres(transform([make_record(posto_id=1, latitude=None, longitude=None)]), DIA_1, conninfo=db)
    load_postgres(transform([make_record(posto_id=1, latitude=38.7, longitude=-9.2)]), DIA_2, conninfo=db)

    assert query(db, "SELECT COUNT(*) FROM dim_postos WHERE posto_id = 1")[0][0] == 2


def test_a_new_station_starts_on_the_day_it_first_appears(db):
    # Station 2 only shows up on day 2, so its history must start on day 2, not earlier
    load_postgres(transform([make_record(posto_id=1)]), DIA_1, conninfo=db)
    load_postgres(transform([make_record(posto_id=1), make_record(posto_id=2, nome="Posto B")]), DIA_2, conninfo=db)

    assert query(db, "SELECT valido_de FROM dim_postos WHERE posto_id = 2") == [(DIA_2,)]


def test_a_failed_load_leaves_nothing_behind(db):
    # A negative price breaks a database rule (CHECK preco > 0) in the LAST step of the load.
    # Because everything runs in one transaction, the dimensions loaded before it must be undone too.
    df = transform([make_record(posto_id=1, preco="1,500 €"), make_record(posto_id=2, nome="Posto B", preco="-1,000 €")])

    # pytest.raises: the test passes only if this exact error happens
    with pytest.raises(psycopg.errors.CheckViolation):
        load_postgres(df, DIA_1, conninfo=db)

    # All-or-nothing: not even the valid station 1 was kept
    assert counts(db) == {"dim_data": 0, "dim_combustivel": 0, "dim_postos": 0, "fact_precos": 0}


# No `db` here: this test only writes a file, so it also runs without a database.
# tmp_path is a temporary folder that pytest creates for the test and cleans up afterwards.
def test_raw_csv_is_saved_with_the_date_in_its_name(tmp_path, monkeypatch):
    monkeypatch.setattr(load_module, "PASTA_RAW", tmp_path)   # write to a temporary folder, not data/raw
    df = transform([make_record(nome="Posto Açaí")])

    caminho = save_raw_csv(df, DIA_1)

    # One file per day, named by date, so a new run never overwrites another day's snapshot
    assert caminho.name == "fuel_prices_2026-10-04.csv"
    assert "Posto Açaí" in caminho.read_text(encoding="utf-8")   # accents survive (UTF-8)
