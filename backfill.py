# ============================================
# BACKFILL: loads raw CSV snapshots that already exist into PostgreSQL
# ============================================
# Created: 04/10/2026
# Usage (from the project root, with .venv active):  python backfill.py
#
# Safe to run any number of times: the load is idempotent,
# so days already in the database are simply skipped.

from datetime import date

import pandas as pd

from etl.load import PASTA_RAW, load_postgres


def run():
    # File names look like fuel_prices_2026-09-27.csv; sorted() puts them oldest first
    ficheiros = sorted(PASTA_RAW.glob("fuel_prices_*.csv"))

    if not ficheiros:
        print(f"No snapshots found in {PASTA_RAW}")
        return

    for caminho in ficheiros:
        # Take the date from the file name: "fuel_prices_2026-09-27" -> 2026-09-27
        snapshot_date = date.fromisoformat(caminho.stem.replace("fuel_prices_", ""))

        # Read everything as text: PostgreSQL converts it to the right types,
        # and text keeps values like postal codes exactly as they were
        df = pd.read_csv(caminho, dtype=str)

        print(f"\n{caminho.name}")
        load_postgres(df, snapshot_date)

    print("\nBackfill finished.")


if __name__ == "__main__":
    run()
