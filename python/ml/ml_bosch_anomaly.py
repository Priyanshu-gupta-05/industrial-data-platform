"""Vibration anomaly detection on REAL Bosch CNC data (file = one machining operation).

  1. Isolation Forest trained on GOOD operations only (unsupervised, as deployable at the edge
     where bad examples are rare), evaluated on held-out good + all bad.
  2. Supervised baseline: Random Forest, stratified 5-fold CV (out-of-fold scores).
  3. Cross-machine generalisation (the challenge highlighted by Tnani et al. 2022):
     train on M01 -> test on M02 and M03, with and without per-machine feature
     normalisation (z-score using each machine's own median/IQR, label-free).

Inputs : data/processed/bosch_features_file.parquet (from python/edge/bosch_features.py)
Outputs: docs/results/ml_bosch_anomaly.json, docs/figures/ml_bosch_*.png

    python python/ml/ml_bosch_anomaly.py
"""
from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split
from sklearn.preprocessing import StandardScaler

from common import FIGURES_DIR, PROCESSED_DIR, metrics, plot_confusion, plot_roc_pr, save_json, style

SEED = 0


def load() -> tuple[pd.DataFrame, list[str]]:
    fl = pd.read_parquet(PROCESSED_DIR / "bosch_features_file.parquet")
    feats = [c for c in fl.columns if "__" in c]
    fl[feats] = fl[feats].replace([np.inf, -np.inf], np.nan).fillna(fl[feats].median())
    return fl, feats


def per_machine_norm(df: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Label-free domain normalisation: robust z-score within each machine."""
    out = df.copy()
    g = df.groupby("machine")[feats]
    med, q1, q3 = g.transform("median"), g.transform(lambda s: s.quantile(0.25)), g.transform(lambda s: s.quantile(0.75))
    out[feats] = (df[feats] - med) / (q3 - q1).replace(0, 1)
    return out


def isolation_forest(fl: pd.DataFrame, feats: list[str]) -> tuple[dict, np.ndarray, np.ndarray]:
    good, bad = fl[fl.label == "good"], fl[fl.label == "bad"]
    g_tr, g_te = train_test_split(good, test_size=0.3, random_state=SEED, stratify=good.machine)
    sc = StandardScaler().fit(g_tr[feats])
    iso = IsolationForest(n_estimators=400, contamination="auto", random_state=SEED).fit(sc.transform(g_tr[feats]))
    test = pd.concat([g_te, bad])
    y = (test.label == "bad").to_numpy()
    s = -iso.score_samples(sc.transform(test[feats]))
    return metrics(y, s), y, s


def random_forest_cv(fl: pd.DataFrame, feats: list[str]) -> tuple[dict, np.ndarray, np.ndarray, pd.Series]:
    y = (fl.label == "bad").to_numpy()
    rf = RandomForestClassifier(n_estimators=500, class_weight="balanced_subsample", min_samples_leaf=2,
                                random_state=SEED, n_jobs=-1)
    s = cross_val_predict(rf, fl[feats], y, cv=StratifiedKFold(5, shuffle=True, random_state=SEED),
                          method="predict_proba")[:, 1]
    imp = pd.Series(rf.fit(fl[feats], y).feature_importances_, index=feats).sort_values(ascending=False)
    return metrics(y, s), y, s, imp


def cross_machine(fl: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    rows = []
    for norm in (False, True):
        d = per_machine_norm(fl, feats) if norm else fl
        tr = d[d.machine == "M01"]
        rf = RandomForestClassifier(n_estimators=500, class_weight="balanced_subsample", min_samples_leaf=2,
                                    random_state=SEED, n_jobs=-1).fit(tr[feats], tr.label == "bad")
        g = tr[tr.label == "good"]
        sc = StandardScaler().fit(g[feats])
        iso = IsolationForest(n_estimators=400, random_state=SEED).fit(sc.transform(g[feats]))
        for target in ("M02", "M03"):
            te = d[d.machine == target]
            y = (te.label == "bad").to_numpy()
            for model, s in (("Random Forest", rf.predict_proba(te[feats])[:, 1]),
                             ("Isolation Forest", -iso.score_samples(sc.transform(te[feats])))):
                m = metrics(y, s)
                rows.append({"train": "M01", "test": target, "model": model,
                             "normalisation": "per-machine robust z" if norm else "none",
                             "roc_auc": m["roc_auc"], "pr_auc": m["pr_auc"], "bad_in_test": m["positives"]})
    return pd.DataFrame(rows)


def temporal(fl: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """Train on 2019 recordings, test on 2021 (bad files cluster in Feb-2019, so a random split
    could partly learn the recording period; this split cannot)."""
    tr, te = fl[fl.year == 2019], fl[fl.year == 2021]
    y = (te.label == "bad").to_numpy()
    rf = RandomForestClassifier(n_estimators=500, class_weight="balanced_subsample", min_samples_leaf=2,
                                random_state=SEED, n_jobs=-1).fit(tr[feats], tr.label == "bad")
    g = tr[tr.label == "good"]
    sc = StandardScaler().fit(g[feats])
    iso = IsolationForest(n_estimators=400, random_state=SEED).fit(sc.transform(g[feats]))
    rows = []
    for model, s in (("Random Forest", rf.predict_proba(te[feats])[:, 1]),
                     ("Isolation Forest", -iso.score_samples(sc.transform(te[feats])))):
        m = metrics(y, s)
        rows.append({"train": "2019 (all machines)", "test": "2021 (all machines)", "model": model,
                     "roc_auc": m["roc_auc"], "pr_auc": m["pr_auc"], "bad_in_test": m["positives"],
                     "n_test": m["n"]})
    return pd.DataFrame(rows)


def figures(iso_m, y_iso, s_iso, rf_m, y_rf, s_rf, imp: pd.Series, xm: pd.DataFrame) -> None:
    fig, ax = plt.subplots(1, 4, figsize=(18, 4.3), gridspec_kw={"width_ratios": [1, 1, 0.8, 1.2]})
    plot_roc_pr(ax[0], ax[1], [("Isolation Forest (good-only)", y_iso, s_iso), ("Random Forest (5-fold CV)", y_rf, s_rf)])
    plot_confusion(ax[2], rf_m, ("good", "bad"), "Random Forest, out-of-fold")
    top = imp.head(10)[::-1]
    ax[3].barh([t.replace("__", " ") for t in top.index], top.values, color=style.SERIES[0], height=0.6)
    ax[3].set_title("Top-10 feature importance (RF, impurity)", fontsize=10)
    ax[3].set_xlabel("Importance")
    ax[3].grid(axis="y", visible=False)
    fig.suptitle("Bosch vibration anomaly detection - good vs bad machining operations (1,702 files)", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "REAL data: Bosch CNC Machining (CC-BY-4.0). File-level aggregates of 1-s edge features (DERIVED).")
    style.save(fig, FIGURES_DIR / "ml_bosch_roc_pr_confusion")

    fig, ax = plt.subplots(figsize=(9, 4))
    piv = xm.pivot_table(index=["model", "test"], columns="normalisation", values="roc_auc")
    labels = [f"{m}\nM01 -> {t}" for m, t in piv.index]
    x = np.arange(len(piv))
    for i, col in enumerate(["none", "per-machine robust z"]):
        b = ax.bar(x + (i - 0.5) * 0.36, piv[col], width=0.34, color=style.SERIES[i], label=f"normalisation: {col}")
        for bar, v in zip(b, piv[col]):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=8.5, color=style.INK_2)
    ax.axhline(0.5, color=style.AXIS, ls="--", lw=1)
    ax.set_xticks(x, labels, fontsize=9)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("ROC-AUC on unseen machine")
    ax.set_title("Cross-machine generalisation: train on M01, test on M02 / M03")
    ax.legend(loc="upper left", fontsize=8.5, ncol=2)
    ax.grid(axis="x", visible=False)
    style.source_note(fig, "REAL data: Bosch CNC Machining. 0.5 = chance. Normalisation uses unlabeled data of each machine.")
    style.save(fig, FIGURES_DIR / "ml_bosch_cross_machine")


def main() -> None:
    style.apply()
    fl, feats = load()
    iso_m, y_iso, s_iso = isolation_forest(fl, feats)
    rf_m, y_rf, s_rf, imp = random_forest_cv(fl, feats)
    xm = cross_machine(fl, feats)
    tm = temporal(fl, feats)
    figures(iso_m, y_iso, s_iso, rf_m, y_rf, s_rf, imp, xm)
    res = {"isolation_forest_good_only": iso_m, "random_forest_cv5": rf_m,
           "top_features": imp.head(10).round(4).to_dict(), "cross_machine": xm.round(4).to_dict("records"),
           "temporal_2019_to_2021": tm.round(4).to_dict("records"),
           "caveat": "39 of 70 bad files are from Feb-2019; temporal hold-out reported to bound period leakage"}
    save_json("ml_bosch_anomaly", res)
    print(f"IsolationForest ROC {iso_m['roc_auc']:.3f} PR {iso_m['pr_auc']:.3f} | "
          f"RF ROC {rf_m['roc_auc']:.3f} PR {rf_m['pr_auc']:.3f} P {rf_m['precision']:.2f} R {rf_m['recall']:.2f}")
    print(xm.round(3).to_string(index=False))
    print(tm.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
