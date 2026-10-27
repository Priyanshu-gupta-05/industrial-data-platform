"""Industrial Data Platform - Streamlit dashboard (entry point).

    cd dashboard
    streamlit run app.py

Local mode reads PostgreSQL (dashboard/.streamlit/secrets.toml, never committed);
hosted mode reads the bundled Parquet snapshot. The sidebar filters apply to every page.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib import data  # noqa: E402

st.set_page_config(page_title="Industrial Data Platform", page_icon="⚙️", layout="wide")

PAGES = [
    st.Page("views/1_fleet_overview.py", title="Fleet overview", icon=":material/factory:", default=True),
    st.Page("views/2_plant_drilldown.py", title="Plant drill-down", icon=":material/grid_view:"),
    st.Page("views/3_machine_health.py", title="Machine health", icon=":material/monitor_heart:"),
    st.Page("views/4_alarms.py", title="Alarms", icon=":material/notifications_active:"),
    st.Page("views/5_quality.py", title="Quality", icon=":material/verified:"),
    st.Page("views/6_edge_demo.py", title="Edge demo", icon=":material/memory:"),
    st.Page("views/7_volume_cost.py", title="Data volume & cost", icon=":material/calculate:"),
    st.Page("views/8_predictive_maintenance.py", title="Predictive maintenance", icon=":material/insights:"),
]
nav = st.navigation(PAGES)

# ---------------------------------------------------------------- shared sidebar filters
md = data.machine_data()
plants = data.master()["plant"]
first_day = md.ts.min().date()
last_day = (md.ts.max() - pd.Timedelta(hours=1)).date()
with st.sidebar:
    st.markdown("### Filters")
    sel = st.multiselect("Plant", plants.plant_id.tolist(), default=plants.plant_id.tolist(),
                         format_func=lambda i: f"{plants.set_index('plant_id').loc[i, 'plant_code']} - "
                                               f"{plants.set_index('plant_id').loc[i, 'location']}")
    rng = st.date_input("Date range (IST)", value=(last_day - dt.timedelta(days=29), last_day),
                        min_value=first_day, max_value=last_day)
    start, end = (rng if isinstance(rng, tuple) and len(rng) == 2 else (rng[0], rng[0]))
    st.session_state["filters"] = {
        "plants": sel or plants.plant_id.tolist(),
        "start": pd.Timestamp(start, tz="Asia/Kolkata"),
        "end": pd.Timestamp(end, tz="Asia/Kolkata") + pd.Timedelta(days=1),
    }
    st.divider()
    mode = data.backend()
    st.markdown(f"**Data source:** {'PostgreSQL (local)' if mode == 'postgres' else 'Parquet snapshot (hosted)'}")
    st.caption("Scenario: Automotive Tier-1 supplier, 3 plants, 100 CNC machines, 2025 calendar. "
               "Data: Bosch & UMich (REAL), Azure PdM & AI4I (BENCHMARK); fleet columns DERIVED.")

nav.run()
