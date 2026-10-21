import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import data, ui

ui.setup("Fleet overview", "100 CNC machines across Chakan, Oragadam and Manesar - KPIs for the selected period")
md = ui.filtered(data.machine_data())
m = data.master()["machine"]
if md.empty:
    st.warning("No data for the selected filters.")
    st.stop()

k = ui.oee_parts(md)
last_ts = md.ts.max()
running_now = (md[md.ts == last_ts].machine_status == "RUNNING").sum()
n_machines = md.machine_id.nunique()
day_end = last_ts.normalize() if last_ts.hour < 23 else last_ts.normalize() + pd.Timedelta(days=1)
last_day = md[(md.ts >= day_end - pd.Timedelta(days=1)) & (md.ts < day_end)]   # last COMPLETE day
open_alarms = int(md[md.ts > last_ts - pd.Timedelta(hours=24)].alarm_count.sum())

c = st.columns(5)
ui.kpi(c[0], "Machines running", f"{running_now} / {n_machines}", f"at {last_ts:%d %b %H:%M} IST")
ui.kpi(c[1], "OEE", f"{k['oee']:.1%}", f"A {k['availability']:.0%} · P {k['performance']:.0%} · Q {k['quality']:.1%}")
ui.kpi(c[2], "Parts last full day", f"{int(last_day.production_count.sum()):,}",
       f"{day_end - pd.Timedelta(days=1):%d %b %Y}")
ui.kpi(c[3], "Reject rate", f"{k['reject_rate']:.2%}", f"{k['rejects']:,} of {k['parts']:,} parts")
ui.kpi(c[4], "Alarms, last 24 h", f"{open_alarms}", "events across selected plants")
st.write("")

md = md.merge(m[["machine_id", "plant_code"]], on="machine_id")
left, right = st.columns([1.1, 1])
with left:
    rows = []
    for p, g in md.groupby("plant_code"):
        o = ui.oee_parts(g)
        rows += [{"plant": p, "component": n, "value": o[key]} for key, n in
                 [("availability", "Availability"), ("performance", "Performance"), ("quality", "Quality"), ("oee", "OEE")]]
    fig = px.bar(pd.DataFrame(rows), x="component", y="value", color="plant", barmode="group",
                 color_discrete_map=ui.PLANT_COLORS, text_auto=".1%", title="OEE components by plant")
    fig.update_yaxes(tickformat=".0%", range=[0, 1.08], title=None)
    fig.update_xaxes(title=None)
    st.plotly_chart(fig, use_container_width=True)
with right:
    mix = md.groupby(["plant_code", "machine_status"], observed=True).size().reset_index(name="hours")
    mix["share"] = mix.hours / mix.groupby("plant_code").hours.transform("sum")
    fig = px.bar(mix, y="plant_code", x="share", color="machine_status", orientation="h",
                 color_discrete_map=ui.STATUS_COLORS, title="Machine-hours by status",
                 category_orders={"machine_status": data.STATUS_ORDER})
    fig.update_xaxes(tickformat=".0%", title=None)
    fig.update_yaxes(title=None)
    st.plotly_chart(fig, use_container_width=True)

daily = (md.assign(day=md.ts.dt.tz_localize(None).dt.floor("D"))
           .groupby(["day", "plant_code"]).agg(parts=("production_count", "sum"),
                                               rejects=("reject_count", "sum")).reset_index())
fig = px.line(daily, x="day", y="parts", color="plant_code", color_discrete_map=ui.PLANT_COLORS,
              title="Daily parts produced by plant", labels={"parts": "Parts per day", "day": ""})
st.plotly_chart(fig, use_container_width=True)

tbl = (md.groupby("plant_code").apply(lambda g: pd.Series(ui.oee_parts(g)), include_groups=False)
         [["parts", "rejects", "reject_rate", "availability", "performance", "quality", "oee"]])
st.dataframe(tbl.style.format({"parts": "{:,.0f}", "rejects": "{:,.0f}", "reject_rate": "{:.2%}",
                               "availability": "{:.1%}", "performance": "{:.1%}", "quality": "{:.2%}", "oee": "{:.1%}"}),
             use_container_width=True)
ui.derived_note()
