"""Shared look and feel: palette (same as the report figures), Plotly template, KPI cards, filters, KPIs."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
PLANT_COLORS = {"P1": SERIES[0], "P2": SERIES[1], "P3": SERIES[2]}
STATUS_COLORS = {"RUNNING": STATUS["good"], "IDLE": "#c3c2b7", "ALARM": STATUS["critical"],
                 "MAINTENANCE": STATUS["warning"], "OFF": "#52514e"}
ISO_ZONES = [(0, 1.4, "A good", "rgba(12,163,12,0.10)"), (1.4, 2.8, "B acceptable", "rgba(159,216,159,0.14)"),
             (2.8, 4.5, "C alert", "rgba(250,178,25,0.16)"), (4.5, 12, "D danger", "rgba(208,59,59,0.12)")]
SEQ_BLUE = [[0, "#f3f7fd"], [0.25, "#9ec5f4"], [0.5, "#3987e5"], [0.75, "#1c5cab"], [1, "#0d366b"]]

pio.templates["idp"] = go.layout.Template(layout=dict(
    colorway=SERIES, font=dict(family="Segoe UI, system-ui, sans-serif", size=13, color="#0b0b0b"),
    title=dict(font=dict(size=15), x=0, xanchor="left"),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    xaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7", zeroline=False),
    yaxis=dict(gridcolor="#e1e0d9", linecolor="#c3c2b7", zeroline=False),
    margin=dict(l=10, r=10, t=50, b=10),
    hoverlabel=dict(font_size=12)))
pio.templates.default = "plotly_white+idp"

CSS = """
<style>
.block-container {padding-top: 2.2rem; max-width: 1500px;}
h1 {font-size: clamp(1.6rem, 1.2rem + 1.6vw, 2.6rem) !important;}

/* Responsive columns: instead of shrinking, columns wrap onto the next row when the screen is narrow.
   Charts/tables need ~340 px, KPI cards ~170 px. */
[data-testid="stHorizontalBlock"] {flex-wrap: wrap !important; gap: 0.75rem !important;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"],
[data-testid="stHorizontalBlock"] > [data-testid="column"] {flex: 1 1 340px !important; min-width: min(340px, 100%) !important;}
[data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:has(.kpi),
[data-testid="stHorizontalBlock"] > [data-testid="column"]:has(.kpi) {flex: 1 1 170px !important; min-width: min(170px, 100%) !important;}

.kpi {border: 1px solid rgba(11,11,11,0.10); border-radius: 10px; padding: 12px 14px; background: #ffffff;
      color: #0b0b0b; box-shadow: 0 1px 2px rgba(11,11,11,0.04); height: 100%;}
.kpi .lab {font-size: 0.74rem; color: #52514e; text-transform: uppercase; letter-spacing: .04em; line-height: 1.3;}
.kpi .val {font-size: clamp(1.25rem, 0.9rem + 1.1vw, 1.9rem); font-weight: 650; line-height: 1.25;
           word-break: keep-all; overflow-wrap: normal;}
.kpi .sub {font-size: 0.76rem; color: #898781; line-height: 1.3;}
.tag {display:inline-block; padding:1px 8px; border-radius:10px; font-size:0.72rem; margin-left:6px;
      border:1px solid rgba(11,11,11,0.15); color:#52514e;}
</style>
"""


def chart(fig, height: int | None = None) -> None:
    """Show a Plotly chart full-width with the legend below the plot, so it can never collide with the title."""
    fig.update_layout(legend=dict(orientation="h", x=0, xanchor="left", y=0, yref="container", yanchor="bottom",
                                  title_text=""),
                      margin=dict(t=50, b=60), autosize=True)          # merges: keeps a page's own l/r margins
    if height:
        fig.update_layout(height=height)
    # toolbar hidden: on narrow screens it covers the title (drag still zooms, double-click resets)
    st.plotly_chart(fig, width="stretch", config={"responsive": True, "displayModeBar": False})


def setup(title: str, subtitle: str = "") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    st.title(title)
    if subtitle:
        st.caption(subtitle)


def kpi(col, label: str, value: str, sub: str = "") -> None:
    col.markdown(f'<div class="kpi"><div class="lab">{label}</div><div class="val">{value}</div>'
                 f'<div class="sub">{sub}</div></div>', unsafe_allow_html=True)


def derived_note() -> None:
    st.caption("Fleet values are DERIVED from the Azure PdM benchmark backbone with models calibrated on real "
               "UMich and Bosch data and the AI4I benchmark - see data/DATA_PROVENANCE.md.")


def get_filters() -> dict:
    """Sidebar filters (set in app.py); safe defaults if a page is rendered before they exist."""
    f = st.session_state.get("filters")
    if not f:
        f = {"plants": [1, 2, 3], "start": pd.Timestamp("2025-01-01", tz="Asia/Kolkata"),
             "end": pd.Timestamp("2026-01-03", tz="Asia/Kolkata")}
    return f


def filtered(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the sidebar plant + date filters stored in session state."""
    f = get_filters()
    out = df
    if f.get("plants"):
        out = out[out.plant_id.isin(f["plants"])]
    if f.get("start") is not None:
        out = out[(out.ts >= f["start"]) & (out.ts < f["end"])]
    return out


def oee_parts(df: pd.DataFrame) -> dict:
    planned = 60.0 * (df.machine_status != "OFF").sum()
    run = df.running_minutes.sum()
    parts, ideal, rej = df.production_count.sum(), df.ideal_count.sum(), df.reject_count.sum()
    a = run / planned if planned else 0
    p = min(parts / ideal, 1) if ideal else 0
    q = (parts - rej) / parts if parts else 0
    return {"availability": a, "performance": p, "quality": q, "oee": a * p * q, "parts": int(parts),
            "rejects": int(rej), "reject_rate": rej / parts if parts else 0}


def health_score(vib: float, temp: float, alarms: int, wear: float) -> float:
    """Same rule as analytics.v_machine_health (sql/04_advanced_queries.sql)."""
    s = 100 - 25 * max(0, (vib - 1.8) / 1.2) - 10 * max(0, (temp - 40) / 5) - 15 * min(alarms, 3) - 10 * wear / 240
    return max(0.0, min(100.0, round(s)))
