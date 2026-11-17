# QUALITY: checks a day's data BEFORE it reaches the database, and stops a bad load
#
# A load can succeed and still be wrong (half the stations, a price parsed as 1164 instead of 1.164).
# Stopping it keeps bad data out of the warehouse; the run is recorded as failed and the backup run tries again.

import logging

log = logging.getLogger(__name__)


class DataQualityError(Exception):
    """The day's data failed one or more checks; nothing was loaded."""


class QualityChecker:
    """Runs every check on a transformed DataFrame and raises DataQualityError if any fails."""

    # Columns the load needs (see Warehouse.COLUMN_MAP in load.py)
    REQUIRED_COLUMNS = ["Id", "Nome", "Marca", "TipoPosto", "Morada", "Localidade", "CodPostal", "Municipio",
                        "Distrito", "Latitude", "Longitude", "Combustivel", "Preco_num", "DataAtualizacao"]
    # Columns that must never be empty: the database requires them (NOT NULL)
    NOT_EMPTY_COLUMNS = ["Id", "Nome", "Combustivel", "Preco_num"]

    # Defaults from real snapshots (about 13,500 rows a day, prices from 1.00 to 3.28 €).
    # A price outside 0.50-5.00 € is a parsing error, not a real price.
    def __init__(self, min_rows=12_000, max_rows=16_000, min_price=0.5, max_price=5.0):
        self.min_rows = min_rows
        self.max_rows = max_rows
        self.min_price = min_price
        self.max_price = max_price

    def check(self, df):
        """Runs every check and raises DataQualityError listing ALL problems found (not just the first)."""
        # Without these columns the other checks can't run, so stop at once
        missing = [c for c in self.REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            raise DataQualityError(f"missing columns: {', '.join(missing)}")

        problems = [
            *self._volume(df),
            *self._empty_values(df),
            *self._prices(df),
            *self._duplicates(df),
        ]
        if problems:
            raise DataQualityError("; ".join(problems))
        log.info("Quality checks passed: %d rows", len(df))

    def _volume(self, df):
        # Far fewer rows than usual means a partial download; far more, a pagination bug
        if not self.min_rows <= len(df) <= self.max_rows:
            yield f"{len(df)} rows, expected {self.min_rows:,} to {self.max_rows:,}"

    def _empty_values(self, df):
        for column in self.NOT_EMPTY_COLUMNS:
            empty = int(df[column].isna().sum())
            if empty:
                yield f"{empty} rows with empty {column}"

    def _prices(self, df):
        outside = df[(df["Preco_num"] < self.min_price) | (df["Preco_num"] > self.max_price)]
        if len(outside):
            examples = ", ".join(str(p) for p in outside["Preco_num"].head(3))
            yield f"{len(outside)} prices outside {self.min_price}-{self.max_price} € (e.g. {examples})"

    def _duplicates(self, df):
        # One price per station and fuel: the load would silently keep only one of them
        duplicates = int(df.duplicated(["Id", "Combustivel"]).sum())
        if duplicates:
            yield f"{duplicates} duplicated station x fuel rows"
