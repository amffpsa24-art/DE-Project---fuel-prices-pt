# Transform raw DGEG records into a clean DataFrame
# Created: 27/09/2026

import pandas as pd


def limpar_preco(preco_str):
    """Convert a DGEG price string such as '1,164 €' to 1.164."""

    preco_limpo = preco_str.replace("€", "").strip()
    preco_limpo = preco_limpo.replace(",", ".")

    return float(preco_limpo)


def transform(registos):
    """Convert raw API records into a cleaned pandas DataFrame."""

    df = pd.DataFrame(registos)
    df["Preco_num"] = df["Preco"].apply(limpar_preco)

    return df