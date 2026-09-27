# ============================================
# LOAD: saves the cleaned DataFrame to a dated CSV file
# ============================================
# Created: 27/09/2026

from datetime import date
from pathlib import Path

# Folder where each daily snapshot is saved
PASTA_DADOS = Path("data") / "raw"

def load(df, pasta=PASTA_DADOS):
    """
    Saves the cleaned DataFrame to a CSV named after today's date,
    e.g. data/raw/fuel_prices_2026-09-27.csv.
    One file per run means daily runs build up a price history
    instead of overwriting yesterday's data.
    """
    # Create the target folder if it doesn't exist yet
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)

    # Build the file name from today's date
    caminho = pasta / f"fuel_prices_{date.today().isoformat()}.csv"

    # index=False: don't write pandas' internal row numbers as a column
    df.to_csv(caminho, index=False)

    print(f"Saved {len(df)} rows to {caminho}")
    return caminho