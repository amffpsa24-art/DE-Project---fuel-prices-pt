# Unit tests: the backfill reads the saved raw data and runs the same quality checks as the daily run (no database)

from datetime import date, datetime

from backfill import Backfill
from etl.bronze import BronzeStore
from etl.quality import QualityChecker
from etl.transform import Transformer
from tests.conftest import make_record

DAY_1, DAY_2 = date(2026, 10, 15), date(2026, 10, 16)


class FakeWarehouse:
    """Stands in for Warehouse: remembers which days it was asked to load, and the prices it got."""

    def __init__(self):
        self.loaded = {}

    def load(self, df, snapshot_date):
        self.loaded[snapshot_date] = df["Preco_num"].tolist()


def save_bronze(store, day, *records, hour=10):
    """One bronze file, written exactly as the daily run writes it."""
    store.save(list(records), day, datetime(day.year, day.month, day.day, hour))


def save_legacy_csv(folder, day, *records):
    """One CSV, written exactly as the daily run wrote it before the bronze layer existed."""
    folder.mkdir(exist_ok=True)
    Transformer().transform(list(records)).to_csv(folder / f"fuel_prices_{day.isoformat()}.csv", index=False)


def backfill(tmp_path, warehouse):
    return Backfill(BronzeStore(tmp_path / "bronze"), warehouse, QualityChecker(min_rows=1),
                    legacy_csv_folder=tmp_path / "raw")


class TestBackfill:
    def test_loads_good_days_and_skips_a_day_that_failed_the_checks(self, tmp_path):
        # Like 16/10/2026: DGEG's answer was saved, then the duplicate check stopped the run
        warehouse = FakeWarehouse()
        store = BronzeStore(tmp_path / "bronze")
        save_bronze(store, DAY_1, make_record(posto_id=1), make_record(posto_id=2))
        save_bronze(store, DAY_2, make_record(posto_id=1), make_record(posto_id=1))

        skipped = backfill(tmp_path, warehouse).run()

        assert skipped == [DAY_2]
        assert list(warehouse.loaded) == [DAY_1]

    def test_a_day_with_two_runs_uses_the_first_good_one(self, tmp_path):
        # The first run of the day failed the checks; a manual rerun got a good answer
        warehouse = FakeWarehouse()
        store = BronzeStore(tmp_path / "bronze")
        save_bronze(store, DAY_1, make_record(posto_id=1), make_record(posto_id=1), hour=10)
        save_bronze(store, DAY_1, make_record(posto_id=1, preco="1,600 €"), hour=13)

        assert backfill(tmp_path, warehouse).run() == []
        assert warehouse.loaded[DAY_1] == [1.6]

    def test_reads_legacy_csvs_in_date_order_with_bronze_days(self, tmp_path):
        # Days before the bronze layer only have a CSV; prices must be numbers again after reading it
        warehouse = FakeWarehouse()
        save_bronze(BronzeStore(tmp_path / "bronze"), DAY_2, make_record(preco="1,700 €"))
        save_legacy_csv(tmp_path / "raw", DAY_1, make_record(preco="1,500 €"))

        backfill(tmp_path, warehouse).run()

        assert warehouse.loaded == {DAY_1: [1.5], DAY_2: [1.7]}
        assert list(warehouse.loaded) == [DAY_1, DAY_2]   # oldest first, for SCD Type 2

    def test_bronze_wins_over_a_csv_of_the_same_day(self, tmp_path):
        # Around 2026-10-31 both exist: the untouched raw answer is the better source
        warehouse = FakeWarehouse()
        save_bronze(BronzeStore(tmp_path / "bronze"), DAY_1, make_record(preco="1,700 €"))
        save_legacy_csv(tmp_path / "raw", DAY_1, make_record(preco="1,500 €"))

        backfill(tmp_path, warehouse).run()

        assert warehouse.loaded == {DAY_1: [1.7]}
