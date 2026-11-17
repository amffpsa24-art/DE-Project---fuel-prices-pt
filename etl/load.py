# LOAD: loads a day's prices into the PostgreSQL star schema

import logging
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# Project root = the folder above etl/, so paths work no matter where Python is run from
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# SQL that moves the staging table into the star schema
SQL_LOAD_FROM_STAGING = PROJECT_ROOT / "sql" / "load_from_staging.sql"


def resolve_conninfo(conninfo=None):
    """
    Returns the connection string to use. None means "the real database":
    reads .env into environment variables (PGHOST, PGUSER, PGPASSWORD, ...), and
    psycopg.connect() with an empty string picks them up automatically.
    """
    if conninfo is None:
        load_dotenv(PROJECT_ROOT / ".env")
        conninfo = ""
    return conninfo


class Warehouse:
    """
    The PostgreSQL star schema.

    conninfo: optional connection string. Normally left empty, so the settings
    come from .env (locally) or the environment (GitHub Actions). Tests pass
    their own, pointing to a separate test database.
    """

    # Columns of stg_precos, in the order rows are sent to the database
    STAGING_COLUMNS = [
        "snapshot_date", "posto_id", "nome", "marca", "tipo_posto", "morada",
        "localidade", "cod_postal", "municipio", "distrito", "latitude",
        "longitude", "combustivel", "preco", "data_atualizacao",
    ]

    # Which DataFrame column feeds each staging column
    COLUMN_MAP = {
        "posto_id": "Id",
        "nome": "Nome",
        "marca": "Marca",
        "tipo_posto": "TipoPosto",
        "morada": "Morada",
        "localidade": "Localidade",
        "cod_postal": "CodPostal",
        "municipio": "Municipio",
        "distrito": "Distrito",
        "latitude": "Latitude",
        "longitude": "Longitude",
        "combustivel": "Combustivel",
        "preco": "Preco_num",
        "data_atualizacao": "DataAtualizacao",
    }

    def __init__(self, conninfo=None):
        self.conninfo = resolve_conninfo(conninfo)

    @classmethod
    def to_rows(cls, df, snapshot_date):
        """
        Turns the DataFrame into a list of tuples in the stg_precos column order.
        Missing values (NaN) become None, which PostgreSQL stores as NULL.
        """
        staging = pd.DataFrame({target: df[source] for target, source in cls.COLUMN_MAP.items()})
        staging.insert(0, "snapshot_date", snapshot_date)
        staging = staging[cls.STAGING_COLUMNS]

        # astype(object) + where(): replace every NaN with None
        staging = staging.astype(object).where(staging.notna(), None)
        return list(staging.itertuples(index=False, name=None))

    def load(self, df, snapshot_date):
        """
        Fills the staging table, then runs the SQL that loads the dimensions and the fact table.
        Everything happens in ONE transaction: if any step fails, nothing from this run is kept.
        Returns the number of fact rows for the day.
        """
        rows = self.to_rows(df, snapshot_date)
        sql_load = SQL_LOAD_FROM_STAGING.read_text(encoding="utf-8")

        # "with" commits if the block finishes, and rolls back if an error happens
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                # 1. Empty the staging table from any previous run
                cur.execute("TRUNCATE stg_precos")

                # 2. Bulk-copy the rows into staging (COPY is much faster than row-by-row INSERTs)
                columns = ", ".join(self.STAGING_COLUMNS)
                with cur.copy(f"COPY stg_precos ({columns}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write_row(row)
                log.info("Staged %d rows in stg_precos", len(rows))

                # 3. Staging -> dimensions -> fact table
                cur.execute(sql_load)

                # 4. How many fact rows exist for this day
                cur.execute(
                    "SELECT COUNT(*) FROM fact_precos WHERE data_key = %s",
                    (int(snapshot_date.strftime("%Y%m%d")),),
                )
                day_total = cur.fetchone()[0]

        # Fewer rows than staged means some were dropped without an error. The usual cause:
        # a day loaded out of date order, so some stations have no version valid on that day
        if day_total < len(rows):
            log.warning("Only %d of %d staged rows are in fact_precos for %s: was this day loaded out of date order?",
                        day_total, len(rows), snapshot_date)
        log.info("Loaded PostgreSQL: %d price rows for %s", day_total, snapshot_date)
        return day_total
