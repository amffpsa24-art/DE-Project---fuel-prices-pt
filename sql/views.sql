--- Dashboard-facing view
-- Created: 04/10/2026
-- Updated: 04/10/2026

CREATE OR REPLACE VIEW vw_precos AS
SELECT
    d.data,
    d.data_key,
    d.ano,
    d.mes,
    d.dia_semana,
    d.fim_de_semana,
    p.posto_id,
    p.nome AS posto,
    p.marca,
    p.tipo_posto,
    p.morada,
    p.localidade,
    p.municipio,
    p.distrito,
    p.latitude,
    p.longitude,
    c.nome AS combustivel,
    f.preco,
    f.data_atualizacao,
    -- Number of days between the snapshot and the station's last price update.
    (d.data - f.data_atualizacao::DATE) AS dias_desde_atualizacao
FROM fact_precos AS f
JOIN dim_data AS d
    USING (data_key)
JOIN dim_postos AS p
    USING (posto_sk)
JOIN dim_combustivel AS c
    USING (combustivel_id);