# TRANSFORM: turns DGEG's raw records into a clean DataFrame

import pandas as pd


class Transformer:
    """Turns raw API records into a DataFrame with a numeric price next to the original text."""

    @staticmethod
    def parse_price(text):
        """Converts a DGEG price such as '1,164 €' to 1.164.

        A missing or empty price becomes NaN, so the quality checks report it
        instead of the pipeline crashing here.
        """
        if text is None or pd.isna(text):
            return float("nan")

        number = text.replace("€", "").strip()
        if not number:
            return float("nan")

        return float(number.replace(",", "."))

    def transform(self, records):
        """Converts raw API records into a pandas DataFrame."""
        df = pd.DataFrame(records)
        df["Preco_num"] = df["Preco"].apply(self.parse_price)
        return df
