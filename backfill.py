# ============================================
# BACKFILL: loads raw CSV snapshots that already exist into PostgreSQL
# ============================================
# Created: 04/10/2026
# Updated: 16/10/2026 (Backfill class)
# Usage (from the project root, with .venv active):  python backfill.py
#
# Safe to run any number of times: the load is idempotent,
# so days already in the database are simply skipped.

import logging

import pandas as pd

from etl.load import RawStore, Warehouse


class Backfill:
    """Loads every CSV in the raw layer into the warehouse, oldest day first."""

    def __init__(self, raw_store, warehouse):
        self.raw_store = raw_store
        self.warehouse = warehouse

    def run(self):
        snapshots = list(self.raw_store.snapshots())

        if not snapshots:
            print(f"No snapshots found in {self.raw_store.pasta}")
            return

        for snapshot_date, caminho in snapshots:
            # Read everything as text: PostgreSQL converts it to the right types,
            # and text keeps values like postal codes exactly as they were
            df = pd.read_csv(caminho, dtype=str)

            print(f"\n{caminho.name}")
            self.warehouse.load(df, snapshot_date)

        print("\nBackfill finished.")


if __name__ == "__main__":
    # Warehouse.load reports through logging: show its messages too
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    Backfill(RawStore(), Warehouse()).run()
