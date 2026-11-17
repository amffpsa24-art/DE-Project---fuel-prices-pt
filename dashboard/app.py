# DASHBOARD: Streamlit app reading the star schema through vw_precos
# Run locally (from the project root):  streamlit run dashboard/app.py
#
# This file is the page layout: sidebar, price board and tabs.
# Database reads are in queries.py; colours, theme and chart helpers in charts.py.

import html
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from charts import CHEAP, DEAR, INK, MAP_HEIGHT, MUTED, PETROL, PRICE_SCALE, RULE, average, chart, line_chart, map_view
from queries import (
    load_dates,
    load_day,
    load_fuels,
    load_options,
    load_series,
    load_station_count,
    load_station_history,
    load_station_versions,
)

st.set_page_config(page_title="Fuel Prices PT", page_icon="⛽", layout="wide")

REPO_URL = "https://github.com/amffpsa24-art/DE-Project---fuel-prices-pt"
ARCHITECTURE_IMG = Path(__file__).resolve().parent.parent / "docs" / "images" / "architecture.png"

# The everyday fuels shown on the price board at the top
BOARD_FUELS = ["Gasóleo simples", "Gasóleo especial", "Gasolina simples 95", "Gasolina especial 98"]

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
# Sidebar: filters
# --------------------------------------------

st.sidebar.header("Filters")

fuels = load_fuels()
dates = load_dates()
default_fuel = fuels.index("Gasóleo simples") if "Gasóleo simples" in fuels else 0
fuel = st.sidebar.selectbox("Fuel", fuels, index=default_fuel)

period = st.sidebar.date_input(
    "Period", value=(dates[0], dates[-1]), min_value=dates[0], max_value=dates[-1], format="DD/MM/YYYY",
    help="Charts use the whole period. The map, tables and price board use the last day in it.",
)
# While the user is picking, the widget briefly returns only the start date
start, end = (period if len(period) == 2 else (period[0], dates[-1]))

# The "current" snapshot = the latest day with data inside the chosen period
days_in_period = [d for d in dates if start <= d <= end]
if not days_in_period:
    st.warning("There are no snapshots in this period. Choose a wider period on the left.")
    st.stop()
snapshot = days_in_period[-1]
previous_snapshot = days_in_period[-2] if len(days_in_period) >= 2 else None

options = load_options(fuel, snapshot)
districts = st.sidebar.multiselect("District", sorted(options["distrito"].dropna().unique()), placeholder="All districts")
# Municipalities depend on the chosen districts
municipality_options = options if not districts else options[options["distrito"].isin(districts)]
municipalities = st.sidebar.multiselect("Municipality", sorted(municipality_options["municipio"].dropna().unique()),
                                        placeholder="All municipalities")
types = st.sidebar.multiselect("Station type", sorted(options["tipo_posto"].dropna().unique()), placeholder="All types")
brands = st.sidebar.multiselect("Brand", sorted(options["marca"].dropna().unique()), placeholder="All brands")
search = st.sidebar.text_input("Station name", placeholder="Search, e.g. Intermarché").strip()

with st.sidebar.expander("Data quality"):
    max_age = st.slider(
        "Leave out prices unchanged for more than (days)", min_value=1, max_value=365, value=30,
        help="Some stations stop updating a fuel. Prices older than this are treated as stale and left out.",
    )

# All choices in one dictionary (tuples, so the cache can use them as keys)
f = {"max_age": max_age, "districts": tuple(districts), "municipalities": tuple(municipalities),
     "types": tuple(types), "brands": tuple(brands), "search": search}
is_filtered = any([districts, municipalities, types, brands, search])


# --------------------------------------------
# Hero: what this is, and today's prices
# --------------------------------------------

st.markdown(f"""
<div class="hero">
  <h1>Fuel prices in Portugal, updated every day</h1>
  <p>Daily prices from {load_station_count(snapshot):,} petrol stations, collected from the official data of DGEG,
  Portugal's Directorate-General for Energy and Geology. Choose a fuel and a region on the left.</p>
</div>
""", unsafe_allow_html=True)

# Price board: average price of the everyday fuels, like the price sign at a station
board_fuels = [x for x in BOARD_FUELS if x in fuels]
if fuel not in board_fuels:
    board_fuels.append(fuel)
board = average(load_series(tuple(board_fuels), previous_snapshot or snapshot, snapshot, f), ["data", "combustivel"])

cells = []
for name in board_fuels:
    prices = board[board["combustivel"] == name].set_index("data")["preco_medio"]
    if snapshot not in prices.index:
        continue
    now = prices[snapshot]
    if previous_snapshot is not None and previous_snapshot in prices.index:
        diff = now - prices[previous_snapshot]
        trend = "up" if diff > 0.0005 else "down" if diff < -0.0005 else "flat"
        arrow = {"up": "▲", "down": "▼", "flat": ""}[trend]
        text = (f"{arrow} {abs(diff):.3f} since {previous_snapshot:%d/%m}" if trend != "flat"
                else f"unchanged since {previous_snapshot:%d/%m}")
    else:
        trend, text = "flat", "first day in this period"
    unit = "€/kg" if "€/kg" in name else "€/m³" if "€/m3" in name else "€/L"
    cells.append(
        f'<div class="cell{" sel" if name == fuel else ""}"><div class="fuel">{html.escape(name)}</div>'
        f'<div class="price">{now:.3f}<span class="unit">{unit}</span></div>'
        f'<div class="chg {trend}">{text}</div></div>'
    )
st.markdown(f'<div class="board">{"".join(cells)}</div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="board-note">Average price on {snapshot:%d/%m/%Y}'
    f'{" for the stations matching your filters" if is_filtered else " across Portugal"}. '
    f'The highlighted fuel is the one shown below.</div>',
    unsafe_allow_html=True,
)

day = load_day(fuel, snapshot, f)
if day.empty:
    st.warning("No stations match these filters. Remove a filter on the left to see results.")
    st.stop()

series_main = load_series((fuel,), start, end, f)
daily = average(series_main, "data")


# --------------------------------------------
# Tabs
# --------------------------------------------

tab_map, tab_evol, tab_list, tab_changes, tab_station, tab_brand, tab_how = st.tabs(
    ["Map", "Evolution", "Stations", "Price changes", "Station history", "Brands", "How it's built"]
)
all_days = pd.date_range(start, end, freq="D").date

with tab_map:
    col_map, col_list = st.columns([3, 2], gap="large")
    on_map = day.dropna(subset=["latitude", "longitude"])
    # Colour scale from the 2nd to the 98th percentile, so a few outliers don't wash out the colours
    low, high = on_map["preco"].quantile([0.02, 0.98])
    center, zoom = map_view(on_map["latitude"], on_map["longitude"])
    fig = px.scatter_map(
        on_map, lat="latitude", lon="longitude", color="preco",
        color_continuous_scale=PRICE_SCALE, range_color=(low, high),
        hover_name="posto", hover_data={"marca": True, "municipio": True, "preco": ":.3f",
                                         "latitude": False, "longitude": False},
        labels={"marca": "Brand", "municipio": "Municipality", "preco": "Price (€)"},
        zoom=zoom, center=center, height=MAP_HEIGHT, map_style="carto-positron",
    )
    fig.update_traces(marker=dict(size=8, opacity=0.9))
    fig.update_layout(margin=dict(l=0, r=0, t=0, b=0),
                      coloraxis_colorbar=dict(title="€", thickness=12, len=0.6, tickformat=".2f"))
    chart(fig, col_map)

    # Next to the map: key numbers for the selected fuel, then the 10 cheapest stations
    m1, m2, m3 = col_list.columns(3)
    m1.metric("Lowest", f"{day['preco'].min():.3f} €")
    m2.metric("Highest", f"{day['preco'].max():.3f} €")
    m3.metric("Stations", f"{len(day):,}")
    col_list.markdown(f"**Cheapest stations for {html.escape(fuel)}**")
    col_list.dataframe(
        day.nsmallest(10, "preco")[["posto", "municipio", "preco"]], hide_index=True, width="stretch",
        column_config={"posto": st.column_config.TextColumn("Station", width="medium"),
                       "municipio": st.column_config.TextColumn("Municipality", width="small"),
                       "preco": st.column_config.NumberColumn("Price (€)", format="%.3f", width="small")},
    )
    col_list.caption("Green dots are cheaper, red dots more expensive. The full list is in the Stations tab.")

with tab_evol:
    other_fuels = st.multiselect("Compare with other fuels", [x for x in fuels if x != fuel], placeholder="Add fuels")
    if other_fuels:
        # One line per fuel (districts are combined)
        series = average(load_series(tuple([fuel] + other_fuels), start, end, f), ["data", "combustivel"])
        fig = line_chart(series, "preco_medio", all_days, color="combustivel")
    elif districts:
        # One line per selected district
        fig = line_chart(average(series_main, ["data", "distrito"]), "preco_medio", all_days, color="distrito")
    else:
        fig = line_chart(daily, "preco_medio", all_days)
    chart(fig)
    st.caption(f"{len(daily)} day(s) of data in this period. A new snapshot is added daily; "
               "dotted segments cross days with no data.")

with tab_list:
    station_columns = {"posto": "Station", "marca": "Brand", "tipo_posto": "Type", "morada": "Address",
                       "localidade": "Town", "municipio": "Municipality", "distrito": "District"}
    table = day.sort_values("preco")[list(station_columns) + ["preco", "data_atualizacao"]]
    st.dataframe(
        table, hide_index=True, width="stretch", height=480,
        column_config={**station_columns,
                       "preco": st.column_config.NumberColumn("Price (€)", format="%.3f"),
                       "data_atualizacao": st.column_config.DatetimeColumn("Price updated", format="DD/MM/YYYY HH:mm")},
    )
    # UTF-8 with BOM ("utf-8-sig") makes Excel show accents correctly
    st.download_button(
        "Download this list (CSV)", table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"fuel_prices_{fuel}_{snapshot}.csv".replace(" ", "_"), mime="text/csv",
    )
    st.caption(f"{len(table):,} stations, cheapest first.")

with tab_changes:
    if previous_snapshot is None:
        st.info("Price changes need at least two days of data. Choose a longer period on the left.")
    else:
        before = load_day(fuel, previous_snapshot, f)[["posto_id", "preco"]]
        changes = day.merge(before, on="posto_id", suffixes=("", "_antes"))   # stations present on both days
        changes["variacao"] = changes["preco"] - changes["preco_antes"]
        raised, lowered = (changes["variacao"] > 0).sum(), (changes["variacao"] < 0).sum()
        st.write(f"From {previous_snapshot:%d/%m} to {snapshot:%d/%m}, **{raised:,}** stations raised the price, "
                 f"**{lowered:,}** lowered it and **{len(changes) - raised - lowered:,}** kept it.")
        cfg = {"posto": "Station", "marca": "Brand", "municipio": "Municipality",
               "preco_antes": st.column_config.NumberColumn("Before (€)", format="%.3f"),
               "preco": st.column_config.NumberColumn("Now (€)", format="%.3f"),
               "variacao": st.column_config.NumberColumn("Change (€)", format="%+.3f")}
        shown = ["posto", "marca", "municipio", "preco_antes", "preco", "variacao"]
        a, b = st.columns(2, gap="large")
        a.subheader("Largest increases")
        a.dataframe(changes[changes["variacao"] > 0].nlargest(10, "variacao")[shown], hide_index=True, column_config=cfg)
        b.subheader("Largest decreases")
        b.dataframe(changes[changes["variacao"] < 0].nsmallest(10, "variacao")[shown], hide_index=True, column_config=cfg)

with tab_station:
    stations = day.sort_values(["posto", "municipio"])
    # Readable label for each station id, e.g. "INTERMARCHÉ FAMÕES, Odivelas (INTERMARCHÉ)"
    labels = {r.posto_id: f"{r.posto}, {r.municipio} ({r.marca})" for r in stations.itertuples()}
    station_id = st.selectbox(
        "Station", list(labels), format_func=labels.get,
        help="Stations matching the filters on the left. Type a name in 'Station name' to narrow the list.",
    )
    history = load_station_history(int(station_id), start, end)
    chart(line_chart(history, "preco", all_days, color="combustivel", ytitle="Price (€)"))

    st.subheader("Station details over time")
    st.dataframe(
        load_station_versions(int(station_id)), hide_index=True, width="stretch",
        column_config={"nome": "Name", "marca": "Brand", "tipo_posto": "Type", "morada": "Address",
                       "municipio": "Municipality", "valido_de": "Valid from", "valido_ate": "Valid until",
                       "atual": "Current"},
    )
    st.caption("A new row appears when DGEG reports a change to the station, such as a new brand, "
               "so older prices keep the details that were true at the time.")

with tab_brand:
    MIN_STATIONS = 10
    brand_avg = (day.groupby("marca").agg(preco_medio=("preco", "mean"), postos=("preco", "size"))
                    .query("postos >= @MIN_STATIONS").sort_values("preco_medio").reset_index())
    if brand_avg.empty:
        st.info(f"No brand has {MIN_STATIONS} or more stations with these filters. Remove a filter to compare brands.")
    else:
        fig = px.bar(brand_avg, x="preco_medio", y="marca", orientation="h", hover_data={"postos": True},
                     text=brand_avg["preco_medio"].map("{:.3f}".format),
                     labels={"preco_medio": "Average price (€)", "marca": "Brand", "postos": "Stations"})
        fig.update_traces(marker_color=PETROL, textposition="outside", cliponaxis=False)
        fig.update_layout(xaxis_title="Average price (€)", yaxis_title=None, height=max(300, 30 * len(brand_avg)),
                          yaxis={"categoryorder": "total descending"})
        fig.update_xaxes(range=[brand_avg["preco_medio"].min() * 0.98, brand_avg["preco_medio"].max() * 1.015])
        chart(fig)
        st.caption(f"Brands with {MIN_STATIONS} or more stations in the current selection.")

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
        "1. **Extract.** Every day, a GitHub Actions job requests all prices from DGEG's API, about 13,600 records.\n"
        "2. **Bronze.** DGEG's answer is saved exactly as it came, in Azure Blob Storage.\n"
        "3. **Transform.** Python and pandas clean the data, for example turning \"1,164 €\" into 1.164.\n"
        "4. **Load.** The day's rows are loaded into a star schema in PostgreSQL (Neon), "
        "with station history tracked as a slowly changing dimension.\n"
        "5. **Serve.** This dashboard reads the warehouse through a view, using a read-only database user.\n\n"
        f"Code, documentation and design decisions: [GitHub repository]({REPO_URL})."
    )

st.caption(f"Source: [DGEG, Preços dos Combustíveis](https://precoscombustiveis.dgeg.gov.pt). "
           f"Latest data: {dates[-1]:%d/%m/%Y}.")
