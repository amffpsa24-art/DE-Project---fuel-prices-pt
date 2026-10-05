# Load transformed fuel-price data into PostgreSQL
# Created: 27/09/2026
# Updated: 04/10/2026

from datetime import date
from pathlib import Path

import pandas as pd
import psycopg
from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PASTA_RAW = PROJECT_ROOT / "data" / "raw"
SQL_LOAD_FROM_STAGING = PROJECT_ROOT / "sql" / "load_from_staging.sql"

COLUNAS_STAGING = [
    "snapshot_date",
    "posto_id",
    "nome",
    "marca",
    "tipo_posto",
    "morada",
    "localidade",
    "cod_postal",
    "municipio",
    "distrito",
    "latitude",
    "longitude",
    "combustivel",
    "preco",
    "data_atualizacao",
]

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
    """Save one local snapshot for each pipeline run."""

    PASTA_RAW.mkdir(parents=True, exist_ok=True)

    caminho = PASTA_RAW / f"fuel_prices_{snapshot_date.isoformat()}.csv"
    df.to_csv(caminho, index=False)

    print(f"Saved {len(df)} rows to {caminho}")
    return caminho


def preparar_linhas(df, snapshot_date):
    """Prepare rows in the same structure as stg_precos."""

    staging = pd.DataFrame(
        {
            destino: df[origem]
            for destino, origem in MAPA_COLUNAS.items()
        }
    )

    staging.insert(0, "snapshot_date", snapshot_date)
    staging = staging[COLUNAS_STAGING]

    # psycopg expects None rather than pandas NaN for SQL NULL values
    staging = staging.astype(object).where(staging.notna(), None)

    return list(
        staging.itertuples(
            index=False,
            name=None,
        )
    )


def load_postgres(df, snapshot_date):
    """Load staging data and update the dimensional model."""

    load_dotenv(PROJECT_ROOT / ".env")

    linhas = preparar_linhas(df, snapshot_date)
    sql_load = SQL_LOAD_FROM_STAGING.read_text(encoding="utf-8")

    with psycopg.connect() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE stg_precos")

            colunas_sql = ", ".join(COLUNAS_STAGING)

            with cur.copy(
                f"COPY stg_precos ({colunas_sql}) FROM STDIN"
            ) as copy:
                for linha in linhas:
                    copy.write_row(linha)

            print(f"Staged {len(linhas)} rows in stg_precos")

            cur.execute(sql_load)

            data_key = int(snapshot_date.strftime("%Y%m%d"))

            cur.execute(
                """
                SELECT COUNT(*)
                FROM fact_precos
                WHERE data_key = %s
                """,
                (data_key,),
            )

            total_dia = cur.fetchone()[0]

    print(
        f"Loaded PostgreSQL: {total_dia} price rows "
        f"for {snapshot_date.isoformat()}"
    )


def load(df, snapshot_date=None):
    """Save the snapshot and load it into PostgreSQL."""

    if snapshot_date is None:
        snapshot_date = date.today()

    save_raw_csv(df, snapshot_date)
    load_postgres(df, snapshot_date)