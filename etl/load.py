# ============================================
# LOAD: saves the raw CSV snapshot, then loads PostgreSQL
# ============================================
# Created: 27/09/2026
# Updated: 04/10/2026 (PostgreSQL star schema)
# Updated: 07/10/2026 (optional connection string, so tests can use a separate database)

from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv

# Project root = the folder above etl/, so paths work no matter where Python is run from
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Raw layer: one CSV per run
PASTA_RAW = PROJECT_ROOT / "data" / "raw"

# SQL that moves the staging table into the star schema
SQL_LOAD_FROM_STAGING = PROJECT_ROOT / "sql" / "load_from_staging.sql"

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


def save_raw_csv(df, snapshot_date):
    """
    Raw layer: saves the DataFrame exactly as transformed,
    e.g. data/raw/fuel_prices_2026-10-04.csv. Never overwrites other days.
    """
    PASTA_RAW.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_RAW / f"fuel_prices_{snapshot_date.isoformat()}.csv"

    # index=False: don't write pandas' internal row numbers as a column
    df.to_csv(caminho, index=False)
    print(f"Saved {len(df)} rows to {caminho}")
    return caminho


def preparar_linhas(df, snapshot_date):
    """
    Turns the DataFrame into a list of tuples in the stg_precos column order.
    Missing values (NaN) become None, which PostgreSQL stores as NULL.
    """
    staging = pd.DataFrame({destino: df[origem] for destino, origem in MAPA_COLUNAS.items()})
    staging.insert(0, "snapshot_date", snapshot_date)
    staging = staging[COLUNAS_STAGING]

    # astype(object) + where(): replace every NaN with None
    staging = staging.astype(object).where(staging.notna(), None)
    return list(staging.itertuples(index=False, name=None))


def load_postgres(df, snapshot_date, conninfo=None):
    """
    Modelled layer: fills the staging table, then runs the SQL that loads
    the dimensions and the fact table. Everything happens in ONE transaction:
    if any step fails, nothing from this run is kept.

    conninfo: optional connection string. Normally left empty, so the settings
    come from .env (locally) or the environment (GitHub Actions). Tests pass
    their own, pointing to a separate test database.
    """
    if conninfo is None:
        # Reads .env into environment variables (PGHOST, PGUSER, PGPASSWORD, ...).
        # psycopg.connect() with an empty string picks them up automatically.
        load_dotenv(PROJECT_ROOT / ".env")
        conninfo = ""

    linhas = preparar_linhas(df, snapshot_date)
    sql_load = SQL_LOAD_FROM_STAGING.read_text(encoding="utf-8")

    # "with" commits if the block finishes, and rolls back if an error happens
    with psycopg.connect(conninfo) as conn:
        with conn.cursor() as cur:
            # 1. Empty the staging table from any previous run
            cur.execute("TRUNCATE stg_precos")

            # 2. Bulk-copy the rows into staging (COPY is much faster than row-by-row INSERTs)
            colunas_sql = ", ".join(COLUNAS_STAGING)
            with cur.copy(f"COPY stg_precos ({colunas_sql}) FROM STDIN") as copy:
                for linha in linhas:
                    copy.write_row(linha)
            print(f"Staged {len(linhas)} rows in stg_precos")

            # 3. Staging -> dimensions -> fact table
            cur.execute(sql_load)

            # 4. Report how many fact rows exist for this day
            cur.execute(
                "SELECT COUNT(*) FROM fact_precos WHERE data_key = %s",
                (int(snapshot_date.strftime("%Y%m%d")),),
            )
            total_dia = cur.fetchone()[0]

    print(f"Loaded PostgreSQL: {total_dia} price rows for {snapshot_date.isoformat()}")


def load(df, snapshot_date=None):
    """
    Full load step: raw CSV first, then PostgreSQL.
    snapshot_date defaults to today; backfill.py passes older dates.
    """
    if snapshot_date is None:
        snapshot_date = date.today()

    save_raw_csv(df, snapshot_date)
    load_postgres(df, snapshot_date)