"""Tool-wear and inspection-outcome classification on REAL UMich CNC mill data.

Signals: spindle (S1) current feedback, output power, actual velocity, X/Y axis currents,
during material-removal phases ("Layer ..."), cut into 5-s windows (50 samples at 100 ms).
Experiment settings (feedrate, clamp pressure) are NOT used as features: the model must
read tool condition from the machine signals.

Targets
  worn vs unworn tool         : 18 experiments
  passed visual inspection    : 14 finalized experiments
Validation: Leave-One-Experiment-Out (windows of one experiment never in both train and test),
reported at window level and experiment level (mean window probability per experiment).
Small sample (18 experiments): results are indicative, not production-grade.

    python python/ml/ml_umich_toolwear.py
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.model_selection import LeaveOneGroupOut, StratifiedKFold, cross_val_predict

from common import FIGURES_DIR, metrics, plot_confusion, plot_roc_pr, save_json, style

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import UMICH_DIR  # noqa: E402

SIGNALS = ["S1_CurrentFeedback", "S1_OutputPower", "S1_ActualVelocity", "X1_CurrentFeedback",
           "Y1_CurrentFeedback", "X1_OutputPower", "Y1_OutputPower"]
WIN = 50
SEED = 0


def windows() -> pd.DataFrame:
    train = pd.read_csv(UMICH_DIR / "train.csv")
    rows = []
    for f in sorted(UMICH_DIR.glob("experiment_*.csv")):
        exp = int(f.stem.split("_")[1])
        d = pd.read_csv(f)
        d = d[d.Machining_Process.str.contains("Layer", na=False)].reset_index(drop=True)
        for w in range(len(d) // WIN):
            seg = d.iloc[w * WIN:(w + 1) * WIN]
            feat = {"experiment": exp}
            for s in SIGNALS:
                v = seg[s].to_numpy()
                feat.update({f"{s}_mean": v.mean(), f"{s}_std": v.std(), f"{s}_max": v.max(),
                             f"{s}_p2p": v.max() - v.min()})
            # context the controller itself logs: commanded feedrate (not the label)
            fr = seg["M1_CURRENT_FEEDRATE"].mean()
            feat["CTX_feedrate"] = fr
            feat["CTX_S1_current_per_feed"] = seg["S1_CurrentFeedback"].mean() / max(fr, 1e-6)
            feat["CTX_S1_power_per_feed"] = seg["S1_OutputPower"].mean() / max(fr, 1e-6)
            rows.append(feat)
    w = pd.DataFrame(rows).merge(train.rename(columns={"No": "experiment"}), on="experiment")
    w["worn"] = (w.tool_condition == "worn").astype(int)
    w["failed_inspection"] = (w.passed_visual_inspection == "no").astype(int)
    return w


def logo(df: pd.DataFrame, target: str, feats: list[str]) -> tuple[np.ndarray, pd.Series]:
    s = np.zeros(len(df))
    for tr, te in LeaveOneGroupOut().split(df, groups=df.experiment):
        rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced",
                                    random_state=SEED, n_jobs=-1).fit(df.iloc[tr][feats], df.iloc[tr][target])
        s[te] = rf.predict_proba(df.iloc[te][feats])[:, 1]
    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced",
                                random_state=SEED, n_jobs=-1).fit(df[feats], df[target])
    pi = permutation_importance(rf, df[feats], df[target], n_repeats=5, random_state=SEED, scoring="roc_auc")
    return s, pd.Series(pi.importances_mean, index=feats).sort_values(ascending=False)


def main() -> None:
    style.apply()
    w = windows()
    sensor = [c for c in w.columns if c.startswith(("S1_", "X1_", "Y1_"))]
    feats = sensor + [c for c in w.columns if c.startswith("CTX_")]
    res, curves, exp_curves = {}, [], []
    # Ablation: sensor signals alone (feedrate dominates the signal level -> confounded)
    s0, _ = logo(w, "worn", sensor)
    res["ablation_worn_sensor_only"] = metrics(w["worn"], s0)
    print(f"worn, sensor-only: window ROC {res['ablation_worn_sensor_only']['roc_auc']:.3f}")
    # Leakage demonstration: a random window split puts windows of the same experiment in train
    # and test, so the model recognises the run, not the tool condition.
    leaky = cross_val_predict(RandomForestClassifier(n_estimators=300, min_samples_leaf=3, random_state=SEED,
                                                     n_jobs=-1), w[feats], w["worn"],
                              cv=StratifiedKFold(5, shuffle=True, random_state=SEED), method="predict_proba")[:, 1]
    res["leaky_random_window_split_worn"] = metrics(w["worn"], leaky)
    print(f"worn, LEAKY random split: ROC {res['leaky_random_window_split_worn']['roc_auc']:.3f}")
    for target, subset, label in [("worn", w, "Worn tool"),
                                  ("failed_inspection", w[w.machining_finalized == "yes"].reset_index(drop=True),
                                   "Failed inspection")]:
        s, imp = logo(subset, target, feats)
        mw = metrics(subset[target], s)
        e = subset.assign(score=s).groupby("experiment").agg(y=(target, "first"), score=("score", "mean"))
        me = metrics(e.y, e.score, threshold=0.5)
        res[target] = {"windows": mw, "experiments": me, "n_experiments": int(len(e)),
                       "top_permutation_importance": imp.head(8).round(4).to_dict()}
        curves.append((f"{label} (windows)", subset[target].to_numpy(), s))
        exp_curves.append((label, me, imp))
        print(f"{target}: window ROC {mw['roc_auc']:.3f} PR {mw['pr_auc']:.3f} | "
              f"experiment ROC {me['roc_auc']:.3f} acc@0.5 {(me['tp'] + me['tn']) / me['n']:.2f} (n={me['n']})")

    fig, ax = plt.subplots(1, 4, figsize=(18, 4.3))
    curves.append(("Worn tool, LEAKY random split", w["worn"].to_numpy(), leaky))
    plot_roc_pr(ax[0], ax[1], curves)
    plot_confusion(ax[2], exp_curves[0][1], ("unworn", "worn"), "Worn tool, per experiment")
    imp = exp_curves[0][2].head(8)[::-1]
    ax[3].barh(imp.index, imp.values, color=style.SERIES[0], height=0.6)
    ax[3].set_title("Permutation importance (worn tool, ROC-AUC drop)", fontsize=10)
    ax[3].set_xlabel("Mean AUC decrease")
    ax[3].grid(axis="y", visible=False)
    fig.suptitle(f"UMich tool wear - leave-one-experiment-out ({len(w):,} windows of 5 s, 18 experiments)",
                 x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "REAL data: UMich SMART CNC mill. Settings (feedrate, clamp pressure) excluded from features. Small n: indicative.")
    style.save(fig, FIGURES_DIR / "ml_umich_toolwear")
    res["n_windows"] = int(len(w))
    res["window_seconds"] = WIN / 10
    save_json("ml_umich_toolwear", res)


if __name__ == "__main__":
    main()
