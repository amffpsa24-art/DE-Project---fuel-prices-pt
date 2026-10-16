# LOAD: saves the raw CSV snapshot, then loads PostgreSQL

# Created: 27/09/2026
# Updated: 04/10/2026 (PostgreSQL star schema)
# Updated: 07/10/2026 (optional connection string, so tests can use a separate database)
# Updated: 11/10/2026 (logging; pipeline.py calls save_raw_csv and load_postgres itself, with checks in between)
# Updated: 16/10/2026 (RawStore and Warehouse classes: the folder and the connection string live on the object)

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

log = logging.getLogger(__name__)

# Project root = the folder above etl/, so paths work no matter where Python is run from
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Raw layer: one CSV per run
PASTA_RAW = PROJECT_ROOT / "data" / "raw"

# SQL that moves the staging table into the star schema
SQL_LOAD_FROM_STAGING = PROJECT_ROOT / "sql" / "load_from_staging.sql"


def resolver_conninfo(conninfo=None):
    """
    Returns the connection string to use. None means "the real database":
    reads .env into environment variables (PGHOST, PGUSER, PGPASSWORD, ...), and
    psycopg.connect() with an empty string picks them up automatically.
    """
    if conninfo is None:
        load_dotenv(PROJECT_ROOT / ".env")
        conninfo = ""
    return conninfo


class RawStore:
    """Raw layer: one CSV per day, e.g. data/raw/fuel_prices_2026-10-04.csv. Never overwrites other days."""

    PREFIXO = "fuel_prices_"

    def __init__(self, pasta=PASTA_RAW):
        self.pasta = Path(pasta)

    def caminho(self, snapshot_date):
        return self.pasta / f"{self.PREFIXO}{snapshot_date.isoformat()}.csv"

    def save(self, df, snapshot_date):
        """Saves the DataFrame exactly as transformed and returns the file's path."""
        self.pasta.mkdir(parents=True, exist_ok=True)
        caminho = self.caminho(snapshot_date)

        # index=False: don't write pandas' internal row numbers as a column
        df.to_csv(caminho, index=False)
        log.info("Saved %d rows to %s", len(df), caminho)
        return caminho

    def snapshots(self):
        """Every saved day as (date, path), oldest first (sorted() works because names hold ISO dates)."""
        for caminho in sorted(self.pasta.glob(f"{self.PREFIXO}*.csv")):
            # "fuel_prices_2026-09-27" -> 2026-09-27
            yield date.fromisoformat(caminho.stem.removeprefix(self.PREFIXO)), caminho


class Warehouse:
    """
    Modelled layer: the PostgreSQL star schema.

    conninfo: optional connection string. Normally left empty, so the settings
    come from .env (locally) or the environment (GitHub Actions). Tests pass
    their own, pointing to a separate test database.
    """

    # Columns of stg_precos, in the order rows are sent to the database
    COLUNAS_STAGING = [
        "snapshot_date", "posto_id", "nome", "marca", "tipo_posto", "morada",
        "localidade", "cod_postal", "municipio", "distrito", "latitude",
        "longitude", "combustivel", "preco", "data_atualizacao",
    ]

    # Which DataFrame column feeds each staging column
    MAPA_COLUNAS = {
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
        self.conninfo = resolver_conninfo(conninfo)

    @classmethod
    def preparar_linhas(cls, df, snapshot_date):
        """
        Turns the DataFrame into a list of tuples in the stg_precos column order.
        Missing values (NaN) become None, which PostgreSQL stores as NULL.
        """
        staging = pd.DataFrame({destino: df[origem] for destino, origem in cls.MAPA_COLUNAS.items()})
        staging.insert(0, "snapshot_date", snapshot_date)
        staging = staging[cls.COLUNAS_STAGING]

        # astype(object) + where(): replace every NaN with None
        staging = staging.astype(object).where(staging.notna(), None)
        return list(staging.itertuples(index=False, name=None))

    def load(self, df, snapshot_date):
        """
        Fills the staging table, then runs the SQL that loads the dimensions and the fact table.
        Everything happens in ONE transaction: if any step fails, nothing from this run is kept.
        Returns the number of fact rows for the day.
        """
        linhas = self.preparar_linhas(df, snapshot_date)
        sql_load = SQL_LOAD_FROM_STAGING.read_text(encoding="utf-8")

        # "with" commits if the block finishes, and rolls back if an error happens
        with psycopg.connect(self.conninfo) as conn:
            with conn.cursor() as cur:
                # 1. Empty the staging table from any previous run
                cur.execute("TRUNCATE stg_precos")

                # 2. Bulk-copy the rows into staging (COPY is much faster than row-by-row INSERTs)
                colunas_sql = ", ".join(self.COLUNAS_STAGING)
                with cur.copy(f"COPY stg_precos ({colunas_sql}) FROM STDIN") as copy:
                    for linha in linhas:
                        copy.write_row(linha)
                log.info("Staged %d rows in stg_precos", len(linhas))

                # 3. Staging -> dimensions -> fact table
                cur.execute(sql_load)

                # 4. Report how many fact rows exist for this day
                cur.execute(
                    "SELECT COUNT(*) FROM fact_precos WHERE data_key = %s",
                    (int(snapshot_date.strftime("%Y%m%d")),),
                )
                total_dia = cur.fetchone()[0]

        log.info("Loaded PostgreSQL: %d price rows for %s", total_dia, snapshot_date)
        return total_dia
