# Transform raw DGEG records into a clean DataFrame
# Created: 27/09/2026

import pandas as pd


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

    preco_limpo = preco_limpo.replace(",", ".")

    return float(preco_limpo)


def transform(registos):
    """Convert raw API records into a cleaned pandas DataFrame."""

    df = pd.DataFrame(registos)
    df["Preco_num"] = df["Preco"].apply(limpar_preco)

    return df