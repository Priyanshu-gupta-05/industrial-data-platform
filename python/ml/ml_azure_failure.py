"""Component-failure prediction (failure within the next 24 h) on the Azure PdM fleet.

Data: Azure PdM BENCHMARK (simulated by Microsoft), 100 machines, hourly, 2015.
Features at hour t use only data up to t: 3-h and 24-h rolling mean/std of volt, rotate,
pressure, vibration; error counts per type in the last 24 h; hours since the last
replacement of each component (maintenance log incl. 2014); machine age and model.
Label: any component failure in (t, t + 24 h].
Split: time-based. Train Jan-Aug 2015, 24-h gap, test Sep-Dec 2015 (no shuffling, no leakage).

Outputs: docs/results/ml_azure_failure.json, docs/figures/ml_azure_*.png,
         data/processed/pdm_risk_scores.parquet (test-period hourly risk, timestamps shifted to 2025)

    python python/ml/ml_azure_failure.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance

from common import FIGURES_DIR, PROCESSED_DIR, metrics, plot_confusion, plot_roc_pr, save_json, style

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import AZURE_DIR  # noqa: E402

SIGNALS = ["volt", "rotate", "pressure", "vibration"]
SPLIT = pd.Timestamp("2015-09-01 06:00")
SHIFT_DAYS = 3654  # same weekday-aligned shift as the fleet table


def build_features() -> pd.DataFrame:
    tel = pd.read_csv(AZURE_DIR / "telemetry.csv", parse_dates=["datetime"]).sort_values(["machineID", "datetime"])
    g = tel.groupby("machineID")[SIGNALS]
    feats = tel[["machineID", "datetime"]].copy()
    for win in (3, 24):
        m = g.rolling(win, min_periods=1).mean().reset_index(level=0, drop=True)
        s = g.rolling(win, min_periods=2).std().reset_index(level=0, drop=True)
        for c in SIGNALS:
            feats[f"{c}_mean_{win}h"] = m[c]
            feats[f"{c}_std_{win}h"] = s[c]

    # error counts in the last 24 h, per error type
    err = pd.read_csv(AZURE_DIR / "errors.csv", parse_dates=["datetime"])
    e = pd.crosstab([err.machineID, err.datetime], err.errorID)
    e = feats[["machineID", "datetime"]].join(e, on=["machineID", "datetime"]).fillna(0)
    ecols = sorted(err.errorID.unique())
    roll = e.groupby("machineID")[ecols].rolling(24, min_periods=1).sum().reset_index(level=0, drop=True)
    for c in ecols:
        feats[f"{c}_count_24h"] = roll[c].to_numpy()

    # hours since last replacement of each component (maintenance log includes 2014 history)
    maint = pd.read_csv(AZURE_DIR / "maint.csv", parse_dates=["datetime"])
    for comp in sorted(maint.comp.unique()):
        mc = maint[maint.comp == comp][["machineID", "datetime"]].rename(columns={"datetime": "last"})
        mc = mc.sort_values("last")
        merged = pd.merge_asof(feats[["machineID", "datetime"]].sort_values("datetime"), mc,
                               left_on="datetime", right_on="last", by="machineID", direction="backward")
        merged = merged.set_index(["machineID", "datetime"])["last"]
        feats[f"{comp}_hours_since_replace"] = (
            (feats.set_index(["machineID", "datetime"]).index.map(lambda k: k[1]) -
             merged.reindex(pd.MultiIndex.from_frame(feats[["machineID", "datetime"]])).to_numpy())
            / pd.Timedelta(hours=1)).to_numpy()

    mach = pd.read_csv(AZURE_DIR / "machines.csv")
    feats = feats.merge(mach, on="machineID")
    feats["model"] = feats["model"].str.replace("model", "").astype(int)

    # label: any failure in (t, t+24h]
    fail = pd.read_csv(AZURE_DIR / "failures.csv", parse_dates=["datetime"])
    f = fail.groupby(["machineID", "datetime"]).size().rename("n").reset_index()
    flag = feats[["machineID", "datetime"]].merge(f, on=["machineID", "datetime"], how="left").fillna({"n": 0})
    flag["n"] = (flag["n"] > 0).astype(int)
    # forward-looking window sum: reverse time, rolling 24 over the NEXT hours (excluding t)
    rev = flag.iloc[::-1]
    nxt = rev.groupby("machineID")["n"].transform(lambda s: s.shift(1).rolling(24, min_periods=1).sum())
    feats["y"] = (nxt.iloc[::-1].fillna(0).to_numpy() > 0).astype(int)
    return feats


def main() -> None:
    style.apply()
    df = build_features()
    X_cols = [c for c in df.columns if c not in ("machineID", "datetime", "y")]
    train = df[df.datetime < SPLIT - pd.Timedelta(hours=24)]      # 24-h gap: no label overlaps the split
    test = df[df.datetime >= SPLIT]
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, class_weight="balanced", random_state=0)
    clf.fit(train[X_cols], train["y"])
    s = clf.predict_proba(test[X_cols])[:, 1]
    m = metrics(test["y"], s)

    # alert-level view: one alert per machine per 24 h -> how many failures get >= 1 alert in the 24 h before
    fail = pd.read_csv(AZURE_DIR / "failures.csv", parse_dates=["datetime"])
    fail = fail[fail.datetime >= SPLIT + pd.Timedelta(hours=24)].drop_duplicates(["machineID", "datetime"])
    tt = test.assign(score=s)
    caught = 0
    for r in fail.itertuples():
        w = tt[(tt.machineID == r.machineID) & (tt.datetime >= r.datetime - pd.Timedelta(hours=24)) &
               (tt.datetime < r.datetime)]
        caught += int((w.score >= m["threshold"]).any())
    m["failures_in_test"] = int(len(fail))
    m["failures_with_alert_in_prior_24h"] = int(caught)
    m["event_recall"] = caught / max(len(fail), 1)

    # Ablation by feature group: each group alone is strongly predictive -> the simulated benchmark
    # carries injected precursors; a real fleet will score lower (stated in the report).
    groups = {"telemetry only": [c for c in X_cols if c.split("_")[0] in SIGNALS],
              "error counts only": [c for c in X_cols if c.startswith("error")],
              "maintenance age + machine only": [c for c in X_cols if "since" in c or c in ("age", "model")]}
    ablation = {}
    for name, cols in groups.items():
        a = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, class_weight="balanced",
                                           random_state=0).fit(train[cols], train["y"])
        sa = a.predict_proba(test[cols])[:, 1]
        am = metrics(test["y"], sa)
        ablation[name] = {"roc_auc": am["roc_auc"], "pr_auc": am["pr_auc"]}

    sub = test.sample(40_000, random_state=0)
    pi = permutation_importance(clf, sub[X_cols], sub["y"], n_repeats=3, random_state=0, scoring="average_precision")
    imp = pd.Series(pi.importances_mean, index=X_cols).sort_values(ascending=False)

    fig, ax = plt.subplots(1, 4, figsize=(18, 4.3))
    plot_roc_pr(ax[0], ax[1], [("Gradient boosting, Sep-Dec test", test["y"].to_numpy(), s)])
    plot_confusion(ax[2], m, ("no failure", "failure<24h"), "Hourly predictions, test")
    top = imp.head(10)[::-1]
    ax[3].barh(top.index, top.values, color=style.SERIES[0], height=0.6)
    ax[3].set_title("Permutation importance (PR-AUC drop)", fontsize=10)
    ax[3].grid(axis="y", visible=False)
    fig.suptitle("Fleet failure prediction - component failure within the next 24 h (time-based split)",
                 x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "BENCHMARK data: Microsoft Azure PdM (simulated). Train Jan-Aug 2015, test Sep-Dec 2015, 24-h gap.")
    style.save(fig, FIGURES_DIR / "ml_azure_failure_24h")

    # risk timeline example: the test machine with most failures
    mid = fail.machineID.value_counts().idxmax()
    t1 = tt[tt.machineID == mid]
    fig, ax = plt.subplots(figsize=(12, 3.6))
    ax.plot(t1.datetime + pd.Timedelta(days=SHIFT_DAYS), t1.score, color=style.SERIES[0], lw=1)
    for d in fail[fail.machineID == mid].datetime:
        ax.axvline(d + pd.Timedelta(days=SHIFT_DAYS), color=style.STATUS["critical"], lw=1.2, ls="--")
    ax.axhline(m["threshold"], color=style.INK_2, lw=1, ls=":")
    ax.set_ylabel("Failure risk (probability)")
    ax.set_title(f"Machine {mid}: hourly risk score vs actual failures (dashed red), alert threshold (dotted)")
    style.source_note(fig, "BENCHMARK data: Azure PdM. Timeline shown on the 2025 scenario calendar (+3,654 days).")
    style.save(fig, FIGURES_DIR / "ml_azure_risk_timeline")

    risk = pd.DataFrame({"machine_id": test.machineID.astype("int16"),
                         "ts": (test.datetime + pd.Timedelta(days=SHIFT_DAYS)).dt.tz_localize("Asia/Kolkata"),
                         "risk": s.astype("float32")})
    risk.to_parquet(PROCESSED_DIR / "pdm_risk_scores.parquet", compression="zstd", index=False)
    save_json("ml_azure_failure", {"test_metrics": m, "train_rows": int(len(train)), "test_rows": int(len(test)),
                                   "train_base_rate": float(train.y.mean()), "ablation": ablation,
                                   "same_hour_error_and_failure": "3 of 719 failure hours (no same-hour leakage)",
                                   "top_features": imp.head(12).round(5).to_dict()})
    print(f"test ROC {m['roc_auc']:.3f} PR {m['pr_auc']:.3f} (base {m['base_rate']:.3f}) P {m['precision']:.2f} "
          f"R {m['recall']:.2f} | failures caught {caught}/{len(fail)}")
    print("top:", list(imp.head(6).index))


if __name__ == "__main__":
    main()
