# ============================================
# Unit tests: the data quality checks that stop a bad load (no database, no network)
# ============================================
# Created: 11/10/2026

import pytest

import etl.quality as quality
from etl.quality import DataQualityError, verificar
from etl.transform import transform
from tests.conftest import make_record


@pytest.fixture
def poucos_registos(monkeypatch):
    """Lowers the minimum volume, so small hand-made samples can pass the other checks."""
    monkeypatch.setattr(quality, "MIN_REGISTOS", 1)


def test_a_normal_day_passes(api_page, poucos_registos):
    verificar(transform(api_page["resultado"]))   # no exception = passed


def test_too_few_rows_fail():
    # The real minimum (12,000): two rows look like a partial extract
    df = transform([make_record(posto_id=1), make_record(posto_id=2)])

    with pytest.raises(DataQualityError, match="2 rows, expected 12,000"):
        verificar(df)


def test_a_price_outside_the_range_fails(poucos_registos):
    # 11,64 € a litre is a parsing slip (should be 1,164), not a real price
    df = transform([make_record(posto_id=1), make_record(posto_id=2, preco="11,64 €")])

    with pytest.raises(DataQualityError, match="1 prices outside"):
        verificar(df)


def test_an_empty_required_field_fails(poucos_registos):
    df = transform([make_record(posto_id=1), make_record(posto_id=2, nome=None)])

    with pytest.raises(DataQualityError, match="1 rows with empty Nome"):
        verificar(df)


def test_a_missing_optional_field_is_fine(poucos_registos):
    # Coordinates or postal codes are sometimes missing at the source: that's normal, not a bad day
    df = transform([make_record(posto_id=1, latitude=None, longitude=None)])

    verificar(df)


def test_duplicated_station_and_fuel_fails(poucos_registos):
    df = transform([make_record(posto_id=1), make_record(posto_id=1)])

    with pytest.raises(DataQualityError, match="1 duplicated"):
        verificar(df)


def test_a_missing_column_fails(poucos_registos):
    # e.g. DGEG renames a field: the load would break, so stop with a clear message
    df = transform([make_record(posto_id=1)]).drop(columns=["Distrito"])

    with pytest.raises(DataQualityError, match="missing columns: Distrito"):
        verificar(df)


def test_every_problem_is_reported_at_once(poucos_registos):
    # One message with all problems, instead of fixing them one run at a time
    df = transform([make_record(posto_id=1, preco="11,64 €"), make_record(posto_id=1, nome=None)])

    with pytest.raises(DataQualityError) as erro:
        verificar(df)
    assert "empty Nome" in str(erro.value)
    assert "prices outside" in str(erro.value)
    assert "duplicated" in str(erro.value)
