# CHARTS: colours, the Plotly theme, and the chart and map helpers the dashboard uses

import math

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# Same palette as .streamlit/config.toml
INK, MUTED, RULE, GRID = "#1C2430", "#5B6676", "#DCE1E7", "#E9ECF0"
PETROL, CHEAP, DEAR = "#0E5A73", "#1F7A5A", "#B5462B"

# Price colour scale for the map: green (cheap) -> sand (average) -> rust (expensive)
PRICE_SCALE = [[0.0, CHEAP], [0.5, "#E6DFCB"], [1.0, DEAR]]
MAP_HEIGHT = 520

# Plotly theme, so every chart uses the same font, colours and quiet gridlines
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


def average(df, by):
    """Average price per group, from sums and counts."""
    g = df.groupby(by, as_index=False)[["soma", "n"]].sum()
    g["preco_medio"] = g["soma"] / g["n"]
    return g


def line_chart(df, y, days, color=None, ytitle="Average price (€)"):
    """
    Line chart over time, honest about missing days:
    - SOLID line between consecutive days with data
    - thin DOTTED line where days are missing (it only connects the snapshots on each side)
    One line per value of `color` (e.g. per fuel), or a single line if color is None.
    """
    fig = go.Figure()
    palette = pio.templates["fuel"].layout.colorway
    groups = [(None, df)] if color is None else list(df.groupby(color))
    for i, (name, d) in enumerate(groups):
        d = d.dropna(subset=[y]).sort_values("data")
        line_color = palette[i % len(palette)]
        # 1. Dotted line through every snapshot (visible only where the solid line is missing)
        fig.add_scatter(x=d["data"], y=d[y], mode="lines", hoverinfo="skip", showlegend=False,
                        line=dict(color=line_color, width=1.5, dash="dot"))
        # 2. Solid line on a full calendar: missing days are empty, so the line breaks there
        full = d.set_index("data")[y].reindex(days)
        fig.add_scatter(x=full.index, y=full.values, name=name or "", showlegend=color is not None,
                        mode="lines" if len(d) > 1 else "markers",   # a single day can only be a dot
                        line=dict(color=line_color, width=2.5), connectgaps=False,
                        hovertemplate="%{x|%d/%m/%Y}<br>%{y:.3f} €<extra>" + (name or "") + "</extra>")
    fig.update_layout(xaxis_title=None, yaxis_title=ytitle, yaxis_tickformat=".3f", legend_title=None,
                      hovermode="x unified", legend=dict(orientation="h", y=1.08, x=0))
    return fig


def map_view(lat, lon, height=MAP_HEIGHT, width=800):
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
    zoom = min(math.log2(height / 512 * 2 * math.pi / dy), math.log2(width / 512 * 360 / dx)) - 0.3
    center_lat = math.degrees(2 * math.atan(math.exp((merc(lat0) + merc(lat1)) / 2)) - math.pi / 2)
    return {"lat": center_lat, "lon": (lon0 + lon1) / 2}, max(3.0, min(zoom, 12.0))


def chart(fig, container=st):
    """Shows a Plotly figure. theme=None keeps our own theme instead of Streamlit's default styling."""
    # Colours set on the figure too: the browser doesn't always apply the template's backgrounds
    fig.update_layout(paper_bgcolor="white", plot_bgcolor="white")
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
    container.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False})
