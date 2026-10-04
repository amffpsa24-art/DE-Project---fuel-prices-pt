-- ============================================
-- STAR SCHEMA for the fuel prices warehouse
-- ============================================
-- Created: 04/10/2026
-- Run with:  psql -U postgres -d fuel_prices -f sql/schema.sql
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
-- dim_postos: one row per station (SCD Type 1: changes overwrite the old values)
-- --------------------------------------------
-- Natural key: DGEG's own station Id.
-- An upgrade to SCD Type 2 would add a surrogate key, because one station would then have several rows.
CREATE TABLE IF NOT EXISTS dim_postos (
    posto_id         INTEGER           PRIMARY KEY,   -- DGEG "Id"
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
    primeira_vez     DATE              NOT NULL,      -- first snapshot this station appeared in
    ultima_vez       DATE              NOT NULL       -- latest snapshot it appeared in (old date = station may have closed)
);


-- --------------------------------------------
-- fact_precos: periodic snapshot fact table
-- --------------------------------------------
-- Grain: one row per station x fuel x snapshot day
CREATE TABLE IF NOT EXISTS fact_precos (
    data_key          INTEGER       NOT NULL REFERENCES dim_data (data_key),
    posto_id          INTEGER       NOT NULL REFERENCES dim_postos (posto_id),
    combustivel_id    INTEGER       NOT NULL REFERENCES dim_combustivel (combustivel_id),
    preco             NUMERIC(6,3)  NOT NULL CHECK (preco > 0),  -- exact decimals, never FLOAT for money
    data_atualizacao  TIMESTAMP,                                 -- when the STATION last changed this price (Lisbon local time)
    carregado_em      TIMESTAMPTZ   NOT NULL DEFAULT now(),      -- when OUR pipeline inserted the row

    -- Idempotency: the same station + fuel + day can only exist once,
    -- so rerunning the pipeline on the same day cannot create duplicates
    PRIMARY KEY (data_key, posto_id, combustivel_id)
);

-- The primary key already indexes queries that start with data_key.
-- These two help queries that filter by station or by fuel.
CREATE INDEX IF NOT EXISTS idx_fact_precos_posto       ON fact_precos (posto_id);
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
