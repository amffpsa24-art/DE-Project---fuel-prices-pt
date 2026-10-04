-- ============================================
-- VIEWS: read-friendly layer for the dashboard
-- ============================================
-- Created: 04/10/2026
-- Updated: 04/10/2026 (dim_postos as SCD Type 2; days since the station's last update)
-- Run with:  psql "<connection string>" -f sql/views.sql
--
-- A view is a saved query: it stores no data, it runs the query every time it is read.
-- The dashboard reads this view instead of joining the star schema itself.

-- vw_precos: every price with its station, fuel and date details in one row.
-- Station details are the ones that were true ON THAT DAY (SCD Type 2),
-- e.g. a station that switched from GALP to PRIO shows GALP for its older prices.
CREATE OR REPLACE VIEW vw_precos AS
SELECT
    -- date
    d.data,
    d.data_key,
    d.ano,
    d.mes,
    d.dia_semana,
    d.fim_de_semana,
    -- station (as it was on that day)
    p.posto_id,
    p.nome            AS posto,
    p.marca,
    p.tipo_posto,
    p.morada,
    p.localidade,
    p.municipio,
    p.distrito,
    p.latitude,
    p.longitude,
    -- fuel and price
    c.nome            AS combustivel,
    f.preco,
    f.data_atualizacao,
    -- How many days the station had gone without changing this price, on the snapshot day.
    -- Large values flag stale prices (e.g. a fuel the station stopped reporting).
    -- New columns go at the END: CREATE OR REPLACE VIEW can add columns, but not reorder them.
    (d.data - f.data_atualizacao::DATE) AS dias_desde_atualizacao
FROM fact_precos      AS f
JOIN dim_data         AS d USING (data_key)
JOIN dim_postos       AS p USING (posto_sk)
JOIN dim_combustivel  AS c USING (combustivel_id);
