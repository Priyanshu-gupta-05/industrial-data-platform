import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from lib import data, ui

ui.setup("Predictive maintenance", "Model risk scores per machine (component failure within 24 h) and model scorecards")
risk = data.risk_scores()
m = data.master()["machine"]
ev = data.events()
f = ui.get_filters()
risk = risk[risk.machine_id.isin(m[m.plant_id.isin(f["plants"])].machine_id)]

times = sorted(risk.ts.dt.floor("D").unique())
as_of = st.select_slider("As of (test period, Sep-Dec 2025)", options=times, value=times[-1],
                         format_func=lambda t: pd.Timestamp(t).strftime("%d %b %Y"))
window = risk[(risk.ts <= as_of) & (risk.ts > as_of - pd.Timedelta(hours=24))]
cur = (window.groupby("machine_id").risk.max().rename("risk_24h").reset_index()
             .merge(m[["machine_id", "machine_code", "plant_code", "machine_type"]], on="machine_id")
             .sort_values("risk_24h", ascending=False))
az = data.result_json("ml_azure_failure")["test_metrics"]
thr = az["threshold"]

c = st.columns(4)
ui.kpi(c[0], "Machines above alert threshold", f"{(cur.risk_24h >= thr).sum()}", f"threshold {thr:.2f}")
ui.kpi(c[1], "Highest risk", cur.machine_code.iloc[0], f"{cur.risk_24h.iloc[0]:.0%}")
ui.kpi(c[2], "Test ROC-AUC / PR-AUC", f"{az['roc_auc']:.3f} / {az['pr_auc']:.3f}", "simulated benchmark")
ui.kpi(c[3], "Failures caught (test)", f"{az['failures_with_alert_in_prior_24h']} / {az['failures_in_test']}",
       "alert in the 24 h before")
st.write("")

left, right = st.columns([1, 1.3])
with left:
    top = cur.head(20).copy()
    top["band"] = pd.cut(top.risk_24h, [-0.01, 0.2, thr, 1.01], labels=["low", "watch", "alert"])
    fig = px.bar(top, x="risk_24h", y="machine_code", orientation="h", color="band",
                 color_discrete_map={"low": ui.STATUS["good"], "watch": ui.STATUS["warning"], "alert": ui.STATUS["critical"]},
                 title="Top-20 machines by max risk in last 24 h", text_auto=".0%")
    fig.update_yaxes(categoryorder="total ascending", title=None)
    fig.update_xaxes(tickformat=".0%", range=[0, 1.05], title=None)
    fig.update_layout(height=560)
    ui.chart(fig)
with right:
    mid = st.selectbox("Machine", cur.machine_id, format_func=lambda i: m.set_index("machine_id").loc[i, "machine_code"])
    r = risk[risk.machine_id == mid]
    fails = ev[(ev.machine_id == mid) & (ev.event_type == "FAILURE") & (ev.ts >= r.ts.min())]
    fig = go.Figure(go.Scattergl(x=r.ts, y=r.risk, mode="lines", line=dict(color=ui.SERIES[0], width=1), name="risk"))
    for t in fails.ts:
        fig.add_vline(x=t, line=dict(color=ui.STATUS["critical"], dash="dash", width=1.2))
    fig.add_hline(y=thr, line=dict(color="#52514e", dash="dot", width=1))
    fig.update_layout(title="Hourly risk vs actual failures (red dashed), alert threshold (dotted)", height=500,
                      yaxis=dict(tickformat=".0%", range=[0, 1.02]), showlegend=False)
    ui.chart(fig)

st.subheader("Model scorecards")
b = data.result_json("ml_bosch_anomaly")
u = data.result_json("ml_umich_toolwear")
a4 = data.result_json("ml_ai4i_failure_modes")["metrics"]
bi = data.result_json("business_impact")
cards = pd.DataFrame([
    {"Model": "Vibration anomaly (Isolation Forest, good-only)", "Data": "Bosch (REAL)",
     "Validation": "held-out good + all bad", "ROC-AUC": b["isolation_forest_good_only"]["roc_auc"],
     "PR-AUC": b["isolation_forest_good_only"]["pr_auc"]},
    {"Model": "Vibration anomaly (Random Forest)", "Data": "Bosch (REAL)", "Validation": "train 2019 -> test 2021",
     "ROC-AUC": b["temporal_2019_to_2021"][0]["roc_auc"], "PR-AUC": b["temporal_2019_to_2021"][0]["pr_auc"]},
    {"Model": "Failed visual inspection", "Data": "UMich (REAL)", "Validation": "leave-one-experiment-out",
     "ROC-AUC": u["failed_inspection"]["experiments"]["roc_auc"], "PR-AUC": u["failed_inspection"]["windows"]["pr_auc"]},
    {"Model": "Worn vs unworn tool", "Data": "UMich (REAL)", "Validation": "leave-one-experiment-out",
     "ROC-AUC": u["worn"]["experiments"]["roc_auc"], "PR-AUC": u["worn"]["windows"]["pr_auc"]},
    {"Model": "Failure within 24 h", "Data": "Azure PdM (BENCHMARK)", "Validation": "time split Jan-Aug / Sep-Dec",
     "ROC-AUC": az["roc_auc"], "PR-AUC": az["pr_auc"]},
    *[{"Model": f"Failure mode {k}", "Data": "AI4I (BENCHMARK)", "Validation": "stratified 5-fold",
       "ROC-AUC": v["base + physics features"]["roc_auc"], "PR-AUC": v["base + physics features"]["pr_auc"]}
      for k, v in a4.items()],
])
st.dataframe(cards.style.format({"ROC-AUC": "{:.3f}", "PR-AUC": "{:.3f}"}), hide_index=True, width="stretch")
c = st.columns(3)
ui.kpi(c[0], "Indicative net benefit / year", f"₹{bi['total_net_saving_inr_per_year'] / 1e7:,.2f} crore",
       "PdM + wear-based tool change")
ui.kpi(c[1], "Downtime avoided", f"{bi['predictive_maintenance']['downtime_hours_saved']:,.0f} h / year",
       "60 % real-world recall assumed")
ui.kpi(c[2], "Reject rate with tool policy", f"{bi['tool_change_policy']['reject_rate_current_pct']:.2f}% -> "
       f"{bi['tool_change_policy']['reject_rate_policy_pct']:.2f}%", "tool change at 150 min wear")
st.caption("Azure PdM is a simulated benchmark with strong injected precursors; real-fleet accuracy will be lower. "
           "UMich worn-tool detection does not generalise across experiments (n = 18) - reported honestly. "
           "INR values are assumptions (docs/results/business_assumptions.csv).")
