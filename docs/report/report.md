<div class="title-page" markdown="1">
<h1>Selecting Cloud and Data Infrastructure for a Smart Factory</h1>
<div class="sub">Technical report: data volume, cloud comparison, decision matrix, PostgreSQL design, Azure reference architecture, edge-versus-cloud analysis and analytics for a 100-machine CNC fleet</div>
<div class="band"></div>
<div class="meta">
<b>Author:</b> Tirthanker Singh<br/>
<b>Repository:</b> https://github.com/TirthankerSingh/industrial-data-platform<br/>
<b>Date:</b> 26 October 2026<br/>
<b>Recommended platform:</b> Microsoft Azure (Central India), edge-first design
</div>
</div>

<div class="toc" markdown="1">
<h2 style="break-before: avoid;">Contents</h2>

[TOC]
</div>

## Executive summary {: .newpage}

A manufacturer runs **100 CNC machines in three plants**. In this report the scenario is an automotive Tier-1 supplier at Chakan (Pune), Oragadam (Chennai) and Manesar (Gurugram). The report designs and justifies the cloud-data architecture that will carry its sensor, production and machine-control data.

**What makes this report evidence-based.**
- Every quantitative claim rests on **four public datasets** that were actually downloaded and processed:
  - two **real** industrial datasets: Bosch CNC vibration, with 1,702 machining operations at 2 kHz [D1], and the UMich CNC mill, with 18 experiments [D2];
  - two **benchmarks**: Microsoft Azure Predictive Maintenance, simulated [D3], and AI4I 2020, synthetic [D4].
- On top of these were built:
  - a PostgreSQL database with 876,100 machine-hours;
  - an MQTT edge gateway with store-and-forward;
  - four machine-learning models;
  - an 8-page dashboard.

<div class="kpis">
<div><b>31.5 bn</b><span>values/year, 1 Hz fleet</span></div>
<div><b>143×</b><span>edge feature reduction (real data)</span></div>
<div><b>4.22 / 5</b><span>Azure weighted score</span></div>
<div><b>0 lost</b><span>of 482 MQTT messages in outages</span></div>
</div>

**Key results.**
1. **Data volume.**
   - The 1 Hz fleet produces 1,000 values/s, which is **31.536 billion a year**.
   - One 100 Hz vibration sensor adds 3.15 billion a year; fitting one to every machine adds 315 billion, ten times the whole 1 Hz fleet.
   - At the real Bosch rate (2 kHz × 3 axes), raw vibration would need 96 Mbps and 378 TB a year.
   - Lossless compression achieves only 5× on vibration. Edge feature extraction achieves **143×** while keeping the fault signal (ROC-AUC 0.98).
2. **Cloud comparison.** Official sources were checked on 2026-10-21.
   - Several IIoT services are retired or in maintenance: GCP IoT Core, Azure Time Series Insights, AWS IoT Analytics and AWS IoT Events [S58][S28][S1][S3].
   - Azure offers the most complete current shop-floor-to-dashboard chain. AWS has the best-documented edge buffering. GCP has no first-party IIoT layer.
3. **Decision matrix.** Across 10 weighted criteria the scores are **Azure 4.22**, AWS 3.92 and GCP 3.57.
   - Azure wins all ±5-point weight shifts and 88.7% of 10,000 Monte-Carlo runs.
   - AWS overtakes only when cost carries at least 35% of the weight.
4. **Cost.**
   - An edge-batched design costs ₹33k–80k per month.
   - Sending one MQTT message per reading would cost ₹14–30 lakh per month, so **edge batching is the largest cost lever**.
5. **Recommendation: Microsoft Azure, Central India, with an edge-first design.**
   - Each plant runs IoT Operations, reading OPC UA from the Fanuc and Siemens controllers, plus a durable 7-day outbox.
   - Data flows through IoT Hub / Event Hubs into Fabric Eventhouse and ADLS, then PostgreSQL Flexible Server, Azure ML and Power BI.
   - The scenario reasons are brownfield OPC UA, the Microsoft tooling already used in the plants, a Pune region next to Chakan, and an edge design that removes Azure's offline-time and cost weaknesses.

## 1. Introduction and industrial scenario {: .newpage}

**The task.** The manufacturer needs infrastructure for monitoring, analytics, storage, dashboards, AI/ML and remote access across 100 CNC machines. The assignment asks for seven things:
- the data volume, and why high-frequency data needs edge processing (Part A);
- a 13-criterion cloud comparison (Part B);
- a weighted decision matrix and recommendation (Part C);
- a SQL database with eight analytical queries (Part D);
- a GitHub repository (Part E);
- a mapped cloud architecture (Part F);
- an edge-versus-cloud analysis (Part G).

**The scenario.** To make the recommendation concrete, this report uses an illustrative automotive Tier-1 supplier in India (Table 1). The fleet uses Fanuc 0i/31i and Siemens SINUMERIK 828D/840D sl controllers. Each machine carries 10 sensor streams at 1 Hz:
- spindle temperature, coolant temperature, spindle vibration (RMS) and spindle RPM;
- spindle motor current, feed-axis load, hydraulic pressure and coolant flow;
- power consumption and door/cycle status.

It also carries one spindle accelerometer: 100 Hz in the assignment calculation, and 2 kHz × 3 axes in the real Bosch data. The plants run 24×7 on three shifts (A 06–14, B 14–22, C 22–06).

Table: Plants, machines and part families (scenario assumptions; data/reference/)

| Plant | Shop floor | Machine IDs | Machine types | Part families (nominal cycle time) | Real data anchoring it |
|---|---|---|---|---|---|
| P1 Chakan, Pune | Powertrain machining | 1–40 | 24 HMC, 16 VMC | Engine block (14 min), cylinder head (7.5 min), crankcase (11 min) | Bosch vibration [D1] |
| P2 Oragadam, Chennai | Transmission & driveline | 41–75 | 15 turning, 10 hobbing, 10 grinding | Gear shaft (3.5), helical gear (4.5), differential housing (6), finish-ground shaft (2.5) | AI4I temperature/torque/wear [D4] |
| P3 Manesar, Gurugram | Chassis & brakes | 76–100 | 17 turning, 8 VMC | Brake disc (2), steering knuckle (5), wheel hub (3) | UMich spindle current [D2] |

**Nominal spindle speed ranges** (scenario assumptions):

| Machine type | RPM range |
|---|---|
| HMC | 2,000–8,000 |
| VMC | 3,000–10,000 |
| Turning | 800–3,500 |
| Hobbing | 300–1,500 |
| Grinding | 1,500–4,500 |

Rated spindle current follows from rated power: I = P / (√3 · 415 V · 0.85).

## 2. Datasets and provenance

Table: Datasets used, their nature and licence

| Dataset | Nature | Size used | Licence | Role |
|---|---|---|---|---|
| Bosch CNC Machining [D1] | **REAL** production plant | 1,702 files, 3 machines, 2 kHz × 3 axes, 24.8 h, 70 bad | CC-BY-4.0 | Edge features, compression, anomaly models, vibration scale |
| UMich SMART CNC Mill [D2] | **REAL** CNC machine | 18 experiments, 25,286 rows × 48 signals at 100 ms | as published | Current calibration, reject model, tool-wear models, MQTT replay |
| Azure PdM [D3] | **BENCHMARK**, simulated by Microsoft | 100 machines × 8,761 h, errors, maintenance, failures | as published | Fleet backbone, 24-h failure prediction |
| AI4I 2020 [D4] | **BENCHMARK**, synthetic | 10,000 rows, 5 failure modes | CC-BY-4.0 | Temperature model, failure-mode classifier |

**How the fleet table is built.**
- The PostgreSQL fact table uses the Azure telemetry as its **backbone**. Machine IDs 1–100 equal the Azure machineIDs, so every row is traceable.
- All other values are **DERIVED** with documented rules; everything is in `data/DATA_PROVENANCE.md`.
- The raw source tables are loaded unchanged into the `raw` schema, so each derived value can be traced back.

**Derivation rules.**
- **Timestamps:** shifted by 3,654 days (522 weeks, so weekdays are preserved) to 2 Jan 2025 – 2 Jan 2026 IST.
- **RPM:** a linear rescale of `rotate` into each machine type's range.
- **Spindle current:** `volt` is mapped onto the real UMich cutting-load band (22/31/41% of peak current).
- **Vibration (mm/s RMS):** an affine map. The fleet median goes to 1.8 mm/s (centre of ISO 10816-3 zone B [D5]); the pre-failure level goes to the Bosch-measured fault ratio (90th percentile 1.68×).
- **Temperature:** an AI4I regression with plant ambient as input (cross-validated R² 0.77).
- **Alarms:** each Azure event type is named after the signal that shifts in the 24 h before it.
- **Status:** derived from alarms, maintenance, holidays and low-load periods.
- **Production:** running minutes ÷ cycle time.
- **Rejects:** a logistic model using UMich's worn-tool odds ratio of 13 and AI4I coefficients, solved for a 1.5% fleet rate.

![Calibration: AI4I temperature model (left) and data-driven alarm naming (right), where each Azure event is named after the telemetry signal that moves in the 24 h before it](docs/figures/calib_temperature_and_alarm_mapping.png)

![End-to-end data pipeline: four datasets, numbered scripts, outputs {tall}](diagrams/05_data_pipeline.png)

## 3. Part A: Industrial data volume

{{include:docs/part_a_data_volume.md|from=## A.1|to=## A.6|shift=1}}


![Fleet uplink bandwidth by payload encoding; the dashed line is a typical 100 Mbps plant leased line](docs/figures/part_a_bandwidth_by_encoding.png)

![Measured file size and compression ratio vs CSV for real UMich, real Bosch and benchmark Azure data](docs/figures/part_a_measured_compression.png)

![Raw 2 kHz Z-axis vibration vs the 1-second RMS and kurtosis features computed at the edge (same machine and operation)](docs/figures/edge_waveform_vs_features.png)

![Spectrogram of a good and a bad operation: the bad operation shows a strong ~250 Hz line and lacks the normal spindle ramp-up](docs/figures/edge_spectrogram_good_vs_bad.png)

![Good vs bad operations in feature space: PCA of file-level features, t-SNE of 1-s windows, and the per-machine domain shift](docs/figures/edge_feature_space_pca_tsne.png)


![Measured data reduction from edge feature extraction](docs/figures/edge_data_reduction.png)

{{include:docs/part_a_data_volume.md|from=## A.6|shift=1}}

## 4. Part B: Cloud platform comparison

{{include:docs/part_b_cloud_comparison.md|from=**Scenario.**|to=## B.1|shift=1}}

{{include:docs/part_b_cloud_comparison.md|from=## B.1|shift=1}}

## 5. Part C: Weighted decision matrix and recommendation

{{include:docs/part_c_decision.md|from=## C.1|to=## C.4|shift=1}}

![Weighted decision matrix: contribution of each criterion to each cloud's total](docs/figures/part_c_weighted_scores.png)

![Sensitivity: alternative weight profiles (left) and 10,000-run Monte-Carlo distribution of Azure's margin (right)](docs/figures/part_c_sensitivity.png)

### 5.1 Indicative INR cost model

{{include:docs/cost_model.md|from=## Assumptions|shift=2}}

![Indicative monthly cloud cost by data strategy (log scale)](docs/figures/part_c_cost_model.png)

{{include:docs/part_c_decision.md|from=## C.4|shift=1}}

## 6. Part D: PostgreSQL database design, queries and results

**Platform and layout.**
- The database runs on PostgreSQL 16 (any 16/17 works).
- Three schemas separate the concerns:
  - `raw`: the four source datasets as published (921,172 rows);
  - `core`: master data and the hourly fact table;
  - `analytics`: views and materialized views for the dashboard.
- The full DDL is in `sql/01_schema.sql`.

**Design choices.**
- **Keys:** primary key `(machine_id, ts)`, which also serves as the main access index.
- **Constraints:** foreign keys to the plant, machine, part-family and alarm masters; CHECK constraints for non-negative counts, `reject_count ≤ production_count`, running minutes 0–60, and alarm-flag consistency.
- **Status:** an ENUM `machine_status_t` (RUNNING / IDLE / ALARM / MAINTENANCE / OFF).
- **Additional indexes:** `ts`, `(plant_id, ts)`, and a partial index on alarm rows (0.5% of rows).
- **Time zone:** the database is set to IST.
- **Required column names:** the view `analytics.v_machine_data_required` exposes `Machine_ID`, `Timestamp`, `Temperature`, `Vibration`, `RPM`, `Current`, `Production_Count`, `Machine_Status`, `Alarm` and `Reject_Count`.
- **Production path:** a TimescaleDB setup (hypertable, continuous aggregates, compression) is documented, commented out, in the schema.

**Loading.** COPY loaded the 876,100 fact rows at about 47,000 rows/s. The table takes 162 MB including indexes, about 185 bytes per row, compared with about 20 bytes per row in Parquet+Zstd.

![Entity-relationship diagram generated from the PostgreSQL catalog (orange: fact table; green: MQTT ingest table) {tall}](diagrams/04_er_diagram.png)

```sql
CREATE TABLE core.machine_data (
    machine_id        SMALLINT    NOT NULL REFERENCES core.machine,
    ts                TIMESTAMPTZ NOT NULL,
    plant_id          SMALLINT    NOT NULL REFERENCES core.plant,
    part_family_id    SMALLINT    NOT NULL REFERENCES core.part_family,
    temperature       REAL,  vibration REAL,  rpm REAL,  current REAL,
    production_count  INTEGER NOT NULL DEFAULT 0 CHECK (production_count >= 0),
    reject_count      INTEGER NOT NULL DEFAULT 0 CHECK (reject_count >= 0),
    machine_status    core.machine_status_t NOT NULL,
    alarm             BOOLEAN NOT NULL DEFAULT FALSE,
    alarm_code        VARCHAR(8) REFERENCES core.alarm_master,
    tool_wear_min REAL, running_minutes REAL NOT NULL CHECK (running_minutes BETWEEN 0 AND 60), ...
    PRIMARY KEY (machine_id, ts),
    CHECK (reject_count <= production_count),  CHECK (alarm = (alarm_code IS NOT NULL)));
```

### 6.1 The eight required queries

The query logic, all from `sql/03_required_queries.sql`:

| # | Question | Logic |
|---|---|---|
| Q1 | Average temperature per machine | Average over hours with running minutes > 0 |
| Q2 | Machine with the most parts | `SUM(production_count)` with `FETCH FIRST 1 ROWS WITH TIES` |
| Q3 | Highest average vibration | Average while running, with its ISO 10816-3 zone |
| Q4 | Alarm count per machine | Alarm events, alarm hours, and critical (failure) hours |
| Q5 | Parts on a selected day | The date is a parameter; the IST day uses a half-open range `[d, d+1)` so the index on `ts` stays usable |
| Q6 | Longest operating duration | Gaps-and-islands: `ts − row_number() × 1 h` is constant within a continuous RUNNING run |
| Q7 | Average RPM while running | RUNNING hours only |
| Q8 | Highest rejection rate | `SUM(reject_count) / SUM(production_count)`, a ratio of sums, not an average of hourly ratios |

{{csv:sql/results/q1_avg_temperature_per_machine.csv|Q1 Average temperature per machine (running hours), highest first|max_rows=5}}

{{csv:sql/results/q2_machine_most_parts.csv|Q2 Machine that produced the most parts}}

{{csv:sql/results/q3_highest_avg_vibration.csv|Q3 Highest average vibration while running|max_rows=5}}

{{csv:sql/results/q4_alarm_count_per_machine.csv|Q4 Alarm count per machine, most first|max_rows=5}}

{{csv:sql/results/q5_parts_on_selected_day.csv|Q5 Parts produced on the selected day (16 Jun 2025, IST)}}

{{csv:sql/results/q6_longest_operating_duration.csv|Q6 Longest continuous operating duration|max_rows=5}}

{{csv:sql/results/q7_avg_rpm_while_running.csv|Q7 Average RPM while running|max_rows=5}}

{{csv:sql/results/q8_highest_rejection_rate.csv|Q8 Highest rejection rate|max_rows=5}}

**Interpretation.**
- **Q2 and Q8 follow cycle time.** Brake-disc turning centres (2-min cycle) produce the most parts. Finish grinders, which run at high utilisation with tool wear, have the highest reject rates, about 1.9–2.0%.
- **Q3 sits in ISO zone B.** Fleet-average vibration is in zone B (1.4–2.8 mm/s), so the useful signal is in the excursions, not the averages (query A7 below).
- **Q6 shows one exceptionally long run.** P1-HMC-18 ran 209 h (8.7 days) without interruption.

### 6.2 Advanced queries (bonus)

`sql/04_advanced_queries.sql` adds:
- OEE (availability × performance × quality) per machine and per plant-month;
- MTBF and MTTR, from failure events and the maintenance islands that follow them;
- shift-wise production;
- an alarm Pareto with cumulative share;
- daily trends with 7-day moving averages, `LAG` and `RANK`;
- vibration anomalies against a rolling 168-hour per-machine baseline, linked to failures in the following 48 h;
- reject rate by tool-wear band;
- dashboard materialized views.

{{csv:sql/results/a1_oee_per_machine.csv|A1 OEE per machine, lowest first|max_rows=5}}

{{csv:sql/results/a3_mtbf_mttr_per_machine.csv|A3 MTBF and MTTR, least reliable first|max_rows=5}}

{{csv:sql/results/a5_alarm_pareto.csv|A5 Alarm Pareto with cumulative share}}

{{csv:sql/results/a7_vibration_anomalies.csv|A7 Vibration anomalies (z > 3 vs rolling 7-day baseline) and how often a failure followed within 48 h|max_rows=5}}

{{csv:sql/results/a8_tool_wear_vs_quality.csv|A8 Reject rate by tool-wear band}}

## 7. Part F: Industrial cloud architecture on Azure

![Required linear architecture with each block mapped to an Azure service (middle) and to what this project built (right) {tall}](diagrams/01_linear_flow.png)

![Azure reference architecture: plant edge (IoT Operations on Arc-enabled K3s) to Azure Central India {tall}](diagrams/02_reference_architecture.png)

{{include:docs/part_f_architecture.md|from=## F.1|to=## F.3|shift=1}}

{{include:docs/part_f_architecture.md|from=## F.3|shift=1}}

![Security zoning: Purdue levels and IEC 62443 zones and conduits [D6]](diagrams/03_security_zones.png)

![MQTT store-and-forward demonstration with real data: subscriber outage and WAN outage, 0 messages lost](docs/figures/edge_mqtt_store_and_forward.png)

## 8. Part G: Edge vs cloud decision

![Edge vs cloud split with measured data rates](diagrams/06_edge_vs_cloud.png)

{{include:docs/part_g_edge_vs_cloud.md|from=## G.1|shift=1}}

## 9. Analytics and machine-learning results

**Validation approach.** All models use evaluation splits that prevent leakage:
- held-out operations for Bosch;
- a 2019 → 2021 time hold-out for Bosch;
- leave-one-experiment-out for UMich;
- a time-based split with a 24-hour gap for Azure;
- stratified 5-fold cross-validation for AI4I.

Where a score looks too good, the cause was investigated and reported.

Table: Model scorecard (docs/results/ml_*.json)

| Model | Data | Validation | ROC-AUC | PR-AUC | Note |
|---|---|---|---:|---:|---|
| Vibration anomaly, Isolation Forest trained on good only | Bosch (REAL) | held-out good + all bad | 0.978 | 0.800 | deployable at the edge: needs no fault examples |
| Vibration anomaly, Random Forest | Bosch (REAL) | stratified 5-fold | 0.995 | 0.986 | precision 0.99, recall 0.97 |
| Same, temporal hold-out | Bosch (REAL) | train 2019 → test 2021 | 0.984 | 0.930 | rules out recording-period leakage (39 of 70 bad files are from Feb 2019) |
| Same, cross-machine | Bosch (REAL) | train M01 → test M02 / M03 | 1.00 / 0.91 | 0.997 / 0.89 | M03 is the hardest domain shift, as the dataset paper notes [D1] |
| Worn vs unworn tool | UMich (REAL) | leave-one-experiment-out | 0.36 | 0.44 | **does not generalise** with 18 experiments; a leaky random split gives 0.72 |
| Failed visual inspection | UMich (REAL) | leave-one-experiment-out | 0.75 | 0.30 | indicative, n = 14 |
| Component failure within 24 h | Azure PdM (BENCHMARK) | time split Jan–Aug / Sep–Dec, 24-h gap | 1.000 | 0.999 | 225/225 failures alerted; ablation shows simulated precursors, so a real fleet would score lower |
| Failure modes HDF / PWF / OSF / TWF | AI4I (BENCHMARK) | stratified 5-fold | 1.00 / 1.00 / 1.00 / 0.93 | 0.99 / 1.00 / 1.00 / 0.09 | physics features (ΔT, power, wear × torque) recover the generating rules; TWF is random by design |

![Bosch vibration anomaly detection: ROC, precision-recall, confusion matrix and feature importance](docs/figures/ml_bosch_roc_pr_confusion.png)

![Cross-machine generalisation on Bosch data: train on M01, test on M02 and M03](docs/figures/ml_bosch_cross_machine.png)

![UMich tool wear and inspection outcome, leave-one-experiment-out, including the leaky random split for comparison](docs/figures/ml_umich_toolwear.png)

![24-hour failure prediction on the Azure PdM fleet (time-based split)](docs/figures/ml_azure_failure_24h.png)

![Hourly risk score vs actual failures for the machine with the most test-period failures](docs/figures/ml_azure_risk_timeline.png)

![AI4I failure modes: the effect of physics features and the share of mean |SHAP| per feature](docs/figures/ml_ai4i_failure_modes.png)

**Business impact (indicative).** The calculation uses the model results and fleet volumes together with stated INR assumptions (`docs/results/business_assumptions.csv`):
- **Downtime cost:** ₹5,000 per machine-hour.
- **Repair premium:** ₹25,000 per unplanned repair.
- **Real-world model performance:** 60% recall and 50% precision.
- **Tool policy:** a wear-based tool change at 150 min, with ₹3,500 per tool.
- **Scrap cost:** 60% of the part value.

Table: Indicative annual business impact for the fleet

| Lever | Volume effect | Net ₹ per year |
|---|---|---:|
| Predictive maintenance | 446 of 743 failures caught; 2,117 machine-hours of downtime avoided | ≈ ₹2.06 crore |
| Wear-based tool change | Reject rate 1.50% → 0.92%, net of extra tools | ≈ ₹3.78 crore |
| **Total** | | **≈ ₹5.84 crore** |

The whole cloud bill (₹4–10 lakh per year) is about 1–2% of this benefit.

![Indicative annual impact for the 100-machine fleet (INR lakh)](docs/figures/ml_business_impact_inr.png)

## 10. Dashboard walkthrough

**Where it runs.**
- **Locally**, the Streamlit dashboard (`dashboard/`) reads PostgreSQL.
- **Hosted** on Streamlit Community Cloud, it reads the bundled Parquet snapshot, so it cannot fail if a database is unavailable on demo day.
- Both modes run the same analysis code. Sidebar filters (plant, date range) apply to every page.

The eight pages are:
1. **Fleet overview:** KPIs (machines running, OEE, parts on the last full day, reject rate, alarms in the last 24 h), OEE components by plant, status mix, daily output.
2. **Plant drill-down:** a shop-floor heatmap (daily running share, or hour-by-hour status), output by part family and shift, and an OEE league table.
3. **Machine health:** vibration with ISO 10816-3 zone bands, temperature, current, tool wear, alarm markers, and a 0–100 health score.
4. **Alarms:** a Pareto with cumulative share, an alarm timeline, alarms per day, and MTBF versus MTTR.
5. **Quality:** reject rate by part family and by machine, and the link to tool wear.
6. **Edge demo:** the real 2 kHz Bosch waveform, 1-s features computed live, a spectrogram, reduction counters, and the MQTT results.
7. **Data volume & cost calculator:** sliders for machines, sensors, Hz, bytes, retention, compression, edge mode and batching. It shows bandwidth, storage and indicative INR per month for each cloud, using the same price file as Part C.
8. **Predictive maintenance:** a risk ranking over time, a per-machine risk timeline against failures, model scorecards, and the INR impact.

[SCREENSHOT: Fleet overview page (local PostgreSQL mode)]

[SCREENSHOT: Machine health page with ISO vibration zones]

[SCREENSHOT: Edge demo page - raw waveform vs features]

[SCREENSHOT: Data volume and cost calculator]

[SCREENSHOT: Predictive maintenance page]

[SCREENSHOT: Hosted dashboard on Streamlit Community Cloud]

## 11. Limitations and honest discussion

- **The fleet table is derived, not measured.**
  - Its backbone is a *simulated* Microsoft benchmark. Every derived column follows documented, calibrated rules, but absolute values (reject counts, temperatures, current) are illustrative.
  - The real-data results are the Bosch and UMich analyses (edge features, compression, anomaly and tool-wear models).
  - Patterns found in the fleet table (OEE, MTBF, Pareto) demonstrate the method, not a real plant's performance.
- **Temperature.** AI4I's process temperature hardly depends on load (only air temperature matters), so fleet temperature varies mainly with plant ambient and season. No load-heating term was invented.
- **Vibration scaling.** The Bosch accelerometer data is in raw units, so only the *ratio* between bad and good operations was transferred to mm/s. Bosch faults are mostly spectral: the median bad/good RMS ratio is just 1.23.
- **Some scores are too good to generalise.**
  - The Azure 24-h failure model is near-perfect because the simulation injects clear precursors.
  - The UMich worn-tool model fails across experiments; 18 experiments are too few.
  - Both results are reported, not hidden.
- **Costs are indicative.**
  - They use list prices on one date, with no networking, support, reservations, GST or labour.
  - GCP India prices were not retrievable, and the GCP partner edge licence is excluded.
  - The Azure IoT Hub bypass variant is unvalidated.
- **Service-status evidence has gaps.** The Azure IoT Central retirement notice was read through a third-party mirror. A few India-availability facts are marked uncertain in `docs/cloud_research_notes.md`.
- **Scores are judgements.** The scores in the decision matrix are evidence-based but still judgements. The sensitivity analysis bounds how much they matter.

## 12. Conclusion and future work

**The architecture.** The factory should adopt an **edge-first architecture on Microsoft Azure (Central India)**:
- IoT Operations reads OPC UA at each plant and turns 2 kHz vibration into 42 features per second, a 143× reduction measured on real data.
- Data is batched one message per machine-second and buffered for 7 days.
- Only about 0.7 Mbps for the whole fleet goes to the cloud. There it feeds Eventhouse and ADLS, PostgreSQL, Azure ML and Power BI.

**Why it holds.**
- The decision is robust to weighting: Azure wins 88.7% of Monte-Carlo runs.
- It follows from the scenario: brownfield OPC UA, Microsoft tooling already in the plants, a Pune region next to Chakan, and an edge design that removes Azure's weaknesses.

**Future work.**
1. A **pilot at Chakan** on one HMC line, to validate the OPC UA licences, the IoT Operations footprint and the IoT Hub bypass.
2. **OEE rollout** with real cycle signals from the controllers, replacing derived production counts.
3. **MLOps:** a model registry, a drift monitor for the cross-machine shift, and OTA deployment of the Isolation Forest to the gateways.
4. A **digital twin** of each line in Fabric, for what-if scheduling.
5. Collecting **real labelled failures** in the plants, to retrain the PdM model away from the benchmark.

## References {: .newpage}

{{REFERENCES}}

## Appendix A: Full required-query outputs {: .newpage}

<div class="compact" markdown="1">

{{csv:docs/results/appendix_per_machine.csv|Full per-machine outputs of Q1 (avg temperature), Q4 (alarms), Q7 (avg RPM running) and Q8 (rejection rate)|max_rows=100}}

</div>

{{csv:sql/results/q8_highest_rejection_rate.csv|Q8 top-10 output|max_rows=10}}

{{csv:sql/results/a4_shift_production.csv|A4 Shift-wise production}}

## Appendix B: Assumptions

{{csv:docs/results/business_assumptions.csv|Business-impact assumptions (INR)|max_rows=40}}

{{csv:data/reference/machine_type.csv|Machine-type assumptions}}

{{csv:data/reference/part_master.csv|Part-family assumptions}}

{{csv:data/reference/alarm_master.csv|Alarm master (illustrative mapping of benchmark events)|cols=alarm_code,alarm_name,severity,source_event,dominant_signal,dominant_z,n_events}}
