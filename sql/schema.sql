-- ============================================
-- STAR SCHEMA for the fuel prices warehouse
-- ============================================
-- Created: 04/10/2026
-- Updated: 04/10/2026 (dim_postos as SCD Type 2)
-- Run with:  psql "<connection string>" -f sql/schema.sql
--
-- Safe to run more than once: every table uses IF NOT EXISTS.
-- Order matters: dimensions first, then the fact table that references them.


-- --------------------------------------------
-- dim_data: one row per calendar day
-- --------------------------------------------
-- Key is an integer like 20261004 (warehouse convention: readable and sortable)
CREATE TABLE IF NOT EXISTS dim_data (
    data_key      INTEGER     PRIMARY KEY,         -- e.g. 20261004
    data          DATE        NOT NULL UNIQUE,     -- e.g. 2026-10-04
    ano           SMALLINT    NOT NULL,            -- year
    trimestre     SMALLINT    NOT NULL,            -- quarter, 1-4
    mes           SMALLINT    NOT NULL,            -- month, 1-12
    dia           SMALLINT    NOT NULL,            -- day of month, 1-31
    dia_semana    SMALLINT    NOT NULL,            -- ISO weekday: 1 = Monday ... 7 = Sunday
    fim_de_semana BOOLEAN     NOT NULL             -- TRUE on Saturday and Sunday
);


-- --------------------------------------------
-- dim_combustivel: one row per fuel type
-- --------------------------------------------
-- The API only gives fuel names, so we generate our own ID
CREATE TABLE IF NOT EXISTS dim_combustivel (
    combustivel_id  SERIAL  PRIMARY KEY,
    nome            TEXT    NOT NULL UNIQUE        -- e.g. 'Gasoleo simples', as sent by the API
);


-- --------------------------------------------
-- dim_postos: one row per VERSION of a station (SCD Type 2)
-- --------------------------------------------
-- When a station's details change (new brand, new name...), the old row is closed
-- and a new row is added, so history keeps the details that were true at the time.
--   posto_sk   = surrogate key: our own ID, one per version (what the fact table points to)
--   posto_id   = natural key: DGEG's station Id, the same for every version of a station
CREATE TABLE IF NOT EXISTS dim_postos (
    posto_sk         SERIAL            PRIMARY KEY,
    posto_id         INTEGER           NOT NULL,      -- DGEG "Id"
    nome             TEXT              NOT NULL,
    marca            TEXT,
    tipo_posto       TEXT,                            -- e.g. 'Outro', 'Autoestrada', 'Hipermercado'
    morada           TEXT,
    localidade       TEXT,
    cod_postal       TEXT,                            -- text, not number: '2580-243' has a dash and leading zeros matter
    municipio        TEXT,
    distrito         TEXT,
    latitude         DOUBLE PRECISION,                -- float is fine here: coordinates are never summed like money
    longitude        DOUBLE PRECISION,
    valido_de        DATE              NOT NULL,      -- first day this version was true
    valido_ate       DATE              NOT NULL DEFAULT '9999-12-31',  -- last day it was true ('9999-12-31' = still current)
    atual            BOOLEAN           NOT NULL DEFAULT TRUE,          -- TRUE only on the current version

    -- A station can't have two versions starting on the same day
    UNIQUE (posto_id, valido_de),
    CHECK (valido_ate >= valido_de)
);

-- At most ONE current version per station (a "partial" unique index: only applies to rows WHERE atual)
CREATE UNIQUE INDEX IF NOT EXISTS uq_dim_postos_atual ON dim_postos (posto_id) WHERE atual;


-- --------------------------------------------
-- fact_precos: periodic snapshot fact table
-- --------------------------------------------
-- Grain: one row per station x fuel x snapshot day
CREATE TABLE IF NOT EXISTS fact_precos (
    data_key          INTEGER       NOT NULL REFERENCES dim_data (data_key),
    posto_sk          INTEGER       NOT NULL REFERENCES dim_postos (posto_sk),   -- the station VERSION valid that day
    combustivel_id    INTEGER       NOT NULL REFERENCES dim_combustivel (combustivel_id),
    preco             NUMERIC(6,3)  NOT NULL CHECK (preco > 0),  -- exact decimals, never FLOAT for money
    data_atualizacao  TIMESTAMP,                                 -- when the STATION last changed this price (Lisbon local time)
    carregado_em      TIMESTAMPTZ   NOT NULL DEFAULT now(),      -- when OUR pipeline inserted the row

    -- Idempotency: the same station + fuel + day can only exist once,
    -- so rerunning the pipeline on the same day cannot create duplicates
    PRIMARY KEY (data_key, posto_sk, combustivel_id)
);

-- The primary key already indexes queries that start with data_key.
-- These two help queries that filter by station or by fuel.
CREATE INDEX IF NOT EXISTS idx_fact_precos_posto       ON fact_precos (posto_sk);
CREATE INDEX IF NOT EXISTS idx_fact_precos_combustivel ON fact_precos (combustivel_id);


-- --------------------------------------------
-- stg_precos: staging table (landing area, emptied at the start of every run)
-- --------------------------------------------
-- Python dumps the day's DataFrame here; SQL then moves it into the dimensions and the fact table.
-- UNLOGGED = faster writes, skips crash protection. Fine, because the data can always be reloaded.
CREATE UNLOGGED TABLE IF NOT EXISTS stg_precos (
    snapshot_date     DATE              NOT NULL,
    posto_id          INTEGER           NOT NULL,
    nome              TEXT,
    marca             TEXT,
    tipo_posto        TEXT,
    morada            TEXT,
    localidade        TEXT,
    cod_postal        TEXT,
    municipio         TEXT,
    distrito          TEXT,
    latitude          DOUBLE PRECISION,
    longitude         DOUBLE PRECISION,
    combustivel       TEXT              NOT NULL,
    preco             NUMERIC(6,3)      NOT NULL,
    data_atualizacao  TIMESTAMP
);
