import pandas as pd
import plotly.express as px
import streamlit as st

from lib import data, ui

ui.setup("Quality", "Rejection rate by machine and part family, and its link to tool wear")
md = ui.filtered(data.machine_data())
m = data.master()["machine"]
md = md.merge(m[["machine_id", "machine_code", "part_name", "plant_code", "machine_type"]], on="machine_id")
k = ui.oee_parts(md)
c = st.columns(4)
ui.kpi(c[0], "Parts produced", f"{k['parts']:,}")
ui.kpi(c[1], "Rejected", f"{k['rejects']:,}")
ui.kpi(c[2], "Reject rate", f"{k['reject_rate']:.2%}", "SUM(rejects) / SUM(parts)")
ui.kpi(c[3], "First-pass yield", f"{1 - k['reject_rate']:.2%}")
st.write("")

left, right = st.columns(2)
with left:
    pf = md.groupby(["part_name", "plant_code"]).agg(parts=("production_count", "sum"),
                                                     rejects=("reject_count", "sum")).reset_index()
    pf["reject_rate"] = pf.rejects / pf.parts
    fig = px.bar(pf.sort_values("reject_rate"), x="reject_rate", y="part_name", color="plant_code", orientation="h",
                 color_discrete_map=ui.PLANT_COLORS, text_auto=".2%", title="Reject rate by part family")
    fig.update_xaxes(tickformat=".1%", title=None)
    fig.update_yaxes(title=None)
    ui.chart(fig)
with right:
    b = md[md.production_count > 0].copy()
    b["wear_band"] = pd.cut(b.tool_wear_min, bins=range(0, 270, 30))
    w = b.groupby("wear_band", observed=True).agg(parts=("production_count", "sum"),
                                                  rejects=("reject_count", "sum")).reset_index()
    w["reject_rate"] = w.rejects / w.parts
    w["band"] = w.wear_band.astype(str)
    fig = px.line(w, x="band", y="reject_rate", markers=True, title="Reject rate rises with tool wear",
                  labels={"band": "Tool wear band (min)", "reject_rate": "Reject rate"})
    fig.update_traces(line_color=ui.SERIES[7])
    fig.update_yaxes(tickformat=".1%")
    ui.chart(fig)

mc = md.groupby(["machine_code", "part_name"]).agg(parts=("production_count", "sum"),
                                                   rejects=("reject_count", "sum"),
                                                   vib=("vibration", "mean")).reset_index()
mc["reject_rate"] = mc.rejects / mc.parts
fig = px.bar(mc.nlargest(20, "reject_rate"), x="machine_code", y="reject_rate", color="part_name",
             title="Top-20 machines by reject rate", text_auto=".2%")
fig.update_yaxes(tickformat=".1%", title=None)
fig.update_xaxes(title=None)
ui.chart(fig)
st.caption("Reject counts are DERIVED: probability model calibrated on UMich inspection outcomes (worn vs unworn "
           "tool, REAL) and AI4I failure modes (BENCHMARK); rises with tool wear, vibration and temperature.")
