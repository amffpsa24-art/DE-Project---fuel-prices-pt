# ============================================
# Unit tests: cleaning prices and building the DataFrame (no database, no network)
# ============================================
# Created: 07/10/2026

import pytest

from etl.transform import limpar_preco, transform
from tests.conftest import make_record


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("1,164 €", 1.164),      # the usual format
        ("2,099 €", 2.099),
        ("0,899 €", 0.899),      # below one euro (e.g. gas sold per kg)
        ("  1,5 €  ", 1.5),      # extra spaces
        ("1,164", 1.164),        # no euro sign
    ],
)
def test_limpar_preco_parses_portuguese_prices(texto, esperado):
    assert limpar_preco(texto) == pytest.approx(esperado)


def test_limpar_preco_rejects_text_that_is_not_a_price():
    # A garbled value must fail loudly, not turn silently into a wrong number
    with pytest.raises(ValueError):
        limpar_preco("sem preço")


def test_transform_keeps_every_record_and_adds_numeric_price():
    registos = [make_record(posto_id=1, preco="1,164 €"), make_record(posto_id=2, preco="2,099 €")]
    df = transform(registos)

    assert len(df) == 2
    assert df["Preco_num"].tolist() == pytest.approx([1.164, 2.099])
    # The original text is kept next to the number, for traceability
    assert df["Preco"].tolist() == ["1,164 €", "2,099 €"]


def test_transform_works_on_a_real_api_sample(api_page):
    df = transform(api_page["resultado"])

    assert len(df) == len(api_page["resultado"])
    assert df["Preco_num"].between(0.5, 5).all()
    assert {"Id", "Combustivel", "Preco_num", "DataAtualizacao"} <= set(df.columns)