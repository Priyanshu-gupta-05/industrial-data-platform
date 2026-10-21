# Data Provenance

This document records **where every dataset comes from, what kind of data it is, and every rule used to derive new values from it**. It is the single reference for the honesty rule of this project:

> Each dataset is labelled **REAL**, **BENCHMARK (simulated)** or **BENCHMARK (synthetic)**. Every column produced by this project's scripts is marked **DERIVED**. Derived values are never presented as raw sensor readings.

Raw datasets are not stored in this repository (size and licence reasons). `python/00_download_datasets.py` fetches them into `../raw_datasets/` (override with the `RAW_DATA_DIR` environment variable). `python/01_verify_datasets.py` checks that they load and writes `data/reference/dataset_inventory.csv`.

## 1. Source datasets

| # | Dataset | Nature | Original source | Licence | Used for |
|---|---------|--------|-----------------|---------|----------|
| 1 | Bosch CNC Machining Dataset | **REAL** (production plant, 3 milling machines, 2019–2021) | Tnani, M.-A., Feil, M., Diepold, K., "Smart Data Collection System for Brownfield CNC Milling Machines: A New Benchmark Dataset for Data-Driven Machine Monitoring," *Procedia CIRP* 107 (2022) 131–136. https://github.com/boschresearch/CNC_Machining | CC-BY-4.0 | Part A edge feature extraction, vibration scale justification, anomaly-detection models, P1 Chakan anchoring |
| 2 | UMich SMART CNC Mill Tool Wear | **REAL** (one CNC mill, 18 machining experiments, System-level Manufacturing and Automation Research Testbed, University of Michigan) | Originally published on Kaggle as `shasun/tool-wear-detection-in-cnc-mill`; mirror used: https://github.com/flyinginte/toolwear_cncmilling | As published on Kaggle by the original authors (see source page) | Spindle current calibration, reject-probability calibration, tool-wear classifier, MQTT replay, P3 Manesar anchoring |
| 3 | Microsoft Azure Predictive Maintenance | **BENCHMARK (simulated by Microsoft)** — 100 machines, hourly, year 2015 | Microsoft Azure AI Gallery predictive-maintenance template; Kaggle `arnabbiswas1/microsoft-azure-predictive-maintenance`; mirror used: https://github.com/avidunixuser/telemetry | As published by Microsoft / Kaggle (see source page) | Backbone of the 100-machine fleet table (timestamps, telemetry variation, errors, maintenance, failures) |
| 4 | AI4I 2020 Predictive Maintenance Dataset | **BENCHMARK (synthetic, reflects real industrial patterns)** — 10,000 rows | Matzka, S., "Explainable Artificial Intelligence for Predictive Maintenance Applications," *2020 Third International Conference on Artificial Intelligence for Industries (AI4I)*, pp. 69–74. UCI Machine Learning Repository, id 601. https://doi.org/10.24432/C5HS5C | CC-BY-4.0 | Temperature model, failure-mode classifier, reject-probability calibration, P2 Oragadam anchoring |

### Verified structure (from `01_verify_datasets.py`)

- **Bosch:** `data/M01|M02|M03/OP00..OP14/good|bad/*.h5`; key `vibration_data`, float32 `(n_samples, 3)` = X/Y/Z acceleration at 2 kHz. File names encode machine, month, year and operation, e.g. `M01_Feb_2019_OP01_000.h5`.
- **UMich:** `train.csv` (18 experiments: material, feedrate, clamp_pressure, tool_condition, machining_finalized, passed_visual_inspection) and `experiment_01..18.csv` (25,286 rows × 48 columns at 100 ms; X1/Y1/Z1/S1 axis signals, M1 program/sequence/feedrate, Machining_Process).
- **Azure PdM:** `telemetry.csv` 876,100 rows (100 machines × 8,761 hours, 2015-01-01 06:00 → 2016-01-01 06:00; volt, rotate, pressure, vibration), `machines.csv` (model, age), `errors.csv` (3,919 rows, error1–5), `maint.csv` (3,286 rows), `failures.csv` (761 rows, comp1–4).
- **AI4I:** 10,000 rows; Type L/M/H; air and process temperature [K], rotational speed [rpm], torque [Nm], tool wear [min]; failure flags (Machine failure 339, TWF 46, HDF 115, PWF 95, OSF 98, RNF 19).

## 2. Scenario reference tables (SCENARIO ASSUMPTIONS)

Built by `python/02_build_reference_tables.py` into `data/reference/`. These describe the illustrative Automotive Tier-1 supplier and are **assumptions, not measured data**.

- `plant.csv`: P1 Chakan (Pune), P2 Oragadam (Chennai), P3 Manesar (Gurugram).
- `shop_floor.csv`: one machining shop floor per plant, with the real dataset that anchors it.
- `machine_type.csv`: nominal spindle RPM range, rated spindle power, supply voltage 415 V, power factor 0.85, and rated current `I = P / (√3 · V · pf)`.
- `part_master.csv`: 10 part families with nominal, low and high cycle times.
- `machine_master.csv`: machine IDs 1–100 **equal the Azure PdM `machineID`**, so each fleet row traces back to its source telemetry. `azure_model` and `age_years` are copied from Azure `machines.csv` (benchmark); `commissioning_year = 2025 − age_years` (DERIVED). Controller assignment is random with seed 42 (assumption). `uns_topic_root` is the Unified Namespace MQTT topic for the machine.

| Plant | Machine IDs | Machine types (count) | Part families |
|-------|-------------|-----------------------|---------------|
| P1 Chakan | 1–40 | HMC (24), VMC (16) | Engine block, cylinder head, crankcase |
| P2 Oragadam | 41–75 | Turning (15), gear hobbing (10), grinding (10) | Gear shaft, helical gear, differential housing, gear shaft finish grind |
| P3 Manesar | 76–100 | Turning (17), VMC (8) | Brake disc, steering knuckle, wheel hub |

Note: the Bosch arrays are stored as **float64** (not float32). Bosch file names repeat across `good/` and `bad/` folders, so the file identifier used everywhere is the relative path `M0x/OPyy/label/name.h5`.

## 3. Edge features (DERIVED from REAL Bosch data)

`python/03_extract_edge_features.py` → `python/edge/bosch_features.py`. All 1,702 files (24.8 h at 2 kHz, 178.6 M tri-axial samples) are cut into non-overlapping 1-s windows (2,000 samples; trailing partial second dropped) → 88,536 windows. Per axis: mean, AC RMS, peak, peak-to-peak, crest factor, kurtosis (Fisher), skewness, Hann-windowed FFT band-energy fractions (0–50, 50–150, 150–300, 300–500, 500–1000 Hz), dominant frequency, spectral centroid = 42 values per second. Outputs `data/processed/bosch_features_1s.parquet` and `bosch_features_file.parquet` (per-file mean/std/max). Small REAL samples: `data/samples/bosch_sample_raw.parquet` (first 10 s of one good and one bad file), `data/samples/umich_experiment_05_sample.csv`, `data/samples/umich_train.csv`.

## 4. Calibration (`python/04_calibrate_models.py` → `data/reference/calibration.json`)

| Model | Source | Result |
|---|---|---|
| Process temperature | AI4I (BENCHMARK) linear regression on air temperature, rpm, torque, tool wear | 5-fold shuffled CV R² = 0.77. Air temperature dominates (coef 0.65); rpm/torque/wear coefficients are ~0, an honest property of AI4I. |
| Spindle load band | UMich (REAL) `S1_CurrentFeedback` while cutting (> 2 A, "Layer" phases) | q05/q50/q95 = 14.7/20.7/27.1 A = 22/31/41 % of the p99.9 current (66.4 A). |
| Vibration scale | Azure vibration + Bosch (REAL) bad/good RMS ratio within the same machine + operation | Median ratio 1.23, p90 1.68. Bosch faults are mostly spectral, not level changes. |
| Reject log-odds | UMich worn vs unworn visual inspection (REAL, n = 14 finalized): 4/8 worn failed, 0/6 unworn failed; Haldane +0.5 → odds ratio 13 (log-odds 2.56). AI4I logistic regression per std: process temperature 0.22, torque 1.16. |
| Alarm names | Mean 24-h per-machine z-score of each Azure signal before each event type | error1 & comp1 → volt; error2/3 & comp2 → rotate; error4 & comp3 → pressure; error5 & comp4 → vibration. |

## 5. Fleet table derivation rules (`python/05_build_fleet_table.py` → `core.machine_data`)

All columns below except `machine_id` and the Azure source timestamp are **DERIVED**.

| Column | Rule |
|---|---|
| `ts` | Azure `datetime` + **3,654 days** (= 522 weeks, so weekdays are preserved: 2015-01-01 Thu → 2025-01-02 Thu), localised to Asia/Kolkata. Range 2025-01-02 06:00 → 2026-01-02 06:00 IST. `source_ts_2015` keeps the original. |
| `plant_id`, `part_family_id` | From `machine_master.csv` (machine IDs 1–40 P1, 41–75 P2, 76–100 P3). |
| `machine_status` | Priority ALARM > MAINTENANCE > OFF > IDLE > RUNNING. ALARM = hour with an Azure error or failure. MAINTENANCE = 4–12 h repair starting the hour after a failure (maint record coinciding with a failure; 743 of 761) or 2–4 h for scheduled maintenance. OFF = plant holidays (26 Jan, 15 Aug, 2 Oct, 20–21 Oct 2025). IDLE = Azure `rotate` below the machine's own 7th percentile (low-load period: waiting for material / changeover). Otherwise RUNNING. |
| `shift` | A 06–14, B 14–22, C 22–06, 24×7. |
| `running_minutes` | 60 − breaks (10 min tea at shift hours 2 and 6, 30 min meal at hour 4) − micro-stops (Gamma(2, 1.5), mean 3 min). IDLE: U(0, 15). ALARM: 10–40 min lost (+15 min for a failure). MAINTENANCE / OFF: 0. |
| `rpm` | Linear rescale of Azure `rotate` from its fleet p0.5–p99.5 (299.9–578.1) into the machine type's nominal range (HMC 2,000–8,000; VMC 3,000–10,000; turning 800–3,500; hobbing 300–1,500; grinding 1,500–4,500), clipped; 0 when not running. Relative variation is preserved. |
| `current` (A) | Azure `volt` p05/p50/p95 mapped piecewise-linearly to the UMich load fractions 22/31/41 % (linear extrapolation outside, clipped 5–120 %); time-weighted with an 8 % no-load current over the hour's non-running minutes; × rated current `P/(√3·415 V·0.85)`. `spindle_load_pct` and `power_kw = √3·415·I·0.85/1000` follow. |
| `vibration` (mm/s RMS) | Affine map of Azure `vibration`: fleet median (40.24) → 1.8 mm/s (centre of ISO 10816-3 zone B); mean 24-h pre-comp4-failure level (50.40) → 1.8 × Bosch p90 bad/good ratio (1.68) = 3.0 mm/s (zone C boundary). Clipped at 0.3; 0 when stopped. Zones (group 2, rigid): A < 1.4, B 1.4–2.8, C 2.8–4.5, D > 4.5. Fleet-hour share A 26 %, B 68 %, C 6.4 %, D 0.04 %. |
| `hydraulic_pressure_bar` | Azure `pressure` p0.5–p99.5 mapped linearly to 45–70 bar. |
| `tool_wear_min` | Sawtooth: accrues 0.10 tool-minute per running minute (the tracked tool is in the cut ~10 % of the time); resets at tool life U(180, 240) min (AI4I range 0–253), at maintenance, and at AL-9400 (tool breakage). |
| `temperature` (°C) | AI4I model applied with: air temperature = plant monthly shop-floor ambient (Pune / Chennai / Gurugram profiles, assumption) + 2.5 °C diurnal swing peaking 15:00; rpm and torque mapped into AI4I ranges from the RPM fraction and load; tool wear; + N(0, 0.72 K) residual. |
| `production_count` | running_minutes ÷ actual cycle time, where actual = nominal × (1 + 0.06·wear/240) × N(1, 0.02); stochastic rounding. `ideal_count` = running_minutes ÷ nominal cycle (for OEE performance). |
| `reject_count` | p = logistic(b0 + 2.56·wear/240 + 0.22·z(temperature) + 1.16·z(vibration)), capped at 20 %; b0 solved by bisection so the fleet reject rate = 1.5 %; count ~ Binomial(production_count, p). Result: fleet 1.50 %, P1 1.48 %, P2 1.61 %, P3 1.37 %. |
| `alarm`, `alarm_code`, `alarm_count` | `alarm` = an event occurred in the hour; code from `alarm_master.csv` (a failure outranks an error); `alarm_count` = events in the hour. **The error → alarm-name mapping is illustrative.** |

Seeds: reference tables 42, fleet build 2025. All scripts are deterministic and idempotent.
