# Transform raw DGEG records into a clean DataFrame
# Created: 27/09/2026
# Updated: 16/10/2026 (Transformer class)

import pandas as pd


class Transformer:
    """Turns raw API records into a DataFrame with a numeric price next to the original text."""

    @staticmethod
    def limpar_preco(preco_str):
        """Convert a DGEG price string such as '1,164 €' to 1.164.

        A missing or empty price becomes NaN, so the quality checks report it
        instead of the pipeline crashing here.
        """
        if preco_str is None or pd.isna(preco_str):
            return float("nan")

        preco_limpo = preco_str.replace("€", "").strip()
        if not preco_limpo:
            return float("nan")

        return float(preco_limpo.replace(",", "."))

    def transform(self, registos):
        """Convert raw API records into a cleaned pandas DataFrame."""
        df = pd.DataFrame(registos)
        df["Preco_num"] = df["Preco"].apply(self.limpar_preco)
        return df
