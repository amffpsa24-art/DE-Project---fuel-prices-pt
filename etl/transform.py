# ============================================
# TRANSFORM: converts raw records into a clean DataFrame
# ============================================
# Created: 27/09/2026

import pandas as pd


def limpar_preco(preco_str):
    """
    Converts a DGEG price string like "1,164 €" into a float like 1.164.
    Kept outside transform() so it can be unit-tested on its own.
    """
    # Remove the euro symbol and surrounding spaces
    preco_limpo = preco_str.replace("€", "").strip()
    # Swap the Portuguese decimal comma for a decimal point
    preco_limpo = preco_limpo.replace(",", ".")
    # Convert the cleaned text into a number
    return float(preco_limpo)


def transform(registos):
    """
    Takes the raw list of dictionaries returned by extract()
    and returns a cleaned pandas DataFrame, ready to be loaded.
    """
    # Each dictionary becomes one row, each key becomes one column
    df = pd.DataFrame(registos)

    # Keep the raw "Preco" string for debugging; add a numeric version next to it.
    # The load step decides which of the two actually goes into the final tables.
    df["Preco_num"] = df["Preco"].apply(limpar_preco)

    return df