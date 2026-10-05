-- Read-only role for the Streamlit dashboard
-- Created: 04/10/2026

GRANT CONNECT ON DATABASE fuel_prices TO dashboard_reader;
GRANT USAGE ON SCHEMA public TO dashboard_reader;

GRANT SELECT
ON vw_precos, dim_postos, dim_combustivel, dim_data
TO dashboard_reader;