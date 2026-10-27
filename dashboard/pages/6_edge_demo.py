import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from lib import data, ui

ui.setup("Edge demo", "What the edge gateway does with REAL 2 kHz Bosch vibration: raw signal in, compact features out")
FS = 2000
s = data.bosch_sample()
red = data.result_json("edge_reduction")

c = st.columns(4)
ui.kpi(c[0], "Reduction per machine-second", f"{red['reduction_ratio_per_second']:.0f}x",
       f"{red['raw_bytes_per_second_float32']:,} B -> {red['feature_bytes_per_second_float32']} B")
ui.kpi(c[1], "Measured on full dataset", f"{red['measured_reduction_vs_raw_float32']:.0f}x",
       f"{red['files']:,} files · {red['raw_hours']:.1f} h of 2 kHz data")
ui.kpi(c[2], "Fleet uplink", f"{red['fleet_raw_mbps']:.1f} -> {red['fleet_feature_mbps']:.2f} Mbps", "100 machines")
ui.kpi(c[3], "Fleet storage / year", f"{red['fleet_raw_TB_per_year']:.1f} -> {red['fleet_feature_TB_per_year']:.2f} TB",
       "raw vs features")
st.write("")

label = st.segmented_control("Operation", ["good", "bad"], default="bad")
d = s[s.label == label]
axis = st.radio("Axis", ["acc_x", "acc_y", "acc_z"], index=2, horizontal=True)
x = d[axis].to_numpy()
n = len(x) // FS
w = x[: n * FS].reshape(n, FS)
ac = w - w.mean(axis=1, keepdims=True)
rms = np.sqrt((ac ** 2).mean(axis=1))
peak = np.abs(ac).max(axis=1)
kurt = ((ac ** 4).mean(axis=1) / np.maximum(rms ** 4, 1e-12)) - 3
spec = np.abs(np.fft.rfft(ac * np.hanning(FS), axis=1)) ** 2
freqs = np.fft.rfftfreq(FS, 1 / FS)
dom = freqs[1:][spec[:, 1:].argmax(axis=1)]
feat = pd.DataFrame({"second": np.arange(n), "RMS": rms, "peak": peak, "crest": peak / rms, "kurtosis": kurt,
                     "dominant Hz": dom})

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08, row_heights=[0.55, 0.45],
                    subplot_titles=(f"Raw {axis} at 2 kHz - {d.file.iloc[0]} ({len(x):,} samples)",
                                    "1-second RMS feature computed at the edge (10 values instead of 20,000)"))
color = ui.SERIES[7] if label == "bad" else ui.SERIES[0]
fig.add_trace(go.Scattergl(x=d.t_s, y=x, mode="lines", line=dict(width=0.6, color=color), name="raw"), row=1, col=1)
fig.add_trace(go.Bar(x=feat.second + 0.5, y=feat.RMS, marker_color=ui.SERIES[2], name="RMS", width=0.8), row=2, col=1)
fig.update_layout(height=560, showlegend=False)
fig.update_xaxes(title_text="Time (s)", row=2, col=1)
ui.chart(fig)

left, right = st.columns([1.3, 1])
with left:
    nper, hop = 256, 128
    frames = np.lib.stride_tricks.sliding_window_view(x - x.mean(), nper)[::hop]
    sp = 10 * np.log10(np.abs(np.fft.rfft(frames * np.hanning(nper), axis=1)) ** 2 + 1e-9)
    f = np.fft.rfftfreq(nper, 1 / FS)
    t = (np.arange(len(frames)) * hop + nper / 2) / FS
    fig = go.Figure(go.Heatmap(z=sp.T, x=t, y=f, colorscale=ui.SEQ_BLUE, zmin=np.percentile(sp, 5),
                               colorbar=dict(title="dB")))
    fig.update_layout(title="Spectrogram (bad operations show a strong ~250 Hz line)", height=380,
                      xaxis_title="Time (s)", yaxis_title="Frequency (Hz)")
    ui.chart(fig)
with right:
    st.markdown("**Features sent to the cloud (per second)**")
    st.dataframe(feat.style.format({"RMS": "{:.1f}", "peak": "{:.1f}", "crest": "{:.2f}", "kurtosis": "{:.2f}",
                                    "dominant Hz": "{:.0f}"}), hide_index=True, width="stretch", height=380)

st.subheader("MQTT store-and-forward test")
mq = data.result_json("mqtt_demo_summary")
c = st.columns(4)
ui.kpi(c[0], "Produced at edge", f"{mq['messages_produced']}")
ui.kpi(c[1], "Stored in PostgreSQL", f"{mq['rows_in_postgres']}")
ui.kpi(c[2], "Lost / duplicates", f"{mq['lost']} / {mq['duplicates_in_postgres']}")
ui.kpi(c[3], "Max outbox backlog", f"{mq['max_outbox_backlog']}", "during 12 s WAN outage")
st.image(str(data.FIGURES / "edge_mqtt_store_and_forward.png"), width="stretch")
st.caption("REAL data: Bosch CNC Machining dataset (Tnani et al., 2022, CC-BY-4.0), first 10 s of one good and one "
           "bad operation (M01, OP01). Features are DERIVED.")
