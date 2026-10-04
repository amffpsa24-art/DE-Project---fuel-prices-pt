# ============================================
# DASHBOARD: Streamlit app reading the star schema through vw_precos
# ============================================
# Created: 04/10/2026
# Run locally (from the project root):  streamlit run dashboard/app.py
# Connection settings come from .streamlit/secrets.toml (git-ignored), using the read-only user.

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st

st.set_page_config(page_title="Fuel Prices PT", page_icon="⛽", layout="wide")

# Query results are cached for 1 hour: the data only changes once a day,
# and caching avoids waking up the database on every click
CACHE_SECONDS = 3600


# --------------------------------------------
# Data access
# --------------------------------------------

def run_query(sql, params=None):
    """Runs a SQL query with the read-only user and returns a DataFrame."""
    with psycopg.connect(**st.secrets["db"]) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            colunas = [c.name for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=colunas)


@st.cache_data(ttl=CACHE_SECONDS)
def load_fuels():
    return run_query("SELECT nome FROM dim_combustivel ORDER BY nome")["nome"].tolist()


@st.cache_data(ttl=CACHE_SECONDS)
def load_latest_date():
    return run_query("SELECT MAX(data) AS data FROM vw_precos")["data"].iloc[0]


@st.cache_data(ttl=CACHE_SECONDS)
def load_day(fuel, day, max_age):
    """Every station's price for one fuel on one day, skipping stale prices."""
    df = run_query(
        """
        SELECT posto, marca, morada, localidade, municipio, distrito,
               latitude, longitude, preco, data_atualizacao, dias_desde_atualizacao
        FROM vw_precos
        WHERE combustivel = %s AND data = %s AND dias_desde_atualizacao <= %s
        """,
        (fuel, day, max_age),
    )
    # NUMERIC arrives as Python Decimal; charts need regular floats
    df["preco"] = df["preco"].astype(float)
    return df


@st.cache_data(ttl=CACHE_SECONDS)
def load_series(fuel, max_age):
    """
    Daily price sums and counts per district and brand.
    Aggregated in SQL so only a few thousand rows travel, not millions.
    Sums and counts (instead of averages) let pandas re-average correctly after filtering.
    """
    df = run_query(
        """
        SELECT data, distrito, marca, SUM(preco) AS soma, COUNT(*) AS n
        FROM vw_precos
        WHERE combustivel = %s AND dias_desde_atualizacao <= %s
        GROUP BY data, distrito, marca
        """,
        (fuel, max_age),
    )
    df["soma"] = df["soma"].astype(float)
    return df


def apply_filters(df, distritos, marcas):
    """An empty selection means 'all'."""
    if distritos:
        df = df[df["distrito"].isin(distritos)]
    if marcas:
        df = df[df["marca"].isin(marcas)]
    return df


# --------------------------------------------
# Sidebar: filters
# --------------------------------------------

st.sidebar.title("Fuel Prices PT")

fuels = load_fuels()
default_fuel = fuels.index("Gasóleo simples") if "Gasóleo simples" in fuels else 0
fuel = st.sidebar.selectbox("Fuel", fuels, index=default_fuel)

max_age = st.sidebar.slider(
    "Ignore prices unchanged for more than (days)", min_value=1, max_value=365, value=30,
    help="Some stations stop updating a fuel. Prices older than this are treated as stale and left out.",
)

latest = load_latest_date()
day_all = load_day(fuel, latest, max_age)
series_all = load_series(fuel, max_age)

distritos = st.sidebar.multiselect("District", sorted(day_all["distrito"].dropna().unique()), placeholder="All districts")
marcas = st.sidebar.multiselect("Brand", sorted(day_all["marca"].dropna().unique()), placeholder="All brands")

day = apply_filters(day_all, distritos, marcas)
series = apply_filters(series_all, distritos, marcas)

st.sidebar.caption(
    "Data: [DGEG](https://precoscombustiveis.dgeg.gov.pt), collected daily by an automated pipeline. "
    "[Source code](https://github.com/amffpsa24-art/DE-Project---fuel-prices-pt)"
)


# --------------------------------------------
# Header and headline numbers
# --------------------------------------------

st.title(f"{fuel}: prices in Portugal")
st.caption(f"Latest snapshot: {latest:%d/%m/%Y}")

if day.empty:
    st.warning("No stations match these filters. Try removing a district or brand.")
    st.stop()

# National (or filtered) average per day = total of prices / number of prices
daily = series.groupby("data", as_index=False)[["soma", "n"]].sum()
daily["preco_medio"] = daily["soma"] / daily["n"]

media_hoje = day["preco"].mean()
delta_texto = None
if len(daily) >= 2:
    # Compare with the previous snapshot available, which is not always yesterday
    # (the history has gaps, e.g. before the daily schedule started)
    delta = daily["preco_medio"].iloc[-1] - daily["preco_medio"].iloc[-2]
    dia_anterior = daily["data"].iloc[-2]
    delta_texto = f"{delta:+.3f} € vs {dia_anterior:%d/%m}"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Average price", f"{media_hoje:.3f} €", delta=delta_texto, delta_color="inverse")
col2.metric("Cheapest", f"{day['preco'].min():.3f} €")
col3.metric("Most expensive", f"{day['preco'].max():.3f} €")
col4.metric("Stations", f"{len(day):,}")


# --------------------------------------------
# Tabs
# --------------------------------------------

tab_evol, tab_map, tab_cheap, tab_brand = st.tabs(["📈 Evolution", "🗺️ Map", "💶 Cheapest stations", "🏷️ Brands"])

with tab_evol:
    # Add the missing days as empty values, so the line breaks at gaps
    # instead of drawing a straight line through days with no data
    todos_dias = pd.date_range(daily["data"].min(), daily["data"].max(), freq="D").date
    daily = daily.set_index("data").reindex(todos_dias).rename_axis("data").reset_index()
    if distritos:
        # One line per selected district
        by_d = series.groupby(["data", "distrito"], as_index=False)[["soma", "n"]].sum()
        by_d["preco_medio"] = by_d["soma"] / by_d["n"]
        by_d = (by_d.set_index(["data", "distrito"])
                    .reindex(pd.MultiIndex.from_product([todos_dias, distritos], names=["data", "distrito"]))
                    .reset_index())
        fig = px.line(by_d, x="data", y="preco_medio", color="distrito", markers=True)
    else:
        fig = px.line(daily, x="data", y="preco_medio", markers=True)
    fig.update_layout(xaxis_title=None, yaxis_title="Average price (€)", yaxis_tickformat=".3f", legend_title=None)
    st.plotly_chart(fig, width="stretch")
    n_dias = int(daily["preco_medio"].notna().sum())
    st.caption(f"{n_dias} day(s) of history so far. A new day is added every evening; gaps are days with no snapshot.")

with tab_map:
    mapa = day.dropna(subset=["latitude", "longitude"])
    # Colour scale from the 2nd to the 98th percentile, so a few outliers don't wash out the colours
    low, high = mapa["preco"].quantile([0.02, 0.98])
    fig = px.scatter_map(
        mapa, lat="latitude", lon="longitude", color="preco",
        color_continuous_scale="RdYlGn_r", range_color=(low, high),
        hover_name="posto", hover_data={"marca": True, "municipio": True, "preco": ":.3f",
                                         "latitude": False, "longitude": False},
        zoom=5.6, center={"lat": 39.6, "lon": -8.0}, height=650, map_style="carto-positron",
    )
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0), coloraxis_colorbar_title="€")
    st.plotly_chart(fig, width="stretch")

with tab_cheap:
    municipios = sorted(day["municipio"].dropna().unique())
    municipio = st.selectbox("Municipality", ["All"] + municipios)
    tabela = day if municipio == "All" else day[day["municipio"] == municipio]
    st.dataframe(
        tabela.nsmallest(15, "preco")[["posto", "marca", "morada", "localidade", "municipio", "preco", "data_atualizacao"]],
        hide_index=True, width="stretch",
        column_config={
            "posto": "Station", "marca": "Brand", "morada": "Address", "localidade": "Town",
            "municipio": "Municipality",
            "preco": st.column_config.NumberColumn("Price (€)", format="%.3f"),
            "data_atualizacao": st.column_config.DatetimeColumn("Price updated", format="DD/MM/YYYY HH:mm"),
        },
    )

with tab_brand:
    MIN_POSTOS = 10
    marcas_df = (day.groupby("marca").agg(preco_medio=("preco", "mean"), postos=("preco", "size"))
                    .query("postos >= @MIN_POSTOS").sort_values("preco_medio").reset_index())
    if marcas_df.empty:
        st.info(f"No brand has at least {MIN_POSTOS} stations with these filters.")
    else:
        fig = px.bar(marcas_df, x="preco_medio", y="marca", orientation="h", hover_data={"postos": True},
                     text=marcas_df["preco_medio"].map("{:.3f}".format))
        fig.update_layout(xaxis_title="Average price (€)", yaxis_title=None, height=max(300, 28 * len(marcas_df)),
                          yaxis={"categoryorder": "total descending"})
        fig.update_xaxes(range=[marcas_df["preco_medio"].min() * 0.98, marcas_df["preco_medio"].max() * 1.01])
        st.plotly_chart(fig, width="stretch")
        st.caption(f"Brands with at least {MIN_POSTOS} stations in the current selection.")