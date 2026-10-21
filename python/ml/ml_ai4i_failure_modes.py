"""Failure-mode classification on AI4I 2020 (BENCHMARK, synthetic; Matzka 2020, UCI 601).

One classifier per failure mode: TWF (tool wear), HDF (heat dissipation), PWF (power),
OSF (overstrain). RNF is random by construction (0.1 % noise) and is excluded.
Features: product type, air/process temperature, rpm, torque, tool wear, plus three
physics features: temperature difference, mechanical power = torque x omega, and
strain = tool wear x torque. Stratified 5-fold CV (out-of-fold scores), with and without
the physics features. Explanations: mean |SHAP| per feature for each mode.

    python python/ml/ml_ai4i_failure_modes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_predict

from common import FIGURES_DIR, metrics, save_json, style

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import AI4I_CSV  # noqa: E402

MODES = {"TWF": "Tool wear", "HDF": "Heat dissipation", "PWF": "Power", "OSF": "Overstrain"}
BASE = ["type", "air_temp_k", "process_temp_k", "rpm", "torque_nm", "tool_wear_min"]
PHYS = ["temp_diff_k", "power_w", "strain_min_nm"]
SEED = 0


def load() -> pd.DataFrame:
    d = pd.read_csv(AI4I_CSV).rename(columns={"Air temperature [K]": "air_temp_k", "Process temperature [K]": "process_temp_k",
                                              "Rotational speed [rpm]": "rpm", "Torque [Nm]": "torque_nm",
                                              "Tool wear [min]": "tool_wear_min"})
    d["type"] = d["Type"].map({"L": 0, "M": 1, "H": 2})
    d["temp_diff_k"] = d.process_temp_k - d.air_temp_k
    d["power_w"] = d.torque_nm * d.rpm * 2 * np.pi / 60
    d["strain_min_nm"] = d.tool_wear_min * d.torque_nm
    return d


def rf() -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=300, min_samples_leaf=2, class_weight="balanced_subsample",
                                  random_state=SEED, n_jobs=-1)


def main() -> None:
    style.apply()
    d = load()
    cv = StratifiedKFold(5, shuffle=True, random_state=SEED)
    res, shap_imp = {}, {}
    for mode in MODES:
        y = d[mode].to_numpy()
        row = {}
        for name, cols in (("base features", BASE), ("base + physics features", BASE + PHYS)):
            s = cross_val_predict(rf(), d[cols], y, cv=cv, method="predict_proba")[:, 1]
            row[name] = metrics(y, s)
        res[mode] = row
        model = rf().fit(d[BASE + PHYS], y)
        sample = d[BASE + PHYS].sample(1500, random_state=SEED)
        sv = shap.TreeExplainer(model).shap_values(sample, check_additivity=False)
        sv = sv[..., 1] if np.ndim(sv) == 3 else (sv[1] if isinstance(sv, list) else sv)
        shap_imp[mode] = pd.Series(np.abs(sv).mean(axis=0), index=BASE + PHYS)
        print(f"{mode}: n_pos={int(y.sum())}  PR-AUC base {row['base features']['pr_auc']:.3f} -> "
              f"+physics {row['base + physics features']['pr_auc']:.3f}  "
              f"(ROC {row['base + physics features']['roc_auc']:.3f})  top SHAP: {shap_imp[mode].idxmax()}")

    # Figure: PR-AUC with / without physics features + SHAP heatmap
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [1, 1.3]})
    x = np.arange(len(MODES))
    for i, name in enumerate(("base features", "base + physics features")):
        vals = [res[m][name]["pr_auc"] for m in MODES]
        b = ax[0].bar(x + (i - 0.5) * 0.36, vals, width=0.34, color=style.SERIES[i], label=name)
        for bar, v in zip(b, vals):
            ax[0].text(bar.get_x() + bar.get_width() / 2, v + 0.01, f"{v:.2f}", ha="center", fontsize=8.5,
                       color=style.INK_2)
    ax[0].set_xticks(x, [f"{m}\n{MODES[m]}\n(n={int(d[m].sum())})" for m in MODES], fontsize=9)
    ax[0].set_ylim(0, 1.1)
    ax[0].set_ylabel("PR-AUC (5-fold out-of-fold)")
    ax[0].set_title("Failure-mode detection: effect of physics features")
    ax[0].legend(loc="upper left", fontsize=8.5)
    ax[0].grid(axis="x", visible=False)
    h = pd.DataFrame(shap_imp).T
    h = h.div(h.sum(axis=1), axis=0)
    im = ax[1].imshow(h.to_numpy(), cmap="Blues", aspect="auto", vmin=0)
    ax[1].set_xticks(range(h.shape[1]), h.columns, rotation=35, ha="right", fontsize=9)
    ax[1].set_yticks(range(len(h)), [f"{m} {MODES[m]}" for m in h.index])
    for i in range(h.shape[0]):
        for j in range(h.shape[1]):
            ax[1].text(j, i, f"{h.iat[i, j]:.0%}", ha="center", va="center", fontsize=8,
                       color="white" if h.iat[i, j] > 0.35 else style.INK)
    ax[1].grid(False)
    ax[1].set_title("Share of mean |SHAP| per feature (which signal explains each mode)")
    fig.colorbar(im, ax=ax[1], shrink=0.85, label="share of attribution")
    fig.suptitle("AI4I 2020 - failure-mode classification and explanation", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "BENCHMARK data: AI4I 2020 (synthetic, CC-BY-4.0). RNF excluded (random by design). Physics features DERIVED.")
    style.save(fig, FIGURES_DIR / "ml_ai4i_failure_modes")
    save_json("ml_ai4i_failure_modes", {"metrics": res, "shap_share": h.round(4).to_dict("index")})


if __name__ == "__main__":
    main()
