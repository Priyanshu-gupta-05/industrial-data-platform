import textwrap

import pandas as pd
import plotly.express as px
import streamlit as st

from lib import data, ui

ui.setup("Alarms", "Pareto of alarm types, alarm timeline and reliability (MTBF / MTTR)")
md = ui.filtered(data.machine_data())
mm = data.master()
m, am = mm["machine"], mm["alarm"]
ev = data.events()
f = ui.get_filters()
ev = ev[(ev.ts >= f["start"]) & (ev.ts < f["end"]) & ev.event_type.isin(["ERROR", "FAILURE"])]
ev = ev.merge(m[["machine_id", "machine_code", "plant_id", "plant_code"]], on="machine_id")
ev = ev[ev.plant_id.isin(f["plants"])].merge(am[["alarm_code", "alarm_name", "severity"]], on="alarm_code")
if ev.empty:
    st.info("No alarms in the selected period.")
    st.stop()

c = st.columns(4)
ui.kpi(c[0], "Alarm events", f"{len(ev):,}", "errors + failures")
ui.kpi(c[1], "Critical (failures)", f"{(ev.severity == 'CRITICAL').sum():,}", "component failures")
ui.kpi(c[2], "Machines affected", f"{ev.machine_id.nunique()}", f"of {md.machine_id.nunique()}")
top = ev.alarm_name.value_counts()
ui.kpi(c[3], "Top alarm", f"{top.iloc[0]}", top.index[0][:40])
st.write("")

left, right = st.columns([1, 1.2])
with left:
    p = ev.groupby(["alarm_code", "alarm_name", "severity"]).size().reset_index(name="events")
    p = p.sort_values("events", ascending=False)
    p["cum"] = p.events.cumsum() / p.events.sum()
    p["label"] = p.apply(lambda r: f"{r.events}  (cum. {r.cum:.0%})", axis=1)
    p["name"] = p["alarm_name"].map(lambda s: "<br>".join(textwrap.wrap(s, 22)))   # wrap long names for narrow screens
    fig = px.bar(p, x="events", y="name", orientation="h", color="severity", text="label",
                 color_discrete_map={"WARNING": ui.STATUS["warning"], "CRITICAL": ui.STATUS["critical"]},
                 title="Alarm Pareto (cumulative share in labels)")
    fig.update_yaxes(categoryorder="total ascending", title=None)
    fig.update_traces(textposition="auto")
    fig.update_layout(height=430)
    ui.chart(fig)
with right:
    fig = px.scatter(ev, x="ts", y="machine_code", color="severity", symbol="severity",
                     color_discrete_map={"WARNING": ui.STATUS["warning"], "CRITICAL": ui.STATUS["critical"]},
                     hover_data=["alarm_code", "alarm_name"], title="Alarm timeline")
    fig.update_traces(marker=dict(size=8, line=dict(width=1, color="white")))
    fig.update_yaxes(title=None, categoryorder="category descending")
    fig.update_xaxes(title=None)
    fig.update_layout(height=max(430, 9 * ev.machine_code.nunique()))
    ui.chart(fig)

daily = ev.assign(day=ev.ts.dt.tz_localize(None).dt.floor("D")).groupby(["day", "plant_code"]).size().reset_index(name="alarms")
fig = px.bar(daily, x="day", y="alarms", color="plant_code", color_discrete_map=ui.PLANT_COLORS,
             title="Alarm events per day by plant")
ui.chart(fig)

st.subheader("Reliability per machine (full year, from sql/04_advanced_queries.sql)")
rel = data.sql_result("a3_mtbf_mttr_per_machine")
rel = rel[rel.plant_code.isin(m[m.plant_id.isin(f["plants"])].plant_code.unique())]
c1, c2 = st.columns([1.2, 1])
with c1:
    fig = px.scatter(rel, x="mtbf_hours", y="mttr_hours", color="plant_code", color_discrete_map=ui.PLANT_COLORS,
                     size="failures", hover_name="machine_code", title="MTBF vs MTTR (bubble = failures)",
                     labels={"mtbf_hours": "MTBF (running hours)", "mttr_hours": "MTTR (hours)"})
    ui.chart(fig)
with c2:
    st.dataframe(rel.sort_values("mtbf_hours").head(15), hide_index=True, width="stretch")
st.caption("Alarm names are an illustrative mapping of Azure PdM benchmark events (see core.alarm_master).")
