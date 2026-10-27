import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import data, ui

ui.setup("Machine health", "Telemetry trends with ISO 10816-3 vibration zones, tool wear and a 0-100 health score")
md = ui.filtered(data.machine_data())
m = data.master()["machine"]
m = m[m.machine_id.isin(md.machine_id.unique())]
if m.empty:
    st.warning("No data for the selected filters.")
    st.stop()
mid = st.selectbox("Machine", m.machine_id, format_func=lambda i: (lambda r: f"{r.machine_code} - {r.part_name} "
                   f"({r.controller})")(m.set_index("machine_id").loc[i]), index=0)
info = m.set_index("machine_id").loc[mid]
d = md[md.machine_id == mid].sort_values("ts")
run = d[d.running_minutes > 0]

last24 = d[d.ts > d.ts.max() - pd.Timedelta(hours=24)]
r24 = last24[last24.running_minutes > 0]
hs = ui.health_score(r24.vibration.mean() if len(r24) else 0, r24.temperature.mean() if len(r24) else 0,
                     int(last24.alarm_count.sum()), float(last24.tool_wear_min.max()))
c = st.columns(5)
ui.kpi(c[0], "Health score (last 24 h)", f"{hs:.0f} / 100", "vibration, temperature, alarms, wear")
ui.kpi(c[1], "Avg vibration", f"{run.vibration.mean():.2f} mm/s", f"max {run.vibration.max():.2f} mm/s")
ui.kpi(c[2], "Avg temperature", f"{run.temperature.mean():.1f} °C", f"max {run.temperature.max():.1f} °C")
ui.kpi(c[3], "Avg RPM (running)", f"{d[d.machine_status == 'RUNNING'].rpm.mean():,.0f}",
       f"type range {info.rpm_min:,}-{info.rpm_max:,}")
ui.kpi(c[4], "Alarms in period", f"{int(d.alarm_count.sum())}", f"{info.machine_type} · {info.plant_code}")
st.write("")

agg = st.segmented_control("Resolution", ["Hourly", "Daily mean"], default="Hourly")
if agg == "Daily mean":
    run = run.set_index("ts").resample("D").mean(numeric_only=True).reset_index()
fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
                    subplot_titles=("Spindle vibration (mm/s RMS) with ISO 10816-3 zones", "Temperature (°C)",
                                    "Spindle current (A)", "Tool wear (min)"))
for lo, hi, name, col in ui.ISO_ZONES:
    fig.add_hrect(y0=lo, y1=hi, fillcolor=col, line_width=0, row=1, col=1,
                  annotation_text=name, annotation_position="right", annotation_font_size=10)
fig.add_trace(go.Scattergl(x=run.ts, y=run.vibration, mode="lines", line=dict(color=ui.SERIES[0], width=1.2),
                           name="vibration"), row=1, col=1)
fig.add_trace(go.Scattergl(x=run.ts, y=run.temperature, mode="lines", line=dict(color=ui.SERIES[1], width=1.2),
                           name="temperature"), row=2, col=1)
fig.add_trace(go.Scattergl(x=run.ts, y=run.current, mode="lines", line=dict(color=ui.SERIES[2], width=1.2),
                           name="current"), row=3, col=1)
fig.add_trace(go.Scattergl(x=d.ts, y=d.tool_wear_min, mode="lines", line=dict(color=ui.SERIES[6], width=1.2),
                           name="tool wear"), row=4, col=1)
al = d[d.alarm]
fig.add_trace(go.Scatter(x=al.ts, y=[0.2] * len(al), mode="markers", name="alarm",
                         marker=dict(symbol="triangle-up", size=10, color=ui.STATUS["critical"]),
                         text=al.alarm_code, hovertemplate="%{x}<br>%{text}<extra>alarm</extra>"), row=1, col=1)
fig.update_yaxes(range=[0, max(5, float(run.vibration.max()) * 1.1)], row=1, col=1)
fig.update_layout(height=900, showlegend=False, margin=dict(r=90))
ui.chart(fig)

if len(al):
    am = data.master()["alarm"][["alarm_code", "alarm_name", "severity"]]
    st.subheader("Alarms in the selected period")
    st.dataframe(al[["ts", "alarm_code", "alarm_count", "machine_status"]].merge(am, on="alarm_code"),
                 hide_index=True, width="stretch")
ui.derived_note()
