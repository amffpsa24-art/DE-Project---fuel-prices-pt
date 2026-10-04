-- ============================================
-- DASHBOARD ROLE: read-only database user for the Streamlit app
-- ============================================
-- Created: 04/10/2026
--
-- Principle of least privilege: the dashboard can only READ, never change data.
-- If its credentials ever leaked, nobody could modify or delete anything with them.

--     CREATE ROLE dashboard_reader WITH LOGIN PASSWORD '<generated password>';
--     psql "<connection string>" -f sql/dashboard_role.sql

-- Allow the role to connect to the database and see the objects in the public schema
GRANT CONNECT ON DATABASE fuel_prices TO dashboard_reader;
GRANT USAGE ON SCHEMA public TO dashboard_reader;

-- Allow reading the dashboard view and the dimensions (used for the filter lists).
-- Nothing else: no INSERT, UPDATE, DELETE, and no access to the staging table.
GRANT SELECT ON vw_precos, dim_postos, dim_combustivel, dim_data TO dashboard_reader;
