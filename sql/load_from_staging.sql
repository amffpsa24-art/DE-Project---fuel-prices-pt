-- ============================================
-- LOAD FROM STAGING: moves stg_precos into the star schema
-- ============================================
-- Created: 04/10/2026
-- Updated: 04/10/2026 (dim_postos as SCD Type 2)
-- Run by etl/load.py, inside one transaction, after stg_precos has been filled.
-- Order matters: the three dimensions first, then the fact table that references them.
--
-- Assumption: snapshots are loaded in date order (daily runs are; backfill.py sorts its files).


-- 1. dim_data: add the snapshot day(s) if they don't exist yet
INSERT INTO dim_data (data_key, data, ano, trimestre, mes, dia, dia_semana, fim_de_semana)
SELECT DISTINCT
    TO_CHAR(snapshot_date, 'YYYYMMDD')::INTEGER,
    snapshot_date,
    EXTRACT(YEAR    FROM snapshot_date),
    EXTRACT(QUARTER FROM snapshot_date),
    EXTRACT(MONTH   FROM snapshot_date),
    EXTRACT(DAY     FROM snapshot_date),
    EXTRACT(ISODOW  FROM snapshot_date),
    EXTRACT(ISODOW  FROM snapshot_date) IN (6, 7)
FROM stg_precos
ON CONFLICT (data_key) DO NOTHING;


-- 2. dim_combustivel: add fuel types never seen before
-- NOT EXISTS filters known fuels first, so the SERIAL counter isn't used up by skipped rows
INSERT INTO dim_combustivel (nome)
SELECT DISTINCT s.combustivel
FROM stg_precos AS s
WHERE NOT EXISTS (
    SELECT 1 FROM dim_combustivel AS c WHERE c.nome = s.combustivel
);


-- 3a. dim_postos, SCD Type 2: CLOSE the current version of stations whose details changed
-- Staging has one row per station x fuel, so DISTINCT ON keeps one row per station first.
-- IS DISTINCT FROM compares the whole list of columns and treats two NULLs as equal.
-- "snapshot_date > valido_de" ignores changes on the same day the version started (e.g. a same-day rerun).
UPDATE dim_postos AS d
SET valido_ate = s.snapshot_date - 1,     -- the old version was true until yesterday
    atual      = FALSE
FROM (
    SELECT DISTINCT ON (posto_id) *
    FROM stg_precos
    ORDER BY posto_id, combustivel
) AS s
WHERE d.posto_id = s.posto_id
  AND d.atual
  AND s.snapshot_date > d.valido_de
  AND (d.nome, d.marca, d.tipo_posto, d.morada, d.localidade, d.cod_postal,
       d.municipio, d.distrito, d.latitude, d.longitude)
      IS DISTINCT FROM
      (s.nome, s.marca, s.tipo_posto, s.morada, s.localidade, s.cod_postal,
       s.municipio, s.distrito, s.latitude, s.longitude);


-- 3b. dim_postos: ADD a current version for every station that has none
-- This covers both brand-new stations and the stations just closed in step 3a.
INSERT INTO dim_postos (
    posto_id, nome, marca, tipo_posto, morada, localidade, cod_postal,
    municipio, distrito, latitude, longitude, valido_de
)
SELECT DISTINCT ON (s.posto_id)
    s.posto_id, s.nome, s.marca, s.tipo_posto, s.morada, s.localidade, s.cod_postal,
    s.municipio, s.distrito, s.latitude, s.longitude, s.snapshot_date
FROM stg_precos AS s
WHERE NOT EXISTS (
    SELECT 1 FROM dim_postos AS d
    WHERE d.posto_id = s.posto_id AND d.atual
)
ORDER BY s.posto_id, s.combustivel;


-- 4. fact_precos: each price points to the station VERSION that was valid on the snapshot day
-- ON CONFLICT DO NOTHING = idempotent: rerunning the same day skips rows that already exist
INSERT INTO fact_precos (data_key, posto_sk, combustivel_id, preco, data_atualizacao)
SELECT
    TO_CHAR(s.snapshot_date, 'YYYYMMDD')::INTEGER,
    d.posto_sk,
    c.combustivel_id,
    s.preco,
    s.data_atualizacao
FROM stg_precos AS s
JOIN dim_postos      AS d ON d.posto_id = s.posto_id
                         AND s.snapshot_date BETWEEN d.valido_de AND d.valido_ate
JOIN dim_combustivel AS c ON c.nome = s.combustivel
ON CONFLICT (data_key, posto_sk, combustivel_id) DO NOTHING;
