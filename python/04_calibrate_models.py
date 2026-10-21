"""Calibrate the derivation models used to build the fleet table.

Every derived fleet column is anchored to a real or benchmark dataset here:

  1. Temperature  : linear model fitted on AI4I (process temperature vs air temperature,
                    rotational speed, torque, tool wear), 5-fold CV R^2 reported.
  2. Current      : load-fraction band from REAL UMich spindle current (S1_CurrentFeedback)
                    while cutting; used to map Azure `volt` to spindle current.
  3. Vibration    : Azure `vibration` scaled to mm/s RMS so the fleet median sits mid
                    ISO 10816-3 zone B; the good->bad spread measured on REAL Bosch
                    features checks that faults reach zones C/D.
  4. Reject model : log-odds terms for tool wear (REAL UMich worn vs unworn inspection
                    outcome) and for temperature / mechanical load (AI4I logistic regression).
  5. Alarm master : each Azure error / failure type is named after the telemetry signal
                    that shifts in the 24 h before it (measured here), so names follow the data.

Outputs: data/reference/calibration.json, data/reference/alarm_master.csv,
         docs/figures/calib_*.png

    python python/04_calibrate_models.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.model_selection import KFold, cross_val_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import style  # noqa: E402
from utils.paths import AI4I_CSV, AZURE_DIR, FIGURES_DIR, PROCESSED_DIR, REFERENCE_DIR, UMICH_DIR  # noqa: E402

AI4I_COLS = {"Air temperature [K]": "air_k", "Process temperature [K]": "proc_k", "Rotational speed [rpm]": "rpm",
             "Torque [Nm]": "torque", "Tool wear [min]": "wear"}
ISO_B_MID = 1.8   # mm/s, centre of zone B (1.4-2.8) for a healthy machine (ISO 10816-3 group 2, rigid)


def temperature_model(ai: pd.DataFrame) -> dict:
    X, y = ai[["air_k", "rpm", "torque", "wear"]], ai["proc_k"]
    lr = LinearRegression().fit(X, y)
    # AI4I rows are time-ordered (air temperature drifts), so folds must be shuffled
    cv = cross_val_score(LinearRegression(), X, y, cv=KFold(5, shuffle=True, random_state=0), scoring="r2")
    resid = y - lr.predict(X)
    return {"intercept": float(lr.intercept_), "coef": dict(zip(X.columns, map(float, lr.coef_))),
            "cv_r2_mean": float(cv.mean()), "cv_r2_std": float(cv.std()), "residual_std_k": float(resid.std()),
            "input_ranges": {c: [float(X[c].min()), float(X[c].max())] for c in X.columns}}


def current_band() -> dict:
    exps = pd.concat([pd.read_csv(f) for f in sorted(UMICH_DIR.glob("experiment_*.csv"))])
    cutting = exps[exps.Machining_Process.str.contains("Layer", na=False)]
    i = cutting["S1_CurrentFeedback"]
    i = i[i > 2.0]  # spindle actually loaded
    ref = float(np.percentile(exps["S1_CurrentFeedback"], 99.9))
    q = {p: float(np.percentile(i, p)) for p in (5, 50, 95)}
    return {"umich_cutting_current_q05_a": q[5], "umich_cutting_current_q50_a": q[50],
            "umich_cutting_current_q95_a": q[95], "umich_current_p999_a": ref,
            "load_fraction_q05": q[5] / ref, "load_fraction_q50": q[50] / ref, "load_fraction_q95": q[95] / ref,
            "n_cutting_samples": int(len(i))}


def vibration_scale(tel: pd.DataFrame) -> dict:
    med = float(tel["vibration"].median())
    scale = ISO_B_MID / med
    out = {"azure_vibration_median": med, "scale_mm_s_per_unit": scale}
    fpath = PROCESSED_DIR / "bosch_features_file.parquet"
    if fpath.exists():
        fl = pd.read_parquet(fpath)
        rms = fl[["x_rms__mean", "y_rms__mean", "z_rms__mean"]].pow(2).sum(axis=1).pow(0.5)  # vector RMS
        good = rms[fl.label == "good"]
        bad = rms[fl.label == "bad"]
        # per machine+operation normalisation removes the operation's own level
        norm = rms / fl.assign(r=rms).groupby(["machine", "operation"]).r.transform(
            lambda s: s[fl.loc[s.index, "label"] == "good"].median())
        out.update({
            "bosch_good_rms_cv": float(good.std() / good.mean()),
            "bosch_bad_to_good_median_ratio": float(bad.median() / good.median()),
            "bosch_bad_to_good_ratio_within_operation_median": float(norm[fl.label == "bad"].median()),
            "bosch_bad_to_good_ratio_within_operation_p90": float(norm[fl.label == "bad"].quantile(0.9)),
        })
        # The 24 h before a bearing / tool failure is the severe end of the fault range, so it is
        # anchored to the 90th percentile of the Bosch bad/good ratio (median is only ~1.2x:
        # Bosch faults show mainly in the spectrum, not in overall RMS level).
        ratio = out["bosch_bad_to_good_ratio_within_operation_p90"]
    else:
        ratio = 2.0
        out["warning"] = "Bosch features missing: fallback bad/good ratio 2.0 used"
    out["implied_fault_level_mm_s"] = ISO_B_MID * ratio
    # Azure: mean raw vibration in the 24 h before comp4 (vibration-related) failures
    fail = pd.read_csv(AZURE_DIR / "failures.csv", parse_dates=["datetime"])
    t = tel.sort_values(["machineID", "datetime"])
    roll = t.groupby("machineID")["vibration"].rolling(24, min_periods=12).mean().reset_index(level=0, drop=True)
    t = t.assign(v24=roll).set_index(["machineID", "datetime"])["v24"]
    pre = fail[fail.failure == "comp4"].join(t, on=["machineID", "datetime"])["v24"].mean()
    out["azure_vibration_pre_comp4_failure_24h"] = float(pre)
    # Affine map: fleet median -> zone-B centre; pre-failure level -> Bosch-measured fault level
    slope = (out["implied_fault_level_mm_s"] - ISO_B_MID) / (pre - med)
    out["vib_slope_mm_s_per_unit"] = float(slope)
    out["vib_offset_mm_s"] = float(ISO_B_MID - slope * med)
    v = np.clip(out["vib_offset_mm_s"] + slope * tel["vibration"], 0.3, None)
    out["fleet_zone_share"] = {name: float(((v >= lo) & (v < hi)).mean()) for lo, hi, name, _ in style.ISO_ZONES}
    out["fleet_zone_share"]["D danger"] += float((v >= style.ISO_ZONES[-1][1]).mean())
    return out


def reject_terms(ai: pd.DataFrame) -> dict:
    tr = pd.read_csv(UMICH_DIR / "train.csv")
    fin = tr[tr.machining_finalized == "yes"]
    tab = pd.crosstab(fin.tool_condition, fin.passed_visual_inspection)
    # Haldane-Anscombe correction (+0.5) because unworn tools have zero failures
    worn_fail, worn_pass = tab.loc["worn", "no"] + 0.5, tab.loc["worn", "yes"] + 0.5
    un_fail, un_pass = tab.loc["unworn"].get("no", 0) + 0.5, tab.loc["unworn", "yes"] + 0.5
    log_or_wear = float(np.log((worn_fail / worn_pass) / (un_fail / un_pass)))

    X = StandardScaler().fit_transform(ai[["proc_k", "torque", "wear"]])
    lr = LogisticRegression(max_iter=1000).fit(X, ai["Machine failure"])
    coef = dict(zip(["proc_k", "torque", "wear"], map(float, lr.coef_[0])))
    return {"umich_crosstab": {k: {kk: int(vv) for kk, vv in v.items()} for k, v in tab.to_dict("index").items()},
            "umich_log_odds_ratio_worn_vs_unworn": log_or_wear, "umich_odds_ratio": float(np.exp(log_or_wear)),
            "ai4i_logit_coef_per_std": coef,
            # Terms used in the fleet reject model (log-odds):
            "b_wear_full_life": log_or_wear,               # from 0 -> end of tool life
            "b_temp_per_std": max(coef["proc_k"], 0.0),    # AI4I process temperature
            "b_vib_per_std": max(coef["torque"], 0.0),     # AI4I torque as mechanical-load proxy for vibration
            "target_plant_reject_rate": 0.015}


def alarm_master(tel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = ["volt", "rotate", "pressure", "vibration"]
    z = tel.sort_values(["machineID", "datetime"]).copy()
    g = z.groupby("machineID")[cols]
    z[cols] = (z[cols] - g.transform("mean")) / g.transform("std")
    roll = z.groupby("machineID")[cols].rolling(24, min_periods=12).mean().reset_index(level=0, drop=True)
    z[cols] = roll
    key = z.set_index(["machineID", "datetime"])[cols]
    evidence = []
    for fname, col in [("errors", "errorID"), ("failures", "failure")]:
        ev = pd.read_csv(AZURE_DIR / f"{fname}.csv", parse_dates=["datetime"])
        j = ev.join(key, on=["machineID", "datetime"]).groupby(col)[cols].mean()
        j["n_events"] = ev[col].value_counts()
        j["source_table"] = fname
        evidence.append(j)
    ev = pd.concat(evidence)
    ev["dominant_signal"] = ev[cols].abs().idxmax(axis=1)
    ev["dominant_z"] = ev.apply(lambda r: r[r["dominant_signal"]], axis=1)

    # Name follows the dominant signal (volt->spindle drive current, rotate->spindle speed,
    # pressure->hydraulics, vibration->vibration). Illustrative CNC alarm vocabulary.
    names = {
        "error1": ("AL-1010", "Spindle drive overcurrent / overload", "WARNING", "spindle_current"),
        "error2": ("AL-2010", "Spindle speed deviation (actual < command)", "WARNING", "spindle_rpm"),
        "error3": ("AL-2020", "Axis following error (servo lag)", "WARNING", "spindle_rpm"),
        "error4": ("AL-3010", "Hydraulic pressure abnormal (tool clamp)", "WARNING", "hydraulic_pressure"),
        "error5": ("AL-4010", "High spindle vibration", "WARNING", "spindle_vibration"),
        "comp1": ("AL-9100", "Spindle motor / drive failure", "CRITICAL", "spindle_current"),
        "comp2": ("AL-9200", "Spindle gearbox / belt failure", "CRITICAL", "spindle_rpm"),
        "comp3": ("AL-9300", "Hydraulic unit / tool-clamp failure", "CRITICAL", "hydraulic_pressure"),
        "comp4": ("AL-9400", "Tool breakage / spindle bearing damage", "CRITICAL", "spindle_vibration"),
    }
    am = pd.DataFrame([{"alarm_code": c, "alarm_name": n, "severity": s, "related_sensor": sensor,
                        "source_event": k} for k, (c, n, s, sensor) in names.items()])
    am = am.merge(ev[["source_table", "n_events", "dominant_signal", "dominant_z"]].rename_axis("source_event")
                  .reset_index(), on="source_event")
    am["mapping_note"] = "Illustrative mapping of Azure PdM benchmark event to CNC alarm; name chosen from dominant pre-event telemetry shift"
    return am, ev


def fig_calibration(ai: pd.DataFrame, temp: dict, ev: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.3))
    X = ai[["air_k", "rpm", "torque", "wear"]]
    pred = temp["intercept"] + X.to_numpy() @ np.array(list(temp["coef"].values()))
    axes[0].scatter(ai["proc_k"] - 273.15, pred - 273.15, s=3, alpha=0.25, color=style.SERIES[0], linewidth=0)
    lim = [ai["proc_k"].min() - 273.6, ai["proc_k"].max() - 272.7]
    axes[0].plot(lim, lim, color=style.INK_2, lw=1, ls="--")
    axes[0].set_xlabel("AI4I process temperature (°C)")
    axes[0].set_ylabel("Model prediction (°C)")
    axes[0].set_title(f"Temperature model on AI4I: CV R² = {temp['cv_r2_mean']:.3f}", fontsize=10)
    cols = ["volt", "rotate", "pressure", "vibration"]
    data = ev[cols]
    im = axes[1].imshow(data.to_numpy(), cmap="RdBu_r", vmin=-2.2, vmax=2.2, aspect="auto")
    axes[1].set_xticks(range(4), cols)
    axes[1].set_yticks(range(len(data)), data.index)
    for i in range(data.shape[0]):
        for j in range(4):
            axes[1].text(j, i, f"{data.iat[i, j]:+.2f}", ha="center", va="center", fontsize=8,
                         color="white" if abs(data.iat[i, j]) > 1.2 else style.INK)
    axes[1].grid(False)
    axes[1].set_title("Mean 24-h telemetry z-score before each Azure event", fontsize=10)
    fig.colorbar(im, ax=axes[1], shrink=0.85, label="z-score (σ)")
    fig.suptitle("Calibration - temperature model (AI4I) and data-driven alarm mapping (Azure PdM)", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "BENCHMARK data: AI4I 2020 (synthetic), Azure PdM (simulated). Model outputs DERIVED.")
    style.save(fig, FIGURES_DIR / "calib_temperature_and_alarm_mapping")


def main() -> None:
    style.apply()
    ai = pd.read_csv(AI4I_CSV).rename(columns=AI4I_COLS)
    tel = pd.read_csv(AZURE_DIR / "telemetry.csv", parse_dates=["datetime"])
    temp = temperature_model(ai)
    cur = current_band()
    vib = vibration_scale(tel)
    rej = reject_terms(ai)
    am, ev = alarm_master(tel)
    am.to_csv(REFERENCE_DIR / "alarm_master.csv", index=False)
    calib = {"temperature_model_ai4i": temp, "current_umich": cur, "vibration": vib, "reject_model": rej,
             "azure_rotate_p005_p995": [float(tel.rotate.quantile(0.005)), float(tel.rotate.quantile(0.995))],
             "azure_volt_p05_p50_p95": [float(tel.volt.quantile(q)) for q in (0.05, 0.5, 0.95)],
             "azure_pressure_p005_p995": [float(tel.pressure.quantile(0.005)), float(tel.pressure.quantile(0.995))]}
    (REFERENCE_DIR / "calibration.json").write_text(json.dumps(calib, indent=2))
    fig_calibration(ai, temp, ev)
    print(json.dumps(calib, indent=1))
    print(am[["alarm_code", "alarm_name", "source_event", "dominant_signal", "dominant_z", "n_events"]].to_string(index=False))


if __name__ == "__main__":
    main()
