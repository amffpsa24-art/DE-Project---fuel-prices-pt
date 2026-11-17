# Unit tests: cleaning prices and building the DataFrame (no database, no network)

import math

import pytest

from etl.transform import Transformer
from tests.conftest import make_record


class TestParsePrice:
    # parametrize: runs the same test once per (input, expected) pair, each reported as its own test
    @pytest.mark.parametrize(
        "text, expected",
        [
            ("1,164 €", 1.164),      # the usual format
            ("2,099 €", 2.099),
            ("0,899 €", 0.899),      # below one euro (e.g. gas sold per kg)
            ("  1,5 €  ", 1.5),      # extra spaces
            ("1,164", 1.164),        # no euro sign
        ],
    )
    def test_parses_portuguese_prices(self, text, expected):
        # approx: floats can be off by a tiny amount (1.164 vs 1.16399999...), so compare with a tolerance
        assert Transformer.parse_price(text) == pytest.approx(expected)

    def test_rejects_text_that_is_not_a_price(self):
        # A garbled value must fail loudly, not turn silently into a wrong number
        with pytest.raises(ValueError):
            Transformer.parse_price("sem preço")

    @pytest.mark.parametrize("text", ["", "   ", " € ", None])
    def test_returns_nan_for_missing_price(self, text):
        # A missing price is not garbled data: it becomes NaN, and the quality checks flag it
        assert math.isnan(Transformer.parse_price(text))


class TestTransform:
    def test_keeps_every_record_and_adds_numeric_price(self):
        records = [make_record(posto_id=1, preco="1,164 €"), make_record(posto_id=2, preco="2,099 €")]
        df = Transformer().transform(records)

        assert len(df) == 2   # no rows lost or duplicated
        assert df["Preco_num"].tolist() == pytest.approx([1.164, 2.099])
        # The original text is kept next to the number, for traceability
        assert df["Preco"].tolist() == ["1,164 €", "2,099 €"]

    def test_works_on_a_real_api_sample(self, api_page):
        # Real data catches what hand-made records might miss (odd fields, real price formats)
        df = Transformer().transform(api_page["resultado"])

        assert len(df) == len(api_page["resultado"])
        assert df["Preco_num"].between(0.5, 5).all()   # sanity range: catches a parsing slip like 1164
        # The columns the load step depends on are present
        assert {"Id", "Combustivel", "Preco_num", "DataAtualizacao"} <= set(df.columns)
