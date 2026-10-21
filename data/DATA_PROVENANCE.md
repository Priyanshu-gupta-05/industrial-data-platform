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

## 3. Derivation rules for the fleet table

*(Completed in the integration stage: timestamp shift, RPM rescale, current, vibration, temperature, alarms, machine status, production count and reject count.)*
