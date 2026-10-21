"""Shared helpers for the ML showcase: metrics, consistent ROC/PR/confusion plots, result files."""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

# harmless joblib/sklearn config-propagation notice, emitted once per parallel job
warnings.filterwarnings("ignore", message=".*sklearn.utils.parallel.delayed.*")

import matplotlib.pyplot as plt
import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, f1_score, precision_recall_curve,
                             roc_auc_score, roc_curve)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import style  # noqa: E402,F401
from utils.paths import FIGURES_DIR, PROCESSED_DIR, REPO_ROOT  # noqa: E402,F401

RESULTS_DIR = REPO_ROOT / "docs" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def metrics(y: np.ndarray, score: np.ndarray, threshold: float | None = None) -> dict:
    """ROC-AUC, PR-AUC (average precision), base rate; F1/confusion at a threshold
    (default: threshold maximising F1 on the given data, reported as such)."""
    y = np.asarray(y).astype(int)
    out = {"n": int(len(y)), "positives": int(y.sum()), "base_rate": float(y.mean()),
           "roc_auc": float(roc_auc_score(y, score)), "pr_auc": float(average_precision_score(y, score))}
    if threshold is None:
        p, r, t = precision_recall_curve(y, score)
        f1 = 2 * p * r / np.clip(p + r, 1e-12, None)
        threshold = float(t[np.argmax(f1[:-1])]) if len(t) else 0.5
        out["threshold_rule"] = "max-F1"
    pred = (score >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    out.update({"threshold": float(threshold), "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
                "precision": float(tp / max(tp + fp, 1)), "recall": float(tp / max(tp + fn, 1)),
                "f1": float(f1_score(y, pred, zero_division=0))})
    return out


def plot_roc_pr(ax_roc, ax_pr, curves: list[tuple[str, np.ndarray, np.ndarray]]) -> None:
    """curves: (label, y_true, score). Colours follow list order (fixed slots)."""
    base = None
    for i, (label, y, s) in enumerate(curves):
        fpr, tpr, _ = roc_curve(y, s)
        p, r, _ = precision_recall_curve(y, s)
        c = style.SERIES[i]
        ax_roc.plot(fpr, tpr, color=c, label=f"{label} (AUC {roc_auc_score(y, s):.2f})")
        ax_pr.plot(r, p, color=c, label=f"{label} (AP {average_precision_score(y, s):.2f})")
        base = np.mean(y)
    ax_roc.plot([0, 1], [0, 1], color=style.AXIS, lw=1, ls="--")
    ax_pr.axhline(base, color=style.AXIS, lw=1, ls="--")
    ax_roc.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC curve")
    ax_pr.set(xlabel="Recall", ylabel="Precision", title="Precision-recall curve")
    for ax in (ax_roc, ax_pr):
        ax.legend(loc="lower right" if ax is ax_roc else "upper right", fontsize=8)
        ax.set_xlim(-0.01, 1.01), ax.set_ylim(-0.01, 1.02)


def plot_confusion(ax, m: dict, labels=("negative", "positive"), title: str = "Confusion matrix") -> None:
    cm = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
    ax.imshow(cm, cmap="Blues", vmin=0, vmax=max(cm.max(), 1) * 1.3)
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center", fontsize=11,
                    color="white" if cm[i, j] > cm.max() * 0.6 else style.INK)
    ax.set_xticks([0, 1], [f"pred {labels[0]}", f"pred {labels[1]}"])
    ax.set_yticks([0, 1], [f"true {labels[0]}", f"true {labels[1]}"])
    ax.grid(False)
    ax.set_title(f"{title}\n(threshold {m['threshold']:.3g}, P={m['precision']:.2f}, R={m['recall']:.2f})", fontsize=10)


def save_json(name: str, obj: dict) -> None:
    (RESULTS_DIR / f"{name}.json").write_text(json.dumps(obj, indent=2, default=float))
