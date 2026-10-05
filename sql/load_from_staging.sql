--- Load staging data into the dimensional model
-- Created: 04/10/2026
-- Assumes snapshots are processed chronologically.

-- Date dimension
INSERT INTO dim_data (
    data_key,
    data,
    ano,
    trimestre,
    mes,
    dia,
    dia_semana,
    fim_de_semana
)
SELECT DISTINCT
    TO_CHAR(snapshot_date, 'YYYYMMDD')::INTEGER,
    snapshot_date,
    EXTRACT(YEAR FROM snapshot_date),
    EXTRACT(QUARTER FROM snapshot_date),
    EXTRACT(MONTH FROM snapshot_date),
    EXTRACT(DAY FROM snapshot_date),
    EXTRACT(ISODOW FROM snapshot_date),
    EXTRACT(ISODOW FROM snapshot_date) IN (6, 7)
FROM stg_precos
ON CONFLICT (data_key) DO NOTHING;


-- Fuel dimension
INSERT INTO dim_combustivel (nome)
SELECT DISTINCT s.combustivel
FROM stg_precos AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM dim_combustivel AS c
    WHERE c.nome = s.combustivel
);


-- Close the current SCD2 version when station attributes change.
UPDATE dim_postos AS d
SET
    valido_ate = s.snapshot_date - 1,
    atual = FALSE
FROM (
    SELECT DISTINCT ON (posto_id) *
    FROM stg_precos
    ORDER BY posto_id, combustivel
) AS s
WHERE d.posto_id = s.posto_id
  AND d.atual
  AND s.snapshot_date > d.valido_de
  AND (
      d.nome,
      d.marca,
      d.tipo_posto,
      d.morada,
      d.localidade,
      d.cod_postal,
      d.municipio,
      d.distrito,
      d.latitude,
      d.longitude
  ) IS DISTINCT FROM (
      s.nome,
      s.marca,
      s.tipo_posto,
      s.morada,
      s.localidade,
      s.cod_postal,
      s.municipio,
      s.distrito,
      s.latitude,
      s.longitude
  );

-- Add new stations and new SCD2 versions.
INSERT INTO dim_postos (
    posto_id,
    nome,
    marca,
    tipo_posto,
    morada,
    localidade,
    cod_postal,
    municipio,
    distrito,
    latitude,
    longitude,
    valido_de
)
SELECT DISTINCT ON (s.posto_id)
    s.posto_id,
    s.nome,
    s.marca,
    s.tipo_posto,
    s.morada,
    s.localidade,
    s.cod_postal,
    s.municipio,
    s.distrito,
    s.latitude,
    s.longitude,
    s.snapshot_date
FROM stg_precos AS s
WHERE NOT EXISTS (
    SELECT 1
    FROM dim_postos AS d
    WHERE d.posto_id = s.posto_id
      AND d.atual
)
ORDER BY s.posto_id, s.combustivel;


-- Load daily prices against the station version valid on the snapshot date.
INSERT INTO fact_precos (
    data_key,
    posto_sk,
    combustivel_id,
    preco,
    data_atualizacao
)
SELECT
    TO_CHAR(s.snapshot_date, 'YYYYMMDD')::INTEGER,
    d.posto_sk,
    c.combustivel_id,
    s.preco,
    s.data_atualizacao
FROM stg_precos AS s
JOIN dim_postos AS d
    ON d.posto_id = s.posto_id
   AND s.snapshot_date BETWEEN d.valido_de AND d.valido_ate
JOIN dim_combustivel AS c
    ON c.nome = s.combustivel
ON CONFLICT (
    data_key,
    posto_sk,
    combustivel_id
) DO NOTHING;