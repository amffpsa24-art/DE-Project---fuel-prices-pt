# DATA QUALITY: checks a day's data BEFORE it reaches the database, and stops a bad load
# Created: 11/10/2026
#
# Why: a load can succeed technically and still be wrong (half a day's stations, prices parsed as 1164
# instead of 1.164...). Stopping it keeps bad data out of the warehouse; the run is recorded as failed,
# and the backup run gets another chance.

import logging

log = logging.getLogger(__name__)

# Thresholds, based on real snapshots (11/10/2026: 13,479 rows, prices from 1.00 to 3.28 €)
MIN_REGISTOS = 12_000      # recent days: 13,479 to 13,938 rows
MAX_REGISTOS = 16_000
PRECO_MIN, PRECO_MAX = 0.5, 5.0    # € per litre / kg / m3; outside this is a parsing error, not a price

# Columns the load needs (see MAPA_COLUNAS in load.py)
COLUNAS_OBRIGATORIAS = ["Id", "Nome", "Marca", "TipoPosto", "Morada", "Localidade", "CodPostal", "Municipio",
                        "Distrito", "Latitude", "Longitude", "Combustivel", "Preco_num", "DataAtualizacao"]
# Columns that must never be empty: the database requires them (NOT NULL)
CAMPOS_SEM_VAZIOS = ["Id", "Nome", "Combustivel", "Preco_num"]


class DataQualityError(Exception):
    """The day's data failed one or more checks; nothing was loaded."""


def verificar(df):
    """Runs every check and raises DataQualityError listing ALL problems found (not just the first)."""
    problemas = []

    # 1. Schema: every column the load uses must exist
    em_falta = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if em_falta:
        # Without these columns the other checks can't run
        raise DataQualityError(f"missing columns: {', '.join(em_falta)}")

    # 2. Volume: far fewer rows than usual means a partial extract; far more, a pagination bug
    if not MIN_REGISTOS <= len(df) <= MAX_REGISTOS:
        problemas.append(f"{len(df)} rows, expected {MIN_REGISTOS:,} to {MAX_REGISTOS:,}")

    # 3. Required fields: empty values here would break the load or create nameless stations
    for coluna in CAMPOS_SEM_VAZIOS:
        vazios = int(df[coluna].isna().sum())
        if vazios:
            problemas.append(f"{vazios} rows with empty {coluna}")

    # 4. Price range
    fora = df[(df["Preco_num"] < PRECO_MIN) | (df["Preco_num"] > PRECO_MAX)]
    if len(fora):
        exemplos = ", ".join(str(p) for p in fora["Preco_num"].head(3))
        problemas.append(f"{len(fora)} prices outside {PRECO_MIN}-{PRECO_MAX} € (e.g. {exemplos})")

    # 5. Duplicates: one price per station and fuel. The load would silently keep only one of them.
    duplicados = int(df.duplicated(["Id", "Combustivel"]).sum())
    if duplicados:
        problemas.append(f"{duplicados} duplicated station x fuel rows")

    if problemas:
        raise DataQualityError("; ".join(problemas))
    log.info("Quality checks passed: %d rows", len(df))
