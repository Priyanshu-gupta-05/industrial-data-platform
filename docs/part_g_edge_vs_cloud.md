# Part G: Edge vs cloud decision

Diagram: `diagrams/06_edge_vs_cloud.png`. Numbers come from this project's measurements (Part A, the MQTT demo and the cost model).

## G.1 Measured evidence used below

| Quantity | Value | Source |
|---|---|---|
| Raw vibration per machine (2 kHz × 3 axes, float32) | 24,000 B/s | Part A, Bosch data |
| Edge features per machine (42 values/s) | 168 B/s, a **143× reduction** (120× measured over all 24.8 h of data) | `edge_reduction.json` |
| Fleet uplink, raw vibration vs features | **19.2 Mbps → 0.13 Mbps** | `edge_reduction.json` |
| Fleet storage per year, raw vibration vs features | **75.7 TB → 0.53 TB** | `edge_reduction.json` |
| Cloud bill, raw 2 kHz vs edge features (Azure, per month) | ₹3,94,487 → ₹80,085, a **₹3.14 lakh/month** saving | `cost_model.md` |
| Cloud bill, one message per reading vs edge batching (AWS / Azure) | ₹29.9 lakh / ₹14.3 lakh → ₹0.43 lakh / ₹0.80 lakh per month | `cost_model.md` |
| Store-and-forward during outage | 0 of 482 messages lost, 126-message peak backlog, 0 duplicates | `mqtt_demo_summary.json` |
| Good vs bad separability from edge features alone | ROC-AUC 0.98 (Isolation Forest trained on good only); 0.98 on a 2019 → 2021 time hold-out | `ml_bosch_anomaly.json` |

## G.2 Operation placement and justification

L = latency, R = reliability, B = bandwidth, C = cost, S = cybersecurity, Sc = scalability.

| Operation | Where | Justification |
|---|---|---|
| **High-frequency vibration processing** (2 kHz → RMS, kurtosis, band energies, dominant frequency) | **Edge** | **B:** 19.2 → 0.13 Mbps for the fleet. **C:** ₹3.1 lakh/month less on Azure. **R:** works offline. The features keep the fault signal (AUC 0.98), so little is lost by not shipping raw data. |
| **Immediate alarms and interlocks** (spindle overload, high vibration) | **Edge** | **L:** must act in under 100 ms. A cloud round-trip from Chakan to Pune adds tens to hundreds of milliseconds, and the WAN can be down. **R:** a protective function must not depend on the internet. |
| **Local machine protection** (feed hold, spindle stop) | **Edge**, inside the CNC/PLC | **S:** stays in the cell zone, with no write path from the cloud (IEC 62443 conduits). **L/R** as above. |
| **Noise filtering and data-quality checks** (range, stuck sensor, timestamp sanity) | **Edge** | **B/C:** bad data never pays for ingestion or storage. **R:** quality flags are added close to the source, while context is still known. |
| **Protocol conversion** (OPC UA / FOCAS / S7 → MQTT, Unified Namespace) | **Edge** | **S:** the cloud never talks to controllers. **Sc:** every plant publishes the same topic model, so plant 4 is a configuration change. |
| **Data aggregation and batching** (one message per machine-second) | **Edge** | **C:** 35–70× lower ingestion bill than one message per reading. **B:** fewer, larger TLS packets. |
| **Store-and-forward during WAN outage** | **Edge** | **R:** 0 lost and 0 duplicates in the demo. A 7-day buffer for 40 machines is about 21 GB, sized to outlast the IoT Operations 72-h offline limit [S34]. |
| **Local HMI / plant dashboard** | **Edge** | **R:** operators keep their view during outages. **L:** live, sub-second refresh. |
| **Model inference at the edge** (Isolation Forest on 1-s features) | **Edge** | **L:** an anomaly flag within 1 s. **B:** only scores and flagged windows are sent. **R:** works offline. |
| **Historical analysis** (876,100 machine-hours, MTBF/MTTR, OEE trends) | **Cloud** | **Sc:** needs the whole fleet's history. **C:** cheap object storage (₹0.7k–1k/month for a year of data). |
| **Fleet-level analysis and benchmarking** (3 plants, 100 machines) | **Cloud** | Only the cloud sees all plants at once, for example OEE by plant and the alarm Pareto. |
| **Long-term storage** (data lake, ≥ 12 months, audit) | **Cloud** | **C:** ADLS ≈ ₹1.9/GB-month. **R:** geo-redundant pair (Pune ↔ Chennai). Edge disks are a buffer, not an archive. |
| **AI/ML model development and retraining** | **Cloud** | Needs history, labels and GPU/CPU on demand (Azure ML). **Sc:** one model serves many machines. Example: the cross-machine Bosch test (M01 → M03) needs fleet data. |
| **OTA model and configuration updates** | **Cloud → edge** | **Sc:** one release pipeline for six gateways. **S:** signed images, pulled by the gateway (outbound connection only) [S34]. |
| **Management dashboards** (OEE, quality, alarms, PdM risk) | **Cloud** | Users are off the shop floor; Entra ID access control; Power BI / Streamlit. |
| **ERP / MES / SAP integration** | **Cloud** | Enterprise systems sit in Level 4/5. Integrating once in the cloud avoids three plant-level integrations. |
| **Digital twin and what-if simulation** | **Cloud** | Compute-heavy, fleet-wide, not time-critical. |
| **Security monitoring (SIEM)** | **Cloud**, with OT sensors at the edge | Defender for IoT sensors watch the OT network locally (passive); alerts are correlated centrally in Sentinel. |

## G.3 Rule of thumb that falls out of the numbers

1. **If it must happen in under 1 s, or must keep working without the internet, it belongs at the edge.** That covers protection, alarms, HMI and buffering.
2. **If it reduces data by more than 10× without losing the signal, do it at the edge.** Feature extraction (143×) and batching (35–70× cost) both qualify.
3. **If it needs more than one machine's or one plant's history, or a human outside the shop floor, it belongs in the cloud.** That covers training, fleet benchmarking, management dashboards and ERP.
4. **Keep the raw high-frequency data for a short time at the edge** (for example a 7-day ring buffer), and upload raw windows only on demand around detected anomalies. Engineers can still inspect a fault waveform, and the 75.7 TB/year of raw data never has to be stored.
