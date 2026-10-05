-- Star schema for the fuel prices warehouse
-- Created: 04/10/2026
-- Updated: 04/10/2026

CREATE TABLE IF NOT EXISTS dim_data (
    data_key      INTEGER     PRIMARY KEY,
    data          DATE        NOT NULL UNIQUE,
    ano           SMALLINT    NOT NULL,
    trimestre     SMALLINT    NOT NULL,
    mes           SMALLINT    NOT NULL,
    dia           SMALLINT    NOT NULL,
    dia_semana    SMALLINT    NOT NULL,
    fim_de_semana BOOLEAN     NOT NULL
);


CREATE TABLE IF NOT EXISTS dim_combustivel (
    combustivel_id SERIAL PRIMARY KEY,
    nome           TEXT   NOT NULL UNIQUE
);


-- SCD Type 2 dimension: each row represents one version of a station.
CREATE TABLE IF NOT EXISTS dim_postos (
    posto_sk      SERIAL           PRIMARY KEY,
    posto_id      INTEGER          NOT NULL,
    nome          TEXT             NOT NULL,
    marca         TEXT,
    tipo_posto    TEXT,
    morada        TEXT,
    localidade    TEXT,
    cod_postal    TEXT,
    municipio     TEXT,
    distrito      TEXT,
    latitude      DOUBLE PRECISION,
    longitude     DOUBLE PRECISION,
    valido_de     DATE             NOT NULL,
    valido_ate    DATE             NOT NULL DEFAULT '9999-12-31',
    atual         BOOLEAN          NOT NULL DEFAULT TRUE,

    UNIQUE (posto_id, valido_de),
    CHECK (valido_ate >= valido_de)
);

-- Ensures that each station has at most one current version.
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_postos_atual
ON dim_postos (posto_id)
WHERE atual;


-- Periodic snapshot fact table.
--- Grain: one row per station version, fuel type and snapshot date.
CREATE TABLE IF NOT EXISTS fact_precos (
    data_key         INTEGER      NOT NULL REFERENCES dim_data (data_key),
    posto_sk         INTEGER      NOT NULL REFERENCES dim_postos (posto_sk),
    combustivel_id   INTEGER      NOT NULL REFERENCES dim_combustivel (combustivel_id),
    preco            NUMERIC(6,3) NOT NULL CHECK (preco > 0),
    data_atualizacao TIMESTAMP,
    carregado_em     TIMESTAMPTZ  NOT NULL DEFAULT now(),

    PRIMARY KEY (data_key, posto_sk, combustivel_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_precos_posto
ON fact_precos (posto_sk);

CREATE INDEX IF NOT EXISTS idx_fact_precos_combustivel
ON fact_precos (combustivel_id);


--- Temporary landing table used before loading the dimensional model.
CREATE UNLOGGED TABLE IF NOT EXISTS stg_precos (
    snapshot_date    DATE             NOT NULL,
    posto_id         INTEGER          NOT NULL,
    nome             TEXT,
    marca            TEXT,
    tipo_posto       TEXT,
    morada           TEXT,
    localidade       TEXT,
    cod_postal       TEXT,
    municipio        TEXT,
    distrito         TEXT,
    latitude         DOUBLE PRECISION,
    longitude        DOUBLE PRECISION,
    combustivel      TEXT             NOT NULL,
    preco            NUMERIC(6,3)     NOT NULL,
    data_atualizacao TIMESTAMP
);