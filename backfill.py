# ============================================
# BACKFILL: loads raw CSV snapshots that already exist into PostgreSQL
# ============================================
# Created: 04/10/2026
# Updated: 16/10/2026 (Backfill class)
# Updated: 31/10/2026 (same quality checks as the daily run: the CSVs include days that failed them)
# Usage (from the project root, with .venv active):  python backfill.py
#
# Safe to run any number of times: the load is idempotent,
# so days already in the database are simply skipped.

import logging

import pandas as pd

from etl.load import RawStore, Warehouse
from etl.quality import DataQualityError, QualityChecker


class Backfill:
    """Loads every CSV in the raw layer into the warehouse, oldest day first, skipping days that fail the checks."""

    def __init__(self, raw_store, warehouse, checker):
        self.raw_store = raw_store
        self.warehouse = warehouse
        self.checker = checker

    def run(self):
        """Returns the days skipped by the quality checks."""
        snapshots = list(self.raw_store.snapshots())

        if not snapshots:
            print(f"No snapshots found in {self.raw_store.pasta}")
            return []

        recusados = []
        for snapshot_date, caminho in snapshots:
            # Read everything as text: PostgreSQL converts it to the right types,
            # and text keeps values like postal codes exactly as they were
            df = pd.read_csv(caminho, dtype=str)
            # ...except the parsed price, which the checks compare with numbers
            df["Preco_num"] = pd.to_numeric(df["Preco_num"])

            print(f"\n{caminho.name}")
            # The daily run saves its CSV BEFORE the checks, so a day that failed them (e.g. 16/10/2026,
            # duplicated rows) has a CSV too. It must not reach the warehouse this way either.
            try:
                self.checker.verificar(df)
            except DataQualityError as e:
                print(f"Skipped, failed the quality checks: {e}")
                recusados.append(snapshot_date)
                continue
            self.warehouse.load(df, snapshot_date)

        print(f"\nBackfill finished. Skipped: {', '.join(map(str, recusados)) or 'none'}.")
        return recusados


if __name__ == "__main__":
    # Warehouse.load reports through logging: show its messages too
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    Backfill(RawStore(), Warehouse(), QualityChecker()).run()
