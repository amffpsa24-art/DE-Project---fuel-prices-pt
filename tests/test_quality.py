# ============================================
# Unit tests: the data quality checks that stop a bad load (no database, no network)
# ============================================
# Created: 11/10/2026
# Updated: 16/10/2026 (tests grouped in a class; thresholds passed to QualityChecker instead of monkeypatched)

import pytest

from etl.quality import DataQualityError, QualityChecker
from etl.transform import Transformer
from tests.conftest import make_record


def df_de(*registos):
    """A transformed DataFrame from hand-made records."""
    return Transformer().transform(list(registos))


class TestQualityChecker:
    # A lower minimum volume, so small hand-made samples can pass the other checks
    checker = QualityChecker(min_registos=1)

    def test_a_normal_day_passes(self, api_page):
        self.checker.verificar(Transformer().transform(api_page["resultado"]))   # no exception = passed

    def test_too_few_rows_fail(self):
        # The real minimum (12,000): two rows look like a partial extract
        with pytest.raises(DataQualityError, match="2 rows, expected 12,000"):
            QualityChecker().verificar(df_de(make_record(posto_id=1), make_record(posto_id=2)))

    def test_a_price_outside_the_range_fails(self):
        # 11,64 € a litre is a parsing slip (should be 1,164), not a real price
        with pytest.raises(DataQualityError, match="1 prices outside"):
            self.checker.verificar(df_de(make_record(posto_id=1), make_record(posto_id=2, preco="11,64 €")))

    def test_an_empty_required_field_fails(self):
        with pytest.raises(DataQualityError, match="1 rows with empty Nome"):
            self.checker.verificar(df_de(make_record(posto_id=1), make_record(posto_id=2, nome=None)))

    def test_an_empty_price_fails(self):
        # An empty price becomes NaN in the transform, and is caught here instead of crashing earlier
        with pytest.raises(DataQualityError, match="1 rows with empty Preco_num"):
            self.checker.verificar(df_de(make_record(posto_id=1), make_record(posto_id=2, preco="")))

    def test_a_missing_optional_field_is_fine(self):
        # Coordinates or postal codes are sometimes missing at the source: that's normal, not a bad day
        self.checker.verificar(df_de(make_record(posto_id=1, latitude=None, longitude=None)))

    def test_duplicated_station_and_fuel_fails(self):
        with pytest.raises(DataQualityError, match="1 duplicated"):
            self.checker.verificar(df_de(make_record(posto_id=1), make_record(posto_id=1)))

    def test_a_missing_column_fails(self):
        # e.g. DGEG renames a field: the load would break, so stop with a clear message
        df = df_de(make_record(posto_id=1)).drop(columns=["Distrito"])

        with pytest.raises(DataQualityError, match="missing columns: Distrito"):
            self.checker.verificar(df)

    def test_every_problem_is_reported_at_once(self):
        # One message with all problems, instead of fixing them one run at a time
        df = df_de(make_record(posto_id=1, preco="11,64 €"), make_record(posto_id=1, nome=None))

        with pytest.raises(DataQualityError) as erro:
            self.checker.verificar(df)
        assert "empty Nome" in str(erro.value)
        assert "prices outside" in str(erro.value)
        assert "duplicated" in str(erro.value)
