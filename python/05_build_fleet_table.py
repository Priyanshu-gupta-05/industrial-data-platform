"""Build the integrated 100-machine fleet fact table (core.machine_data).

Backbone: Azure PdM telemetry (BENCHMARK, simulated), 100 machines x 8,761 hours.
Every other column is DERIVED with rules documented in data/DATA_PROVENANCE.md and
calibrated in python/04_calibrate_models.py (data/reference/calibration.json).

Output: data/processed/machine_data.parquet   (also the hosted-dashboard snapshot)
        data/processed/events.parquet          (alarm / maintenance / failure events, DERIVED timestamps)

    python python/05_build_fleet_table.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.paths import AZURE_DIR, PROCESSED_DIR, REFERENCE_DIR  # noqa: E402

SEED = 2025
# 2015-01-01 (Thu) + 3,654 days = 2025-01-02 (Thu): 3,654 = 522 weeks, so weekdays are preserved.
SHIFT_DAYS = 3654
TZ = "Asia/Kolkata"

# Shift model: 3 x 8 h shifts, 24x7. Breaks inside each shift reduce running minutes.
SHIFT_STARTS = {6: "A", 14: "B", 22: "C"}               # shift A 06-14, B 14-22, C 22-06
BREAK_MINUTES_BY_HOUR_IN_SHIFT = {2: 10, 4: 30, 6: 10}   # tea (10), meal (30), tea (10)
# Plant holidays (OFF all day, all plants): Republic Day, Independence Day, Gandhi Jayanti, Diwali (2 days)
HOLIDAYS = ["2025-01-26", "2025-08-15", "2025-10-02", "2025-10-20", "2025-10-21"]
# Mean daily shop-floor ambient temperature (deg C) by month, per plant (scenario assumption;
# shaped on IMD climate normals for Pune, Chennai and Gurugram, buffered by the shop building)
AMBIENT_C = {
    1: [24, 28, 27, 29, 31, 30, 27, 27, 27, 27, 25, 23],
    2: [27, 28, 30, 32, 34, 34, 32, 31, 31, 30, 28, 27],
    3: [16, 19, 25, 31, 34, 34, 31, 30, 29, 27, 22, 17],
}
DIURNAL_AMPLITUDE_C = 2.5  # peak at 15:00
# The tracked (critical) tool is in the cut ~10 % of machine running time (a magazine holds many
# tools), so a 180-240 tool-minute life lasts ~30-40 running hours between changes.
TOOL_CUT_SHARE = 0.10
P_REJECT_CAP = 0.20


def load_inputs():
    tel = pd.read_csv(AZURE_DIR / "telemetry.csv", parse_dates=["datetime"])
    errors = pd.read_csv(AZURE_DIR / "errors.csv", parse_dates=["datetime"])
    maint = pd.read_csv(AZURE_DIR / "maint.csv", parse_dates=["datetime"])
    failures = pd.read_csv(AZURE_DIR / "failures.csv", parse_dates=["datetime"])
    machines = pd.read_csv(REFERENCE_DIR / "machine_master.csv")
    parts = pd.read_csv(REFERENCE_DIR / "part_master.csv")
    alarms = pd.read_csv(REFERENCE_DIR / "alarm_master.csv")
    calib = json.loads((REFERENCE_DIR / "calibration.json").read_text())
    return tel, errors, maint, failures, machines, parts, alarms, calib


def shift_ts(s: pd.Series) -> pd.Series:
    return (s + pd.Timedelta(days=SHIFT_DAYS)).dt.tz_localize(TZ)


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    tel, errors, maint, failures, machines, parts, alarms, calib = load_inputs()
    t0, t1 = tel.datetime.min(), tel.datetime.max()
    maint = maint[(maint.datetime >= t0) & (maint.datetime <= t1)]

    df = tel.rename(columns={"machineID": "machine_id"}).sort_values(["machine_id", "datetime"]).reset_index(drop=True)
    df["ts"] = shift_ts(df["datetime"])
    df = df.merge(machines[["machine_id", "plant_id", "machine_type", "part_family_id", "rpm_min", "rpm_max",
                            "rated_current_a", "rated_power_kw"]], on="machine_id", how="left")
    df = df.merge(parts[["part_family_id", "cycle_time_min"]], on="part_family_id", how="left")
    n = len(df)
    local = df["ts"].dt.tz_localize(None)
    hour = local.dt.hour.to_numpy()

    # ---------------------------------------------------------------- events -> per-hour flags
    key = df.set_index(["machine_id", "datetime"]).index
    def flag(ev: pd.DataFrame) -> np.ndarray:
        idx = pd.MultiIndex.from_frame(ev.rename(columns={"machineID": "machine_id"})[["machine_id", "datetime"]])
        return key.isin(idx)

    err_map = alarms.set_index("source_event")["alarm_code"].to_dict()
    errors["alarm_code"] = errors.errorID.map(err_map)
    failures["alarm_code"] = failures.failure.map(err_map)
    # one alarm code per hour: a failure outranks an error; among errors keep the first
    ev_all = pd.concat([failures.assign(rank=0)[["datetime", "machineID", "alarm_code", "rank"]],
                        errors.assign(rank=1)[["datetime", "machineID", "alarm_code", "rank"]]])
    alarm_count = ev_all.groupby(["machineID", "datetime"]).size()
    ev_first = ev_all.sort_values("rank").drop_duplicates(["machineID", "datetime"]).set_index(["machineID", "datetime"])
    df["alarm_code"] = ev_first["alarm_code"].reindex(key).to_numpy()
    df["alarm_count"] = alarm_count.reindex(key).fillna(0).astype(np.int16).to_numpy()
    is_failure = flag(failures)
    is_error = flag(errors)

    # repairs after a failure (MAINTENANCE for 4-12 h) and scheduled maintenance (2-4 h)
    fail_keys = set(map(tuple, failures[["machineID", "datetime", "failure"]].to_numpy()))
    maint["is_failure_repair"] = [(m, d, c) in fail_keys for m, d, c in maint[["machineID", "datetime", "comp"]].to_numpy()]
    maint_hours = np.zeros(n, dtype=bool)
    pos = pd.Series(np.arange(n), index=key)
    for (m, d), grp in maint.groupby(["machineID", "datetime"]):
        dur = int(rng.integers(4, 13)) if grp.is_failure_repair.any() else int(rng.integers(2, 5))
        start = pos.get((m, d))
        if start is None:
            continue
        # repair starts the hour after the failure hour; scheduled maintenance starts at the record hour
        s = start + (1 if grp.is_failure_repair.any() else 0)
        end = min(s + dur, len(df))
        same_machine = df["machine_id"].to_numpy()[s:end] == m
        maint_hours[s:end][same_machine] = True
    df["maint_after"] = maint_hours

    # ---------------------------------------------------------------- status
    holiday = local.dt.strftime("%Y-%m-%d").isin(HOLIDAYS).to_numpy()
    rot_p7 = df.groupby("machine_id")["rotate"].transform(lambda s: s.quantile(0.07)).to_numpy()
    low_load = df["rotate"].to_numpy() < rot_p7
    status = np.full(n, "RUNNING", dtype=object)
    status[low_load] = "IDLE"
    status[holiday] = "OFF"
    status[maint_hours] = "MAINTENANCE"
    status[is_error | is_failure] = "ALARM"   # alarm hour has priority (the event happened in this hour)
    df["machine_status"] = status

    # ---------------------------------------------------------------- running minutes in the hour
    hour_in_shift = np.array([(h - 6) % 8 for h in hour])
    breaks = np.array([BREAK_MINUTES_BY_HOUR_IN_SHIFT.get(int(x), 0) for x in hour_in_shift])
    microstops = rng.gamma(2.0, 1.5, n)                       # short stops, mean 3 min
    run_min = 60 - breaks - microstops
    run_min = np.where(status == "IDLE", rng.uniform(0, 15, n), run_min)
    run_min = np.where(status == "ALARM", 60 - breaks - rng.uniform(10, 40, n) - (is_failure * 15), run_min)
    run_min = np.where(np.isin(status, ["MAINTENANCE", "OFF"]), 0, run_min)
    df["running_minutes"] = np.clip(run_min, 0, 60).round(1)
    running = df["running_minutes"].to_numpy() > 0

    # ---------------------------------------------------------------- RPM (linear rescale per machine type)
    r_lo, r_hi = calib["azure_rotate_p005_p995"]
    frac = np.clip((df["rotate"] - r_lo) / (r_hi - r_lo), 0, 1)
    df["rpm"] = np.where(running, df["rpm_min"] + frac * (df["rpm_max"] - df["rpm_min"]), 0).round(0)

    # ---------------------------------------------------------------- current (from volt, UMich load band)
    c = calib["current_umich"]
    v05, v50, v95 = calib["azure_volt_p05_p50_p95"]
    # piecewise-linear: Azure volt p05/p50/p95 -> UMich cutting load fraction q05/q50/q95 (extrapolated beyond)
    load = np.interp(df["volt"], [v05, v50, v95], [c["load_fraction_q05"], c["load_fraction_q50"], c["load_fraction_q95"]],
                     left=np.nan, right=np.nan)
    slope_lo = (c["load_fraction_q50"] - c["load_fraction_q05"]) / (v50 - v05)
    slope_hi = (c["load_fraction_q95"] - c["load_fraction_q50"]) / (v95 - v50)
    load = np.where(df["volt"] < v05, c["load_fraction_q05"] + (df["volt"] - v05) * slope_lo, load)
    load = np.where(df["volt"] > v95, c["load_fraction_q95"] + (df["volt"] - v95) * slope_hi, load)
    load = np.clip(load, 0.05, 1.2)
    idle_current = 0.08  # magnetising / no-load current fraction when spindle is stopped
    duty = df["running_minutes"].to_numpy() / 60
    load_eff = np.where(running, duty * load + (1 - duty) * idle_current, 0.0)
    df["spindle_load_pct"] = (load_eff * 100).round(1)
    df["current"] = (load_eff * df["rated_current_a"]).round(2)
    df["power_kw"] = (np.sqrt(3) * 415 * df["current"] * 0.85 / 1000).round(2)

    # ---------------------------------------------------------------- vibration (mm/s RMS)
    vb = calib["vibration"]
    vib = vb["vib_offset_mm_s"] + vb["vib_slope_mm_s_per_unit"] * df["vibration"]
    vib = np.clip(vib, 0.3, None)
    df["vibration_mm_s"] = np.where(running | (status == "ALARM"), vib, 0.0).round(3)

    # ---------------------------------------------------------------- hydraulic pressure (bar)
    p_lo, p_hi = calib["azure_pressure_p005_p995"]
    df["hydraulic_pressure_bar"] = (45 + (df["pressure"] - p_lo) / (p_hi - p_lo) * 25).round(2)  # 45-70 bar band

    # ---------------------------------------------------------------- tool wear (min, sawtooth)
    tool_wear = np.zeros(n)
    life = rng.uniform(180, 240, 100 + 1)   # per machine tool life (min), AI4I tool-wear range 0-253 min
    mid = df["machine_id"].to_numpy()
    rmin = df["running_minutes"].to_numpy()
    tool_change = np.isin(status, ["MAINTENANCE"]) | (df["alarm_code"].isin(["AL-9400"]).to_numpy())
    w = 0.0
    for i in range(n):
        if i == 0 or mid[i] != mid[i - 1]:
            w = rng.uniform(0, life[mid[i]])
        if tool_change[i] or w >= life[mid[i]]:
            w = 0.0
        w += rmin[i] * TOOL_CUT_SHARE   # tool-minutes accrue only while this tool is in the cut
        tool_wear[i] = w
    df["tool_wear_min"] = np.round(tool_wear, 1)

    # ---------------------------------------------------------------- temperature (AI4I model)
    tm = calib["temperature_model_ai4i"]
    month = local.dt.month.to_numpy()
    amb = np.array([AMBIENT_C[p][m - 1] for p, m in zip(df["plant_id"].to_numpy(), month)], dtype=float)
    amb += DIURNAL_AMPLITUDE_C * np.cos((hour - 15) / 24 * 2 * np.pi)
    air_k = amb + 273.15
    ai_rpm = np.interp(frac, [0, 1], tm["input_ranges"]["rpm"])
    ai_torque = np.interp(load, [0.05, 1.2], tm["input_ranges"]["torque"])
    co = tm["coef"]
    proc_k = (tm["intercept"] + co["air_k"] * air_k + co["rpm"] * ai_rpm + co["torque"] * ai_torque
              + co["wear"] * df["tool_wear_min"].to_numpy() + rng.normal(0, tm["residual_std_k"], n))
    df["temperature"] = (proc_k - 273.15).round(2)
    df["ambient_c"] = amb.round(1)

    # ---------------------------------------------------------------- production
    cyc = df["cycle_time_min"].to_numpy()
    # actual cycle slows slightly with tool wear (performance loss up to ~6 %)
    actual_cyc = cyc * (1 + 0.06 * df["tool_wear_min"].to_numpy() / 240) * rng.normal(1.0, 0.02, n)
    expected = rmin / actual_cyc
    # stochastic rounding: a machine completes floor(expected) parts plus one more with the fractional probability
    expected = np.clip(expected, 0, None)
    df["production_count"] = (np.floor(expected) + (rng.random(n) < expected % 1)).astype(np.int32)
    df["ideal_count"] = (rmin / cyc).round(2)

    # ---------------------------------------------------------------- rejects
    rj = calib["reject_model"]
    wear_n = df["tool_wear_min"].to_numpy() / 240
    temp_z = (df["temperature"] - df["temperature"].mean()) / df["temperature"].std()
    vib_z = (df["vibration_mm_s"] - df.loc[running, "vibration_mm_s"].mean()) / df.loc[running, "vibration_mm_s"].std()
    logit_wo_b0 = rj["b_wear_full_life"] * wear_n + rj["b_temp_per_std"] * temp_z + rj["b_vib_per_std"] * vib_z
    logit_wo_b0 = logit_wo_b0.to_numpy()
    prod = df["production_count"].to_numpy()
    # solve intercept so the production-weighted reject rate hits the target
    # an hour with >20 % scrap would trigger a line stop in practice, so probability is capped
    def p_of(b0: float) -> np.ndarray:
        return np.minimum(1 / (1 + np.exp(-(b0 + logit_wo_b0))), P_REJECT_CAP)
    lo, hi = -12.0, 0.0
    for _ in range(60):
        b0 = (lo + hi) / 2
        rate = (prod * p_of(b0)).sum() / prod.sum()
        lo, hi = (b0, hi) if rate < rj["target_plant_reject_rate"] else (lo, b0)
    p_rej = p_of(b0)
    df["reject_probability"] = p_rej.round(5)
    df["reject_count"] = rng.binomial(prod, p_rej).astype(np.int32)
    calib["reject_model"]["b0_solved"] = b0

    # ---------------------------------------------------------------- tidy
    df["alarm"] = df["alarm_code"].notna()
    shift_start = np.array([6 if 6 <= h < 14 else 14 if 14 <= h < 22 else 22 for h in hour])
    df["shift"] = pd.Series(shift_start).map(SHIFT_STARTS).to_numpy()
    out = df[["machine_id", "ts", "plant_id", "part_family_id", "shift", "temperature", "vibration_mm_s", "rpm",
              "current", "production_count", "reject_count", "machine_status", "alarm", "alarm_code", "alarm_count",
              "tool_wear_min", "running_minutes", "spindle_load_pct", "power_kw", "hydraulic_pressure_bar",
              "ambient_c", "ideal_count", "reject_probability"]].rename(columns={"vibration_mm_s": "vibration"})
    out["source_ts_2015"] = df["datetime"]   # traceability to the Azure source row
    for col, dt in [("plant_id", "int16"), ("part_family_id", "int16"), ("machine_id", "int16"),
                    ("temperature", "float32"), ("vibration", "float32"), ("rpm", "float32"), ("current", "float32"),
                    ("tool_wear_min", "float32"), ("running_minutes", "float32"), ("spindle_load_pct", "float32"),
                    ("power_kw", "float32"), ("hydraulic_pressure_bar", "float32"), ("ambient_c", "float32"),
                    ("ideal_count", "float32"), ("reject_probability", "float32")]:
        out[col] = out[col].astype(dt)

    events = pd.concat([
        errors.assign(event_type="ERROR", source="errors.csv").rename(columns={"errorID": "source_code"}),
        failures.assign(event_type="FAILURE", source="failures.csv").rename(columns={"failure": "source_code"}),
        maint.assign(event_type=np.where(maint.is_failure_repair, "REPAIR", "SCHEDULED_MAINTENANCE"),
                     source="maint.csv", alarm_code=None).rename(columns={"comp": "source_code"}),
    ])[["machineID", "datetime", "event_type", "source_code", "alarm_code", "source"]]
    events = events.rename(columns={"machineID": "machine_id", "datetime": "source_ts_2015"})
    events["ts"] = shift_ts(events["source_ts_2015"])
    (REFERENCE_DIR / "calibration.json").write_text(json.dumps(calib, indent=2))
    return out, events.sort_values(["machine_id", "ts"]).reset_index(drop=True)


def main() -> None:
    out, events = build()
    out.to_parquet(PROCESSED_DIR / "machine_data.parquet", compression="zstd", index=False)
    events.to_parquet(PROCESSED_DIR / "events.parquet", compression="zstd", index=False)
    size = (PROCESSED_DIR / "machine_data.parquet").stat().st_size / 1e6
    print(f"machine_data: {len(out):,} rows x {out.shape[1]} cols, {size:.1f} MB  "
          f"({out.ts.min()} -> {out.ts.max()})")
    print(out.machine_status.value_counts(normalize=True).round(4).to_dict())
    print("reject rate overall:", round(out.reject_count.sum() / out.production_count.sum() * 100, 3), "%")
    print("by plant:", (out.groupby("plant_id").reject_count.sum() / out.groupby("plant_id").production_count.sum() * 100)
          .round(2).to_dict())
    print(out.describe().T[["mean", "min", "50%", "max"]].round(2).to_string())


if __name__ == "__main__":
    main()
