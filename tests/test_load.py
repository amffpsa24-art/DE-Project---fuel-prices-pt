# Database tests: staging -> star schema, idempotency and SCD Type 2
# These run against a separate test database (see conftest.py), never the real one.
# Every test that takes `db` starts with empty tables, so tests can run in any order.

from datetime import date

import psycopg
import pytest

from etl.load import Warehouse
from etl.transform import Transformer
from tests.conftest import make_record, query

# Two consecutive snapshot days, to simulate the pipeline running on day 1 and then day 2
DAY_1, DAY_2 = date(2026, 10, 4), date(2026, 10, 5)


def make_df(*records):
    """A transformed DataFrame from hand-made records."""
    return Transformer().transform(list(records))


def counts(db):
    """Number of rows in every star schema table."""
    tables = ["dim_data", "dim_combustivel", "dim_postos", "fact_precos"]
    return {t: query(db, f"SELECT COUNT(*) FROM {t}")[0][0] for t in tables}


@pytest.fixture
def warehouse(db):
    """A Warehouse pointing to the (freshly emptied) test database."""
    return Warehouse(db)


class TestLoad:
    def test_fills_every_table(self, db, warehouse):
        # 2 stations, 2 fuels, 3 prices (station 1 sells both fuels)
        warehouse.load(make_df(
            make_record(posto_id=1, fuel="Gasóleo simples"),
            make_record(posto_id=1, fuel="Gasolina simples 95"),
            make_record(posto_id=2, fuel="Gasóleo simples", nome="Posto B"),
        ), DAY_1)

        # Each dimension stores each thing once; the fact table has one row per station x fuel
        assert counts(db) == {"dim_data": 1, "dim_combustivel": 2, "dim_postos": 2, "fact_precos": 3}

    def test_loading_the_same_day_twice_creates_no_duplicates(self, db, warehouse):
        # Idempotency: rerunning the same day must leave the database exactly as it was
        df = make_df(make_record(posto_id=1), make_record(posto_id=2, nome="Posto B"))
        warehouse.load(df, DAY_1)
        before = counts(db)

        warehouse.load(df, DAY_1)   # e.g. a retried GitHub Actions run

        assert counts(db) == before

    def test_warns_when_a_day_loaded_out_of_order_loses_rows(self, db, warehouse, caplog):
        # Station 1's only version starts on day 2, so day 1's price has no version to point to and is dropped.
        # There's no error, so the warning is the only sign (e.g. a backfill of an older day)
        warehouse.load(make_df(make_record(posto_id=1)), DAY_2)

        warehouse.load(make_df(make_record(posto_id=1)), DAY_1)

        assert "Only 0 of 1 staged rows" in caplog.text

    def test_prices_are_stored_exactly(self, db, warehouse):
        warehouse.load(make_df(make_record(preco="1,164 €")), DAY_1)

        (price,) = query(db, "SELECT preco FROM fact_precos")[0]
        assert str(price) == "1.164"     # NUMERIC keeps exact decimals, no 1.16399999...

    def test_a_failed_load_leaves_nothing_behind(self, db, warehouse):
        # A negative price breaks a database rule (CHECK preco > 0) in the LAST step of the load.
        # Because everything runs in one transaction, the dimensions loaded before it must be undone too.
        df = make_df(make_record(posto_id=1, preco="1,500 €"), make_record(posto_id=2, nome="Posto B", preco="-1,000 €"))

        # pytest.raises: the test passes only if this exact error happens
        with pytest.raises(psycopg.errors.CheckViolation):
            warehouse.load(df, DAY_1)

        # All-or-nothing: not even the valid station 1 was kept
        assert counts(db) == {"dim_data": 0, "dim_combustivel": 0, "dim_postos": 0, "fact_precos": 0}


# SCD Type 2: when a station's details change, keep the old version and add a new one, instead of overwriting
class TestStationHistory:
    def test_a_brand_change_creates_a_new_version_and_keeps_history(self, db, warehouse):
        warehouse.load(make_df(make_record(posto_id=1, marca="GALP")), DAY_1)
        warehouse.load(make_df(make_record(posto_id=1, marca="PRIO")), DAY_2)

        versions = query(db, "SELECT marca, valido_de, valido_ate, atual FROM dim_postos WHERE posto_id = 1 "
                             "ORDER BY valido_de")
        assert versions == [
            ("GALP", DAY_1, date(2026, 10, 4), False),   # closed the day before the change was seen
            ("PRIO", DAY_2, date(9999, 12, 31), True),   # 9999-12-31 = "still valid", the current version
        ]
        # Each price keeps the brand the station had that day
        brands = query(db, "SELECT data, marca FROM vw_precos ORDER BY data")
        assert brands == [(DAY_1, "GALP"), (DAY_2, "PRIO")]

    def test_unchanged_station_keeps_a_single_version(self, db, warehouse):
        # The opposite case: nothing changed, so no new version (otherwise dim_postos would grow every day)
        for day in (DAY_1, DAY_2):
            warehouse.load(make_df(make_record(posto_id=1)), day)

        assert query(db, "SELECT COUNT(*) FROM dim_postos")[0][0] == 1
        assert query(db, "SELECT COUNT(*) FROM fact_precos")[0][0] == 2   # but still one price per day

    def test_missing_coordinates_do_not_count_as_a_change(self, db, warehouse):
        # Missing on both days = no change, so no new version
        for day in (DAY_1, DAY_2):
            warehouse.load(make_df(make_record(posto_id=1, latitude=None, longitude=None)), day)

        assert query(db, "SELECT COUNT(*) FROM dim_postos")[0][0] == 1

    def test_coordinates_added_later_count_as_a_change(self, db, warehouse):
        # Missing -> known IS a change. A plain "<>" comparison would miss it, because in SQL
        # anything compared with NULL is "unknown", not "different". That's why the load uses IS DISTINCT FROM.
        warehouse.load(make_df(make_record(posto_id=1, latitude=None, longitude=None)), DAY_1)
        warehouse.load(make_df(make_record(posto_id=1, latitude=38.7, longitude=-9.2)), DAY_2)

        assert query(db, "SELECT COUNT(*) FROM dim_postos WHERE posto_id = 1")[0][0] == 2

    def test_a_new_station_starts_on_the_day_it_first_appears(self, db, warehouse):
        # Station 2 only shows up on day 2, so its history must start on day 2, not earlier
        warehouse.load(make_df(make_record(posto_id=1)), DAY_1)
        warehouse.load(make_df(make_record(posto_id=1), make_record(posto_id=2, nome="Posto B")), DAY_2)

        assert query(db, "SELECT valido_de FROM dim_postos WHERE posto_id = 2") == [(DAY_2,)]
