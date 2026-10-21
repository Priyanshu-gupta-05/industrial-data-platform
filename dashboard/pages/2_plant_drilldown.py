import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import data, ui

ui.setup("Plant drill-down", "Shop-floor status heatmap, production trend and machine league table")
md_all = ui.filtered(data.machine_data())
mm = data.master()
m, plants = mm["machine"], mm["plant"]
avail = [p for p in plants.plant_id if p in md_all.plant_id.unique()]
if not avail:
    st.warning("No data for the selected filters.")
    st.stop()
pid = st.radio("Plant", avail, horizontal=True,
               format_func=lambda i: plants.set_index("plant_id").loc[i, "plant_name"])
md = md_all[md_all.plant_id == pid].merge(m[["machine_id", "machine_code", "machine_type", "part_name"]], on="machine_id")

view = st.segmented_control("Heatmap", ["Daily running share", "Hourly status on one day"], default="Daily running share")
if view == "Hourly status on one day":
    days = sorted(md.ts.dt.date.unique())
    day = st.select_slider("Day", options=days, value=days[-1])
    d = md[md.ts.dt.date == day]
    codes = {s: i for i, s in enumerate(data.STATUS_ORDER)}
    piv = d.pivot_table(index="machine_code", columns=d.ts.dt.hour, values="machine_status",
                        aggfunc=lambda s: codes[str(s.iloc[0])])
    n = len(data.STATUS_ORDER)
    scale = []
    for i, s in enumerate(data.STATUS_ORDER):
        scale += [[i / n, ui.STATUS_COLORS[s]], [(i + 1) / n, ui.STATUS_COLORS[s]]]
    fig = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=piv.index, colorscale=scale, zmin=-0.5, zmax=n - 0.5,
                               xgap=1, ygap=1, customdata=[[data.STATUS_ORDER[int(v)] if v == v else "" for v in r]
                                                           for r in piv.values],
                               hovertemplate="%{y} %{x}:00 - %{customdata}<extra></extra>",
                               colorbar=dict(tickvals=list(range(n)), ticktext=data.STATUS_ORDER)))
    fig.update_layout(title=f"Machine status by hour, {day:%d %b %Y}", height=max(420, 18 * len(piv)),
                      xaxis_title="Hour of day (IST)")
else:
    d = md.assign(day=md.ts.dt.tz_localize(None).dt.floor("D"))
    piv = d.groupby(["machine_code", "day"]).running_minutes.sum().unstack() / (24 * 60)
    fig = go.Figure(go.Heatmap(z=piv.values, x=piv.columns, y=piv.index, colorscale=ui.SEQ_BLUE, zmin=0, zmax=1,
                               xgap=1, ygap=1, hovertemplate="%{y} %{x|%d %b}: %{z:.0%} running<extra></extra>",
                               colorbar=dict(title="Running", tickformat=".0%")))
    fig.update_layout(title="Share of each day spent running (dark = productive)", height=max(420, 18 * len(piv)))
st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    t = (md.assign(day=md.ts.dt.tz_localize(None).dt.floor("D")).groupby(["day", "part_name"])
           .production_count.sum().reset_index())
    fig = px.area(t, x="day", y="production_count", color="part_name", title="Daily parts by part family",
                  labels={"production_count": "Parts per day", "day": ""})
    st.plotly_chart(fig, use_container_width=True)
with c2:
    sh = md.groupby("shift").agg(parts=("production_count", "sum"), rejects=("reject_count", "sum")).reset_index()
    sh["reject_rate"] = sh.rejects / sh.parts
    fig = px.bar(sh, x="shift", y="parts", text_auto=",.0f", title="Parts by shift (A 06-14, B 14-22, C 22-06)",
                 color_discrete_sequence=[ui.SERIES[0]])
    st.plotly_chart(fig, use_container_width=True)

league = (md.groupby(["machine_code", "machine_type", "part_name"])
            .apply(lambda g: pd.Series(ui.oee_parts(g)), include_groups=False).reset_index()
            .sort_values("oee"))
st.subheader("Machine league table (lowest OEE first)")
st.dataframe(league[["machine_code", "machine_type", "part_name", "parts", "reject_rate", "availability",
                     "performance", "quality", "oee"]],
             column_config={"oee": st.column_config.ProgressColumn("OEE", format="percent", min_value=0, max_value=1),
                            "reject_rate": st.column_config.NumberColumn("Reject rate", format="percent"),
                            "availability": st.column_config.NumberColumn(format="percent"),
                            "performance": st.column_config.NumberColumn(format="percent"),
                            "quality": st.column_config.NumberColumn(format="percent"),
                            "parts": st.column_config.NumberColumn(format="localized")},
             hide_index=True, use_container_width=True)
ui.derived_note()
