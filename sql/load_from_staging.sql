-- ============================================
-- LOAD FROM STAGING: moves stg_precos into the star schema
-- ============================================
-- Created: 04/10/2026
-- Run by etl/load.py, inside one transaction, after stg_precos has been filled.
-- Order matters: the three dimensions first, then the fact table that references them.


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


-- 3. dim_postos: add new stations, overwrite details of known ones (SCD Type 1)
-- DISTINCT ON keeps ONE row per station: staging has one row per station x fuel,
-- and ON CONFLICT DO UPDATE refuses to update the same station twice in one statement.
INSERT INTO dim_postos (
    posto_id, nome, marca, tipo_posto, morada, localidade, cod_postal,
    municipio, distrito, latitude, longitude, primeira_vez, ultima_vez
)
SELECT DISTINCT ON (posto_id)
    posto_id, nome, marca, tipo_posto, morada, localidade, cod_postal,
    municipio, distrito, latitude, longitude, snapshot_date, snapshot_date
FROM stg_precos
ORDER BY posto_id
ON CONFLICT (posto_id) DO UPDATE SET
    nome         = EXCLUDED.nome,
    marca        = EXCLUDED.marca,
    tipo_posto   = EXCLUDED.tipo_posto,
    morada       = EXCLUDED.morada,
    localidade   = EXCLUDED.localidade,
    cod_postal   = EXCLUDED.cod_postal,
    municipio    = EXCLUDED.municipio,
    distrito     = EXCLUDED.distrito,
    latitude     = EXCLUDED.latitude,
    longitude    = EXCLUDED.longitude,
    -- LEAST / GREATEST keep these right even when loading old snapshots after newer ones (backfill)
    primeira_vez = LEAST(dim_postos.primeira_vez, EXCLUDED.primeira_vez),
    ultima_vez   = GREATEST(dim_postos.ultima_vez, EXCLUDED.ultima_vez);


-- 4. fact_precos: the prices, now pointing to the dimension rows above
-- ON CONFLICT DO NOTHING = idempotent: rerunning the same day skips rows that already exist
INSERT INTO fact_precos (data_key, posto_id, combustivel_id, preco, data_atualizacao)
SELECT
    TO_CHAR(s.snapshot_date, 'YYYYMMDD')::INTEGER,
    s.posto_id,
    c.combustivel_id,
    s.preco,
    s.data_atualizacao
FROM stg_precos AS s
JOIN dim_combustivel AS c ON c.nome = s.combustivel
ON CONFLICT (data_key, posto_id, combustivel_id) DO NOTHING;
