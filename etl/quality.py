# DATA QUALITY: checks a day's data BEFORE it reaches the database, and stops a bad load
# Created: 11/10/2026
# Updated: 16/10/2026 (QualityChecker class: thresholds are constructor arguments, so tests can lower them)
#
# Why: a load can succeed technically and still be wrong (half a day's stations, prices parsed as 1164
# instead of 1.164...). Stopping it keeps bad data out of the warehouse; the run is recorded as failed,
# and the backup run gets another chance.

import logging

log = logging.getLogger(__name__)


class DataQualityError(Exception):
    """The day's data failed one or more checks; nothing was loaded."""


class QualityChecker:
    """Runs every check on a transformed DataFrame and raises DataQualityError if any fails."""

    # Columns the load needs (see Warehouse.MAPA_COLUNAS in load.py)
    COLUNAS_OBRIGATORIAS = ["Id", "Nome", "Marca", "TipoPosto", "Morada", "Localidade", "CodPostal", "Municipio",
                            "Distrito", "Latitude", "Longitude", "Combustivel", "Preco_num", "DataAtualizacao"]
    # Columns that must never be empty: the database requires them (NOT NULL)
    CAMPOS_SEM_VAZIOS = ["Id", "Nome", "Combustivel", "Preco_num"]

    # Defaults based on real snapshots (11/10/2026: 13,479 rows, prices from 1.00 to 3.28 €).
    # Prices are € per litre / kg / m3; outside 0.5-5.0 is a parsing error, not a price.
    def __init__(self, min_registos=12_000, max_registos=16_000, preco_min=0.5, preco_max=5.0):
        self.min_registos = min_registos
        self.max_registos = max_registos
        self.preco_min = preco_min
        self.preco_max = preco_max

    def verificar(self, df):
        """Runs every check and raises DataQualityError listing ALL problems found (not just the first)."""
        # 1. Schema: without these columns the other checks can't run, so stop at once
        em_falta = [c for c in self.COLUNAS_OBRIGATORIAS if c not in df.columns]
        if em_falta:
            raise DataQualityError(f"missing columns: {', '.join(em_falta)}")

        problemas = [
            *self._volume(df),
            *self._vazios(df),
            *self._precos(df),
            *self._duplicados(df),
        ]
        if problemas:
            raise DataQualityError("; ".join(problemas))
        log.info("Quality checks passed: %d rows", len(df))

    def _volume(self, df):
        # Far fewer rows than usual means a partial extract; far more, a pagination bug
        if not self.min_registos <= len(df) <= self.max_registos:
            yield f"{len(df)} rows, expected {self.min_registos:,} to {self.max_registos:,}"

    def _vazios(self, df):
        # Empty values here would break the load or create nameless stations
        for coluna in self.CAMPOS_SEM_VAZIOS:
            vazios = int(df[coluna].isna().sum())
            if vazios:
                yield f"{vazios} rows with empty {coluna}"

    def _precos(self, df):
        fora = df[(df["Preco_num"] < self.preco_min) | (df["Preco_num"] > self.preco_max)]
        if len(fora):
            exemplos = ", ".join(str(p) for p in fora["Preco_num"].head(3))
            yield f"{len(fora)} prices outside {self.preco_min}-{self.preco_max} € (e.g. {exemplos})"

    def _duplicados(self, df):
        # One price per station and fuel. The load would silently keep only one of them.
        duplicados = int(df.duplicated(["Id", "Combustivel"]).sum())
        if duplicados:
            yield f"{duplicados} duplicated station x fuel rows"
