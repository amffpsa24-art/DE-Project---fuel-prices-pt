# ============================================
# DASHBOARD: Streamlit app reading the star schema through vw_precos
# ============================================
# Created: 04/10/2026
# Updated: 04/10/2026 (more filters, station history, price changes, fuel comparison, CSV export)
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

# Columns shown in the station tables, with readable names
COLUNAS_POSTOS = {
    "posto": "Station", "marca": "Brand", "tipo_posto": "Type", "morada": "Address",
    "localidade": "Town", "municipio": "Municipality", "distrito": "District",
}


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


def to_float(df, *colunas):
    """NUMERIC arrives as Python Decimal; charts and maths need regular floats."""
    for c in colunas:
        df[c] = df[c].astype(float)
    return df


def build_filters(f):
    """
    Turns the sidebar choices into SQL conditions + parameters.
    Filtering happens in the database, so only the rows needed travel to the app.
    An empty choice means 'no filter'.
    """
    clausulas, params = ["dias_desde_atualizacao <= %s"], [f["max_age"]]
    for coluna, valores in [("distrito", f["distritos"]), ("municipio", f["municipios"]),
                            ("tipo_posto", f["tipos"]), ("marca", f["marcas"])]:
        if valores:
            clausulas.append(f"{coluna} = ANY(%s)")   # = ANY(list): matches any value in the list
            params.append(list(valores))
    if f["pesquisa"]:
        clausulas.append("posto ILIKE %s")          # ILIKE = case-insensitive text match
        params.append(f"%{f['pesquisa']}%")
    return " AND ".join(clausulas), params


@st.cache_data(ttl=CACHE_SECONDS)
def load_fuels():
    return run_query("SELECT nome FROM dim_combustivel ORDER BY nome")["nome"].tolist()


@st.cache_data(ttl=CACHE_SECONDS)
def load_dates():
    """Every day that has a snapshot, oldest first."""
    return run_query("SELECT data FROM dim_data ORDER BY data")["data"].tolist()


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


def fill_gaps(df, dias, chave=None):
    """Adds missing days as empty rows, so chart lines break at gaps instead of bridging them."""
    if chave is None:
        return df.set_index("data").reindex(dias).rename_axis("data").reset_index()
    indice = pd.MultiIndex.from_product([dias, df[chave].unique()], names=["data", chave])
    return df.set_index(["data", chave]).reindex(indice).reset_index()


def average(df, por):
    """Average price per group, from sums and counts."""
    g = df.groupby(por, as_index=False)[["soma", "n"]].sum()
    g["preco_medio"] = g["soma"] / g["n"]
    return g


# --------------------------------------------
# Sidebar: filters
# --------------------------------------------

st.sidebar.title("⛽ Fuel Prices PT")

fuels = load_fuels()
dates = load_dates()
default_fuel = fuels.index("Gasóleo simples") if "Gasóleo simples" in fuels else 0
fuel = st.sidebar.selectbox("Fuel", fuels, index=default_fuel)

periodo = st.sidebar.date_input(
    "Period", value=(dates[0], dates[-1]), min_value=dates[0], max_value=dates[-1], format="DD/MM/YYYY",
    help="The charts use the whole period. Map, tables and headline numbers use the last snapshot in it.",
)
# While the user is picking, the widget briefly returns only the start date
inicio, fim = (periodo if len(periodo) == 2 else (periodo[0], dates[-1]))

# The "current" snapshot = the latest day with data inside the chosen period
dias_no_periodo = [d for d in dates if inicio <= d <= fim]
if not dias_no_periodo:
    st.warning("There are no snapshots in this period.")
    st.stop()
snapshot = dias_no_periodo[-1]
snapshot_anterior = dias_no_periodo[-2] if len(dias_no_periodo) >= 2 else None

opcoes = load_options(fuel, snapshot)
distritos = st.sidebar.multiselect("District", sorted(opcoes["distrito"].dropna().unique()), placeholder="All districts")
# Municipalities depend on the chosen districts
mun_opcoes = opcoes if not distritos else opcoes[opcoes["distrito"].isin(distritos)]
municipios = st.sidebar.multiselect("Municipality", sorted(mun_opcoes["municipio"].dropna().unique()), placeholder="All municipalities")
tipos = st.sidebar.multiselect("Station type", sorted(opcoes["tipo_posto"].dropna().unique()), placeholder="All types")
marcas = st.sidebar.multiselect("Brand", sorted(opcoes["marca"].dropna().unique()), placeholder="All brands")
pesquisa = st.sidebar.text_input("Search station name", placeholder="e.g. Intermarché").strip()

with st.sidebar.expander("Data quality"):
    max_age = st.slider(
        "Ignore prices unchanged for more than (days)", min_value=1, max_value=365, value=30,
        help="Some stations stop updating a fuel. Prices older than this are treated as stale and left out.",
    )

# All choices in one dictionary (tuples, so the cache can use them as keys)
f = {"max_age": max_age, "distritos": tuple(distritos), "municipios": tuple(municipios),
     "tipos": tuple(tipos), "marcas": tuple(marcas), "pesquisa": pesquisa}

st.sidebar.caption(
    "Data: [DGEG](https://precoscombustiveis.dgeg.gov.pt), collected daily by an automated pipeline. "
    "[Source code](https://github.com/amffpsa24-art/DE-Project---fuel-prices-pt)"
)


# --------------------------------------------
# Header and headline numbers
# --------------------------------------------

st.title(f"{fuel}: prices in Portugal")
st.caption(f"Snapshot: {snapshot:%d/%m/%Y} · period {inicio:%d/%m/%Y} – {fim:%d/%m/%Y}")

day = load_day(fuel, snapshot, f)
if day.empty:
    st.warning("No stations match these filters. Try removing some of them.")
    st.stop()

series_main = load_series((fuel,), inicio, fim, f)
daily = average(series_main, "data")

delta_texto = None
if len(daily) >= 2:
    # Compare with the previous snapshot available, which is not always yesterday
    delta = daily["preco_medio"].iloc[-1] - daily["preco_medio"].iloc[-2]
    delta_texto = f"{delta:+.3f} € vs {daily['data'].iloc[-2]:%d/%m}"

col1, col2, col3, col4 = st.columns(4)
col1.metric("Average price", f"{day['preco'].mean():.3f} €", delta=delta_texto, delta_color="inverse")
col2.metric("Cheapest", f"{day['preco'].min():.3f} €")
col3.metric("Most expensive", f"{day['preco'].max():.3f} €")
col4.metric("Stations", f"{len(day):,}")


# --------------------------------------------
# Tabs
# --------------------------------------------

tab_evol, tab_map, tab_list, tab_changes, tab_station, tab_brand = st.tabs(
    ["📈 Evolution", "🗺️ Map", "💶 Stations", "↕️ Price changes", "📍 Station history", "🏷️ Brands"]
)
todos_dias = pd.date_range(inicio, fim, freq="D").date

with tab_evol:
    outros = st.multiselect("Compare with other fuels", [x for x in fuels if x != fuel], placeholder="Add fuels")
    if outros:
        # One line per fuel (districts are combined)
        serie = average(load_series(tuple([fuel] + outros), inicio, fim, f), ["data", "combustivel"])
        fig = px.line(fill_gaps(serie, todos_dias, "combustivel"), x="data", y="preco_medio", color="combustivel", markers=True)
    elif distritos:
        # One line per selected district
        serie = average(series_main, ["data", "distrito"])
        fig = px.line(fill_gaps(serie, todos_dias, "distrito"), x="data", y="preco_medio", color="distrito", markers=True)
    else:
        fig = px.line(fill_gaps(daily, todos_dias), x="data", y="preco_medio", markers=True)
    fig.update_layout(xaxis_title=None, yaxis_title="Average price (€)", yaxis_tickformat=".3f", legend_title=None)
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{len(daily)} snapshot(s) in this period. A new one is added every evening; gaps are days with no snapshot.")

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

with tab_list:
    tabela = day.sort_values("preco")[list(COLUNAS_POSTOS) + ["preco", "data_atualizacao"]]
    st.dataframe(
        tabela, hide_index=True, width="stretch", height=500,
        column_config={**COLUNAS_POSTOS,
                       "preco": st.column_config.NumberColumn("Price (€)", format="%.3f"),
                       "data_atualizacao": st.column_config.DatetimeColumn("Price updated", format="DD/MM/YYYY HH:mm")},
    )
    # Export for people, so: UTF-8 with BOM ("utf-8-sig"), which makes Excel show accents correctly.
    # (The pipeline's raw CSVs stay plain UTF-8: they are for machines.)
    st.download_button(
        "⬇️ Download as CSV", tabela.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"fuel_prices_{fuel}_{snapshot}.csv".replace(" ", "_"), mime="text/csv",
    )
    st.caption(f"{len(tabela):,} stations, cheapest first.")

with tab_changes:
    if snapshot_anterior is None:
        st.info("Price changes need at least two snapshots in the selected period.")
    else:
        antes = load_day(fuel, snapshot_anterior, f)[["posto_id", "preco"]]
        mud = day.merge(antes, on="posto_id", suffixes=("", "_antes"))   # stations present on both days
        mud["variacao"] = mud["preco"] - mud["preco_antes"]
        subiu, desceu = (mud["variacao"] > 0).sum(), (mud["variacao"] < 0).sum()
        st.write(f"Between **{snapshot_anterior:%d/%m}** and **{snapshot:%d/%m}**: "
                 f"**{subiu:,}** stations raised the price, **{desceu:,}** cut it, "
                 f"**{len(mud) - subiu - desceu:,}** kept it.")
        cfg = {**COLUNAS_POSTOS, "preco_antes": st.column_config.NumberColumn("Before (€)", format="%.3f"),
               "preco": st.column_config.NumberColumn("Now (€)", format="%.3f"),
               "variacao": st.column_config.NumberColumn("Change (€)", format="%+.3f")}
        mostrar = ["posto", "marca", "municipio", "preco_antes", "preco", "variacao"]
        c1, c2 = st.columns(2)
        c1.subheader("Biggest increases")
        c1.dataframe(mud[mud["variacao"] > 0].nlargest(10, "variacao")[mostrar], hide_index=True, column_config=cfg)
        c2.subheader("Biggest decreases")
        c2.dataframe(mud[mud["variacao"] < 0].nsmallest(10, "variacao")[mostrar], hide_index=True, column_config=cfg)

with tab_station:
    postos = day.sort_values(["posto", "municipio"])
    # Readable label for each station id, e.g. "INTERMARCHÉ FAMÕES · Odivelas (INTERMARCHÉ)"
    rotulos = {r.posto_id: f"{r.posto} · {r.municipio} ({r.marca})" for r in postos.itertuples()}
    escolha = st.selectbox(
        "Station", list(rotulos), format_func=rotulos.get,
        help="Stations matching the sidebar filters. Use 'Search station name' to narrow the list.",
    )
    hist = load_station_history(int(escolha), inicio, fim)
    fig = px.line(fill_gaps(hist[["data", "combustivel", "preco"]], todos_dias, "combustivel"),
                  x="data", y="preco", color="combustivel", markers=True)
    fig.update_layout(xaxis_title=None, yaxis_title="Price (€)", yaxis_tickformat=".3f", legend_title=None)
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Station details over time**")
    st.dataframe(
        load_station_versions(int(escolha)), hide_index=True, width="stretch",
        column_config={"nome": "Name", "marca": "Brand", "tipo_posto": "Type", "morada": "Address",
                       "municipio": "Municipality", "valido_de": "Valid from", "valido_ate": "Valid until",
                       "atual": "Current"},
    )
    st.caption("Each row is a version of the station's details. A new row appears when DGEG reports a change, "
               "such as a new brand (slowly changing dimension, Type 2).")

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