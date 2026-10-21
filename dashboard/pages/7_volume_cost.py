import math

import pandas as pd
import plotly.express as px
import streamlit as st

from lib import data, ui

ui.setup("Data volume & cost calculator", "Move the sliders: storage, bandwidth and indicative INR/month update live")
P = data.prices()
FX = P["fx"]["usd_inr"]
red = data.result_json("edge_reduction")

with st.container(border=True):
    c = st.columns(4)
    machines = c[0].slider("Machines", 10, 1000, 100, step=10)
    sensors = c[1].slider("Sensors per machine", 1, 50, 10)
    hz = c[2].select_slider("Sampling rate (Hz)", [1, 2, 5, 10, 50, 100, 500, 1000, 2000], value=1)
    bpp = c[3].select_slider("Bytes per data point", [8, 20, 38, 219], value=20,
                             help="8 = value only; 20 = binary record; 38 = batched JSON/MQTT; 219 = one JSON message "
                                  "per value (measured in Part A)")
    c = st.columns(4)
    retention = c[0].slider("Retention (months)", 1, 60, 12)
    compression = c[1].slider("Storage compression ratio", 1.0, 10.0, 6.9, 0.1,
                              help="6.9x = Parquet+Zstd measured on real UMich CNC data")
    edge = c[2].selectbox("Edge processing", ["Raw to cloud", f"Edge features (/{red['reduction_ratio_per_second']:.0f}, "
                                              "measured on Bosch)", "Edge aggregation to 1 Hz"])
    batch_s = c[3].slider("MQTT batching interval (s)", 1, 60, 1)

pps = machines * sensors * hz
if edge.startswith("Edge features"):
    pps /= red["reduction_ratio_per_second"]
elif edge.startswith("Edge aggregation"):
    pps = machines * sensors * min(hz, 1)
bps = pps * bpp
gb_day = bps * 86400 / 1e9
stored_tb = bps * 86400 * 30 * retention / compression / 1e12
mbps = bps * 8 / 1e6

k = st.columns(5)
ui.kpi(k[0], "Data points / second", f"{pps:,.0f}")
ui.kpi(k[1], "Points / year", f"{pps * 365 * 86400 / 1e9:,.2f} bn")
ui.kpi(k[2], "Uplink bandwidth", f"{mbps:,.2f} Mbps", "sustained, before compression")
ui.kpi(k[3], "Raw volume / day", f"{gb_day:,.1f} GB")
ui.kpi(k[4], "Stored at retention", f"{stored_tb:,.2f} TB", f"after {compression:.1f}x compression")
st.write("")

# ---- indicative monthly cloud cost (USD list prices, India regions where available) -> INR
msg_bytes = bps / machines * batch_s                       # one message per machine per batch interval
msgs_month = machines * (86400 / batch_s) * 30
stored_gb_avg = stored_tb * 1000                           # steady state at full retention

az = P["azure"]
units = [(name, math.ceil(msgs_month / 30 * math.ceil(msg_bytes / 4096) / az[f"iot_hub_{name}_msgs_per_day"]),
          az[f"iot_hub_{name}_unit_month"]) for name in ("s1", "s2", "s3")]
tier, n_units, unit_price = min(units, key=lambda u: u[1] * u[2])
azure = {"Ingestion": n_units * unit_price, "Storage": stored_gb_avg * az["adls_hot_gb_month"],
         "Database + compute": 2 * az["postgres_flex_d2ds_v5_hour"] * P["hours_per_month"]}
aws = P["aws"]
aws_c = {"Ingestion": msgs_month * math.ceil(msg_bytes / 5120) / 1e6 * aws["iot_core_per_million_msgs"]
                      + msgs_month / 1e6 * (aws["iot_core_rules_per_million"] + aws["iot_core_actions_per_million"]),
         "Storage": stored_gb_avg * aws["s3_standard_gb_month"],
         "Database + compute": 2 * aws["rds_postgres_t4g_medium_hour"] * 2 * P["hours_per_month"]}
g = P["gcp"]
gcp = {"Ingestion": bps * 86400 * 30 / 2 ** 40 * g["pubsub_per_tib"] + g["mqtt_broker_vm_month"],
       "Storage": stored_gb_avg * g["gcs_standard_gb_month"],
       "Database + compute": (2 * g["cloudsql_vcpu_hour"] + 8 * g["cloudsql_gib_hour"]) * P["hours_per_month"] * 2}
rows = [{"cloud": cl, "component": comp, "inr_month": usd * FX}
        for cl, d in (("Azure (Central India)", azure), ("AWS (Mumbai)", aws_c), ("GCP (Mumbai)", gcp))
        for comp, usd in d.items()]
df = pd.DataFrame(rows)
left, right = st.columns([1.4, 1])
with left:
    fig = px.bar(df, x="cloud", y="inr_month", color="component", text_auto=",.0f",
                 title=f"Indicative cloud cost, INR per month (1 USD = ₹{FX:.2f}, {P['fx']['date']})",
                 color_discrete_sequence=ui.SERIES)
    fig.update_yaxes(title="INR / month", tickformat=",.0f")
    fig.update_xaxes(title=None)
    st.plotly_chart(fig, use_container_width=True)
with right:
    tot = df.groupby("cloud").inr_month.sum().rename("INR / month").to_frame()
    tot["INR / year"] = tot["INR / month"] * 12
    st.dataframe(tot.style.format("₹{:,.0f}"), use_container_width=True)
    st.caption(f"Azure IoT Hub: {n_units} x {tier.upper()} unit(s); message ≈ {msg_bytes / 1024:,.1f} KB "
               f"({math.ceil(msg_bytes / 4096)} x 4 KB meter). AWS IoT Core metered per 5 KB. GCP has no managed "
               "IoT service: Pub/Sub + a self-managed MQTT broker VM.")
st.info("Indicative only: public list prices accessed 2026-10-21 (docs/sources.md, data/reference/cloud_prices.json); "
        "excludes networking, support plans, reservations, taxes and edge hardware. Full model: docs/cost_model.md.")
