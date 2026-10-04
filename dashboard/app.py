# ============================================
# DASHBOARD: Streamlit app reading the star schema through vw_precos
# ============================================
# Created: 04/10/2026
# Updated: 04/10/2026 (clean corporate design: price board, theme, "How it's built")
# Run locally (from the project root):  streamlit run dashboard/app.py
# Connection settings come from .streamlit/secrets.toml (git-ignored), using the read-only user.
# Colours and font come from .streamlit/config.toml.

import html
import math
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import psycopg
import streamlit as st

st.set_page_config(page_title="Fuel Prices PT", page_icon="⛽", layout="wide")

REPO_URL = "https://github.com/amffpsa24-art/DE-Project---fuel-prices-pt"
ARCHITECTURE_IMG = Path(__file__).resolve().parent.parent / "docs" / "images" / "architecture.png"

# Query results are cached for 1 hour: the data only changes once a day,
# and caching avoids waking up the database on every click
CACHE_SECONDS = 3600
MAP_HEIGHT = 520

# The everyday fuels shown on the price board at the top
BOARD_FUELS = ["Gasóleo simples", "Gasóleo especial", "Gasolina simples 95", "Gasolina especial 98"]


# --------------------------------------------
# Visual identity (same palette as .streamlit/config.toml)
# --------------------------------------------

INK, MUTED, RULE, GRID = "#1C2430", "#5B6676", "#DCE1E7", "#E9ECF0"
PETROL, CHEAP, DEAR = "#0E5A73", "#1F7A5A", "#B5462B"

# Price colour scale for the map: green (cheap) -> sand (average) -> rust (expensive)
PRICE_SCALE = [[0.0, CHEAP], [0.5, "#E6DFCB"], [1.0, DEAR]]

# Plotly template, so every chart uses the same font, colours and quiet gridlines
pio.templates["fuel"] = go.layout.Template(layout=dict(
    font=dict(family="IBM Plex Sans, sans-serif", color=INK, size=13),
    colorway=[PETROL, "#C27C2C", "#6A5E9E", "#3E8E6E", DEAR, "#5F7FA6"],
    paper_bgcolor="white", plot_bgcolor="white",
    xaxis=dict(gridcolor=GRID, linecolor=RULE, ticks="outside", tickcolor=RULE),
    yaxis=dict(gridcolor=GRID, linecolor=RULE, zeroline=False),
    hoverlabel=dict(font=dict(family="IBM Plex Sans, sans-serif")),
    margin=dict(l=60, r=20, t=30, b=40),
))
pio.templates.default = "fuel"

st.markdown(f"""
<style>
.block-container {{ padding-top: 3.6rem; padding-bottom: 2rem; }}
.hero h1 {{ font-size: 2.1rem; font-weight: 600; letter-spacing: -0.015em; line-height: 1.15; margin: 0 0 .4rem; padding: 0; }}
.hero p  {{ color: {MUTED}; font-size: 1rem; line-height: 1.5; max-width: 100ch; margin: 0 0 .3rem; }}
.board {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
          border: 1px solid {RULE}; border-radius: 6px; margin: 1.1rem 0 .35rem; overflow: hidden; }}
.board .cell {{ padding: .8rem 1.1rem .75rem; border-right: 1px solid {RULE}; border-bottom: 1px solid {RULE}; margin: 0 -1px -1px 0; }}
.board .cell.sel {{ background: #EDF4F6; box-shadow: inset 3px 0 0 {PETROL}; }}
.board .fuel  {{ color: {MUTED}; font-size: .85rem; }}
.board .price {{ font-size: 1.85rem; font-weight: 500; line-height: 1.25; font-variant-numeric: tabular-nums; color: {INK}; }}
.board .unit  {{ font-size: .95rem; color: {MUTED}; margin-left: .2rem; }}
.board .chg   {{ font-size: .82rem; font-variant-numeric: tabular-nums; }}
.chg.up {{ color: {DEAR}; }} .chg.down {{ color: {CHEAP}; }} .chg.flat {{ color: {MUTED}; }}
.board-note {{ color: {MUTED}; font-size: .82rem; margin-bottom: .9rem; }}
[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
</style>
""", unsafe_allow_html=True)


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


# --------------------------------------------
# Helpers for charts
# --------------------------------------------

def average(df, por):
    """Average price per group, from sums and counts."""
    g = df.groupby(por, as_index=False)[["soma", "n"]].sum()
    g["preco_medio"] = g["soma"] / g["n"]
    return g


def line_chart(df, y, dias, cor=None, ytitle="Average price (€)"):
    """
    Line chart over time, honest about missing days:
    - SOLID line between consecutive days with data
    - thin DOTTED line where days are missing (it only connects the snapshots on each side)
    One line per value of `cor` (e.g. per fuel), or a single line if cor is None.
    """
    fig = go.Figure()
    paleta = pio.templates["fuel"].layout.colorway
    grupos = [(None, df)] if cor is None else list(df.groupby(cor))
    for i, (nome, d) in enumerate(grupos):
        d = d.dropna(subset=[y]).sort_values("data")
        cor_linha = paleta[i % len(paleta)]
        # 1. Dotted line through every snapshot (visible only where the solid line is missing)
        fig.add_scatter(x=d["data"], y=d[y], mode="lines", hoverinfo="skip", showlegend=False,
                        line=dict(color=cor_linha, width=1.5, dash="dot"))
        # 2. Solid line on a full calendar: missing days are empty, so the line breaks there
        cheio = d.set_index("data")[y].reindex(dias)
        fig.add_scatter(x=cheio.index, y=cheio.values, name=nome or "", showlegend=cor is not None,
                        mode="lines" if len(d) > 1 else "markers",   # a single day can only be a dot
                        line=dict(color=cor_linha, width=2.5), connectgaps=False,
                        hovertemplate="%{x|%d/%m/%Y}<br>%{y:.3f} €<extra>" + (nome or "") + "</extra>")
    fig.update_layout(xaxis_title=None, yaxis_title=ytitle, yaxis_tickformat=".3f", legend_title=None,
                      hovermode="x unified", legend=dict(orientation="h", y=1.08, x=0))
    return fig


def map_view(lat, lon, altura=MAP_HEIGHT, largura=800):
    """
    Centre and zoom that fit the stations on screen: all of Portugal by default,
    closer in when filtering a district or municipality.
    Maps use the Mercator projection, so latitudes are converted before measuring the extent.
    """
    def merc(x):
        return math.log(math.tan(math.pi / 4 + math.radians(x) / 2))
    # Ignore the extreme 0.5% on each side, so one odd coordinate can't zoom the map out
    lat0, lat1 = lat.quantile([0.005, 0.995])
    lon0, lon1 = lon.quantile([0.005, 0.995])
    dy = max(merc(lat1) - merc(lat0), 1e-4)
    dx = max(lon1 - lon0, 1e-4)
    # At zoom z the whole world is 512 * 2^z pixels wide; pick the zoom where the stations fill the map
    zoom = min(math.log2(altura / 512 * 2 * math.pi / dy), math.log2(largura / 512 * 360 / dx)) - 0.3
    centro_lat = math.degrees(2 * math.atan(math.exp((merc(lat0) + merc(lat1)) / 2)) - math.pi / 2)
    return {"lat": centro_lat, "lon": (lon0 + lon1) / 2}, max(3.0, min(zoom, 12.0))


def chart(fig, container=st):
    """theme=None keeps our own Plotly template instead of Streamlit's default chart styling."""
    # Colours set on the figure itself too: the browser doesn't always apply the template's backgrounds
    fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    container.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})


# --------------------------------------------
# Sidebar: filters
# --------------------------------------------

st.sidebar.header("Filters")

fuels = load_fuels()
dates = load_dates()
default_fuel = fuels.index("Gasóleo simples") if "Gasóleo simples" in fuels else 0
fuel = st.sidebar.selectbox("Fuel", fuels, index=default_fuel)

periodo = st.sidebar.date_input(
    "Period", value=(dates[0], dates[-1]), min_value=dates[0], max_value=dates[-1], format="DD/MM/YYYY",
    help="Charts use the whole period. The map, tables and price board use the last day in it.",
)
# While the user is picking, the widget briefly returns only the start date
inicio, fim = (periodo if len(periodo) == 2 else (periodo[0], dates[-1]))

# The "current" snapshot = the latest day with data inside the chosen period
dias_no_periodo = [d for d in dates if inicio <= d <= fim]
if not dias_no_periodo:
    st.warning("There are no snapshots in this period. Choose a wider period on the left.")
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
pesquisa = st.sidebar.text_input("Station name", placeholder="Search, e.g. Intermarché").strip()

with st.sidebar.expander("Data quality"):
    max_age = st.slider(
        "Leave out prices unchanged for more than (days)", min_value=1, max_value=365, value=30,
        help="Some stations stop updating a fuel. Prices older than this are treated as stale and left out.",
    )

# All choices in one dictionary (tuples, so the cache can use them as keys)
f = {"max_age": max_age, "distritos": tuple(distritos), "municipios": tuple(municipios),
     "tipos": tuple(tipos), "marcas": tuple(marcas), "pesquisa": pesquisa}
filtrado = any([distritos, municipios, tipos, marcas, pesquisa])


# --------------------------------------------
# Hero: what this is, and today's prices
# --------------------------------------------

st.markdown(f"""
<div class="hero">
  <h1>Fuel prices in Portugal, updated every evening</h1>
  <p>Daily prices from {load_station_count(snapshot):,} petrol stations, collected from the official data of DGEG,
  Portugal's Directorate-General for Energy and Geology. Choose a fuel and a region on the left.</p>
</div>
""", unsafe_allow_html=True)

# Price board: average price of the everyday fuels, like the price sign at a station
quadro = [x for x in BOARD_FUELS if x in fuels]
if fuel not in quadro:
    quadro.append(fuel)
board = average(load_series(tuple(quadro), snapshot_anterior or snapshot, snapshot, f), ["data", "combustivel"])

celulas = []
for nome in quadro:
    linhas = board[board["combustivel"] == nome].set_index("data")["preco_medio"]
    if snapshot not in linhas.index:
        continue
    agora = linhas[snapshot]
    if snapshot_anterior is not None and snapshot_anterior in linhas.index:
        dif = agora - linhas[snapshot_anterior]
        classe = "up" if dif > 0.0005 else "down" if dif < -0.0005 else "flat"
        seta = {"up": "▲", "down": "▼", "flat": ""}[classe]
        texto = f"{seta} {abs(dif):.3f} since {snapshot_anterior:%d/%m}" if classe != "flat" else f"unchanged since {snapshot_anterior:%d/%m}"
    else:
        classe, texto = "flat", "first day in this period"
    unidade = "€/kg" if "€/kg" in nome else "€/m³" if "€/m3" in nome else "€/L"
    celulas.append(
        f'<div class="cell{" sel" if nome == fuel else ""}"><div class="fuel">{html.escape(nome)}</div>'
        f'<div class="price">{agora:.3f}<span class="unit">{unidade}</span></div>'
        f'<div class="chg {classe}">{texto}</div></div>'
    )
st.markdown(f'<div class="board">{"".join(celulas)}</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="board-note">Average price on {snapshot:%d/%m/%Y}'
    f'{" for the stations matching your filters" if filtrado else " across Portugal"}. '
    f'The highlighted fuel is the one shown below.</div>',
    unsafe_allow_html=True,
)

day = load_day(fuel, snapshot, f)
if day.empty:
    st.warning("No stations match these filters. Remove a filter on the left to see results.")
    st.stop()

series_main = load_series((fuel,), inicio, fim, f)
daily = average(series_main, "data")



# --------------------------------------------
# Tabs
# --------------------------------------------

tab_map, tab_evol, tab_list, tab_changes, tab_station, tab_brand, tab_how = st.tabs(
    ["Map", "Evolution", "Stations", "Price changes", "Station history", "Brands", "How it's built"]
)
todos_dias = pd.date_range(inicio, fim, freq="D").date

with tab_map:
    col_mapa, col_lista = st.columns([3, 2], gap="large")
    mapa = day.dropna(subset=["latitude", "longitude"])
    # Colour scale from the 2nd to the 98th percentile, so a few outliers don't wash out the colours
    low, high = mapa["preco"].quantile([0.02, 0.98])
    centro, zoom = map_view(mapa["latitude"], mapa["longitude"])
    fig = px.scatter_map(
        mapa, lat="latitude", lon="longitude", color="preco",
        color_continuous_scale=PRICE_SCALE, range_color=(low, high),
        hover_name="posto", hover_data={"marca": True, "municipio": True, "preco": ":.3f",
                                         "latitude": False, "longitude": False},
        labels={"marca": "Brand", "municipio": "Municipality", "preco": "Price (€)"},
        zoom=zoom, center=centro, height=MAP_HEIGHT, map_style="carto-positron",
    )
    fig.update_traces(marker=dict(size=8, opacity=0.9))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                      coloraxis_colorbar=dict(title="€", thickness=12, len=0.6, tickformat=".2f"))
    chart(fig, col_mapa)

    # Next to the map: key numbers for the selected fuel, then the 10 cheapest stations
    m1, m2, m3 = col_lista.columns(3)
    m1.metric("Lowest", f"{day['preco'].min():.3f} €")
    m2.metric("Highest", f"{day['preco'].max():.3f} €")
    m3.metric("Stations", f"{len(day):,}")
    col_lista.markdown(f"**Cheapest stations for {html.escape(fuel)}**")
    col_lista.dataframe(
        day.nsmallest(10, "preco")[["posto", "municipio", "preco"]], hide_index=True, width="stretch",
        column_config={"posto": st.column_config.TextColumn("Station", width="medium"),
                       "municipio": st.column_config.TextColumn("Municipality", width="small"),
                       "preco": st.column_config.NumberColumn("Price (€)", format="%.3f", width="small")},
    )
    col_lista.caption("Green dots are cheaper, red dots more expensive. The full list is in the Stations tab.")

with tab_evol:
    outros = st.multiselect("Compare with other fuels", [x for x in fuels if x != fuel], placeholder="Add fuels")
    if outros:
        # One line per fuel (districts are combined)
        serie = average(load_series(tuple([fuel] + outros), inicio, fim, f), ["data", "combustivel"])
        fig = line_chart(serie, "preco_medio", todos_dias, cor="combustivel")
    elif distritos:
        # One line per selected district
        fig = line_chart(average(series_main, ["data", "distrito"]), "preco_medio", todos_dias, cor="distrito")
    else:
        fig = line_chart(daily, "preco_medio", todos_dias)
    chart(fig)
    st.caption(f"{len(daily)} day(s) of data in this period. A new day is added every evening; "
               "dotted segments cross days with no data.")

with tab_list:
    colunas_postos = {"posto": "Station", "marca": "Brand", "tipo_posto": "Type", "morada": "Address",
                      "localidade": "Town", "municipio": "Municipality", "distrito": "District"}
    tabela = day.sort_values("preco")[list(colunas_postos) + ["preco", "data_atualizacao"]]
    st.dataframe(
        tabela, hide_index=True, width="stretch", height=480,
        column_config={**colunas_postos,
                       "preco": st.column_config.NumberColumn("Price (€)", format="%.3f"),
                       "data_atualizacao": st.column_config.DatetimeColumn("Price updated", format="DD/MM/YYYY HH:mm")},
    )
    # Export for people, so: UTF-8 with BOM ("utf-8-sig"), which makes Excel show accents correctly.
    # (The pipeline's raw CSVs stay plain UTF-8: they are for machines.)
    st.download_button(
        "Download this list (CSV)", tabela.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"fuel_prices_{fuel}_{snapshot}.csv".replace(" ", "_"), mime="text/csv",
    )
    st.caption(f"{len(tabela):,} stations, cheapest first.")

with tab_changes:
    if snapshot_anterior is None:
        st.info("Price changes need at least two days of data. Choose a longer period on the left.")
    else:
        antes = load_day(fuel, snapshot_anterior, f)[["posto_id", "preco"]]
        mud = day.merge(antes, on="posto_id", suffixes=("", "_antes"))   # stations present on both days
        mud["variacao"] = mud["preco"] - mud["preco_antes"]
        subiu, desceu = (mud["variacao"] > 0).sum(), (mud["variacao"] < 0).sum()
        st.write(f"From {snapshot_anterior:%d/%m} to {snapshot:%d/%m}, **{subiu:,}** stations raised the price, "
                 f"**{desceu:,}** lowered it and **{len(mud) - subiu - desceu:,}** kept it.")
        cfg = {"posto": "Station", "marca": "Brand", "municipio": "Municipality",
               "preco_antes": st.column_config.NumberColumn("Before (€)", format="%.3f"),
               "preco": st.column_config.NumberColumn("Now (€)", format="%.3f"),
               "variacao": st.column_config.NumberColumn("Change (€)", format="%+.3f")}
        mostrar = ["posto", "marca", "municipio", "preco_antes", "preco", "variacao"]
        a, b = st.columns(2, gap="large")
        a.subheader("Largest increases")
        a.dataframe(mud[mud["variacao"] > 0].nlargest(10, "variacao")[mostrar], hide_index=True, column_config=cfg)
        b.subheader("Largest decreases")
        b.dataframe(mud[mud["variacao"] < 0].nsmallest(10, "variacao")[mostrar], hide_index=True, column_config=cfg)

with tab_station:
    postos = day.sort_values(["posto", "municipio"])
    # Readable label for each station id, e.g. "INTERMARCHÉ FAMÕES, Odivelas (INTERMARCHÉ)"
    rotulos = {r.posto_id: f"{r.posto}, {r.municipio} ({r.marca})" for r in postos.itertuples()}
    escolha = st.selectbox(
        "Station", list(rotulos), format_func=rotulos.get,
        help="Stations matching the filters on the left. Type a name in 'Station name' to narrow the list.",
    )
    hist = load_station_history(int(escolha), inicio, fim)
    chart(line_chart(hist, "preco", todos_dias, cor="combustivel", ytitle="Price (€)"))

    st.subheader("Station details over time")
    st.dataframe(
        load_station_versions(int(escolha)), hide_index=True, width="stretch",
        column_config={"nome": "Name", "marca": "Brand", "tipo_posto": "Type", "morada": "Address",
                       "municipio": "Municipality", "valido_de": "Valid from", "valido_ate": "Valid until",
                       "atual": "Current"},
    )
    st.caption("A new row appears when DGEG reports a change to the station, such as a new brand, "
               "so older prices keep the details that were true at the time.")

with tab_brand:
    MIN_POSTOS = 10
    marcas_df = (day.groupby("marca").agg(preco_medio=("preco", "mean"), postos=("preco", "size"))
                    .query("postos >= @MIN_POSTOS").sort_values("preco_medio").reset_index())
    if marcas_df.empty:
        st.info(f"No brand has {MIN_POSTOS} or more stations with these filters. Remove a filter to compare brands.")
    else:
        fig = px.bar(marcas_df, x="preco_medio", y="marca", orientation="h", hover_data={"postos": True},
                     text=marcas_df["preco_medio"].map("{:.3f}".format),
                     labels={"preco_medio": "Average price (€)", "marca": "Brand", "postos": "Stations"})
        fig.update_traces(marker_color=PETROL, textposition="outside", cliponaxis=False)
        fig.update_layout(xaxis_title="Average price (€)", yaxis_title=None, height=max(300, 30 * len(marcas_df)),
                          yaxis={"categoryorder": "total descending"})
        fig.update_xaxes(range=[marcas_df["preco_medio"].min() * 0.98, marcas_df["preco_medio"].max() * 1.015])
        chart(fig)
        st.caption(f"Brands with {MIN_POSTOS} or more stations in the current selection.")

with tab_how:
    st.subheader("How this dashboard is built")
    st.markdown(
        "DGEG publishes each station's current price but keeps no history: once a price changes, "
        "the old one is gone. This project collects a snapshot every day and stores it, "
        "building the history that makes the charts here possible."
    )
    if ARCHITECTURE_IMG.exists():
        st.image(str(ARCHITECTURE_IMG), width="stretch")
    st.markdown(
        "1. **Extract.** Every evening, a GitHub Actions job requests all prices from DGEG's API, about 13,600 records.\n"
        "2. **Transform.** Python and pandas clean the data, for example turning \"1,164 €\" into 1.164.\n"
        "3. **Load.** The day's rows are kept as a raw CSV, then loaded into a star schema in PostgreSQL (Neon), "
        "with station history tracked as a slowly changing dimension.\n"
        "4. **Serve.** This dashboard reads the warehouse through a view, using a read-only database user.\n\n"
        f"Code, documentation and design decisions: [GitHub repository]({REPO_URL})."
    )

st.caption(f"Source: [DGEG, Preços dos Combustíveis](https://precoscombustiveis.dgeg.gov.pt). "
           f"Latest data: {dates[-1]:%d/%m/%Y}.")