# BACKFILL: rebuilds the warehouse from the raw data saved on disk
# Usage (from the project root, with .venv active):  python backfill.py
#
# Reads two sources, oldest day first:
#   - data/bronze/: DGEG's raw JSON, one file per run (from 2026-10-31)
#   - data/raw/:    the CSVs the pipeline saved before the bronze layer existed (up to 2026-10-31)
# A day with bronze files uses those; a day with only a CSV uses the CSV.
# Days failing the quality checks are skipped. Safe to run any number of times: loads never duplicate data.

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from etl.bronze import BronzeStore
from etl.load import Warehouse
from etl.quality import DataQualityError, QualityChecker
from etl.transform import Transformer

LEGACY_CSV_FOLDER = Path(__file__).resolve().parent / "data" / "raw"
LEGACY_CSV_PREFIX = "fuel_prices_"


class Backfill:
    """Loads every saved day into the warehouse, oldest first, skipping days that fail the checks."""

    def __init__(self, bronze_store, warehouse, checker, transformer=None, legacy_csv_folder=LEGACY_CSV_FOLDER):
        self.bronze_store = bronze_store
        self.warehouse = warehouse
        self.checker = checker
        self.transformer = transformer or Transformer()
        self.legacy_csv_folder = Path(legacy_csv_folder)

    def find_days(self):
        """{day: [files]}, oldest day first. Bronze files win over a legacy CSV of the same day."""
        days = {}
        for day, path in self.bronze_store.snapshots():
            days.setdefault(day, []).append(path)
        for path in self.legacy_csv_folder.glob(f"{LEGACY_CSV_PREFIX}*.csv"):
            # "fuel_prices_2026-09-27.csv" -> 2026-09-27
            days.setdefault(date.fromisoformat(path.stem.removeprefix(LEGACY_CSV_PREFIX)), [path])
        # Sorted, because SCD Type 2 needs the days loaded in date order
        return dict(sorted(days.items()))

    def read(self, path):
        """One file as a transformed DataFrame, whatever its format."""
        if path.suffix == ".csv":
            # Read as text, so values like postal codes stay exactly as they were...
            df = pd.read_csv(path, dtype=str)
            # ...except the parsed price, which the checks compare with numbers
            df["Preco_num"] = pd.to_numeric(df["Preco_num"])
            return df
        return self.transformer.transform(self.bronze_store.read(path))

    def run(self):
        """Returns the days skipped by the quality checks."""
        days = self.find_days()
        if not days:
            print(f"No raw data found in {self.bronze_store.folder} or {self.legacy_csv_folder}")
            return []

        skipped = []
        for day, paths in days.items():
            # A day with several runs: load the first file that passes the checks
            for path in paths:
                print(f"\n{day}: {path.name}")
                df = self.read(path)
                try:
                    self.checker.check(df)
                except DataQualityError as e:
                    print(f"Failed the quality checks: {e}")
                    continue
                self.warehouse.load(df, day)
                break
            else:
                skipped.append(day)

        print(f"\nBackfill finished. Skipped: {', '.join(map(str, skipped)) or 'none'}.")
        return skipped


if __name__ == "__main__":
    # Warehouse.load reports through logging: show its messages too
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    Backfill(BronzeStore(), Warehouse(), QualityChecker()).run()
