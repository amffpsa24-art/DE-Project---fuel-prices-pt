# Unit tests: the backfill reads the raw CSVs and runs the same quality checks as the daily run (no database)
# Created: 31/10/2026

from datetime import date

from backfill import Backfill
from etl.load import RawStore
from etl.quality import QualityChecker
from etl.transform import Transformer
from tests.conftest import make_record

DIA_1, DIA_2 = date(2026, 10, 15), date(2026, 10, 16)


class FakeWarehouse:
    """Stands in for Warehouse: remembers which days it was asked to load, and the prices it got."""

    def __init__(self):
        self.carregados = {}

    def load(self, df, snapshot_date):
        self.carregados[snapshot_date] = df["Preco_num"].tolist()


def guardar(store, dia, *registos):
    """A raw CSV, written exactly as the daily run writes it."""
    store.save(Transformer().transform(list(registos)), dia)


class TestBackfill:
    def test_loads_good_days_and_skips_a_day_that_failed_the_checks(self, tmp_path):
        # Like 16/10/2026: the daily run saved the CSV, then the duplicate check stopped it
        store, warehouse = RawStore(tmp_path), FakeWarehouse()
        guardar(store, DIA_1, make_record(posto_id=1), make_record(posto_id=2))
        guardar(store, DIA_2, make_record(posto_id=1), make_record(posto_id=1))

        recusados = Backfill(store, warehouse, QualityChecker(min_registos=1)).run()

        assert recusados == [DIA_2]
        assert list(warehouse.carregados) == [DIA_1]

    def test_prices_are_numbers_again_after_the_csv(self, tmp_path):
        # The CSV is read as text; the price checks (0.5-5.0 €) need numbers, or they'd crash on "1.5" < 0.5
        store, warehouse = RawStore(tmp_path), FakeWarehouse()
        guardar(store, DIA_1, make_record(preco="1,500 €"))

        Backfill(store, warehouse, QualityChecker(min_registos=1)).run()

        assert warehouse.carregados[DIA_1] == [1.5]
