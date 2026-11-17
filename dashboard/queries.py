# QUERIES: every database read the dashboard makes
#
# Connection settings come from .streamlit/secrets.toml (git-ignored), using the read-only user.
# Results are cached for 1 hour: the data only changes once a day, so most visits never touch the database.

import pandas as pd
import psycopg
import streamlit as st

CACHE_SECONDS = 3600


def run_query(sql, params=None):
    """Runs a SQL query with the read-only user and returns a DataFrame."""
    with psycopg.connect(**st.secrets["db"]) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [c.name for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=columns)


def to_float(df, *columns):
    """NUMERIC arrives as Python Decimal; charts and maths need regular floats."""
    for c in columns:
        df[c] = df[c].astype(float)
    return df


def build_filters(f):
    """
    Turns the sidebar choices into SQL conditions + parameters.
    Filtering happens in the database, so only the rows needed travel to the app.
    An empty choice means 'no filter'.
    """
    clauses, params = ["dias_desde_atualizacao <= %s"], [f["max_age"]]
    for column, values in [("distrito", f["districts"]), ("municipio", f["municipalities"]),
                           ("tipo_posto", f["types"]), ("marca", f["brands"])]:
        if values:
            clauses.append(f"{column} = ANY(%s)")   # = ANY(list): matches any value in the list
            params.append(list(values))
    if f["search"]:
        clauses.append("posto ILIKE %s")           # ILIKE = case-insensitive text match
        params.append(f"%{f['search']}%")
    return " AND ".join(clauses), params


@st.cache_data(ttl=CACHE_SECONDS)
def load_fuels():
    return run_query("SELECT nome FROM dim_combustivel ORDER BY nome")["nome"].tolist()


@st.cache_data(ttl=CACHE_SECONDS)
def load_dates():
    """Every day that has a snapshot, oldest first."""
    return run_query("SELECT data FROM dim_data ORDER BY data")["data"].tolist()


@st.cache_data(ttl=CACHE_SECONDS)
def load_station_count(day):
    return int(run_query("SELECT COUNT(DISTINCT posto_id) AS n FROM vw_precos WHERE data = %s", (day,))["n"].iloc[0])


@st.cache_data(ttl=CACHE_SECONDS)
def load_options(fuel, day):
    """Values available for the sidebar filters, on one day, for one fuel."""
    return run_query(
        "SELECT DISTINCT distrito, municipio, tipo_posto, marca FROM vw_precos WHERE combustivel = %s AND data = %s",
        (fuel, day),
    )


@st.cache_data(ttl=CACHE_SECONDS)
def load_day(fuel, day, f):
    """Every matching station's price for one fuel on one day."""
    where, params = build_filters(f)
    df = run_query(
        f"""
        SELECT posto_id, posto, marca, tipo_posto, morada, localidade, municipio, distrito,
               latitude, longitude, preco, data_atualizacao, dias_desde_atualizacao
        FROM vw_precos
        WHERE combustivel = %s AND data = %s AND {where}
        """,
        [fuel, day] + params,
    )
    return to_float(df, "preco")


@st.cache_data(ttl=CACHE_SECONDS)
def load_series(fuels, start, end, f):
    """
    Daily price sums and counts per fuel and district.
    Sums and counts (instead of averages) let pandas re-average correctly when combining groups.
    """
    where, params = build_filters(f)
    df = run_query(
        f"""
        SELECT data, combustivel, distrito, SUM(preco) AS soma, COUNT(*) AS n
        FROM vw_precos
        WHERE combustivel = ANY(%s) AND data BETWEEN %s AND %s AND {where}
        GROUP BY data, combustivel, distrito
        """,
        [list(fuels), start, end] + params,
    )
    return to_float(df, "soma")


@st.cache_data(ttl=CACHE_SECONDS)
def load_station_history(posto_id, start, end):
    df = run_query(
        """
        SELECT data, combustivel, preco, marca
        FROM vw_precos
        WHERE posto_id = %s AND data BETWEEN %s AND %s
        ORDER BY data
        """,
        (posto_id, start, end),
    )
    return to_float(df, "preco")


@st.cache_data(ttl=CACHE_SECONDS)
def load_station_versions(posto_id):
    """Every version of a station's details (SCD Type 2)."""
    return run_query(
        """
        SELECT nome, marca, tipo_posto, morada, municipio, valido_de, valido_ate, atual
        FROM dim_postos WHERE posto_id = %s ORDER BY valido_de
        """,
        (posto_id,),
    )
