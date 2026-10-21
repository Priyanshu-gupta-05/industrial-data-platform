"""Edge feature extraction on the REAL Bosch 2 kHz tri-axial vibration data.

What an edge gateway would do next to each machining centre: cut the raw
2 kHz X/Y/Z acceleration into 1-second windows and send only compact
features to the cloud. Every one of the 1,702 Bosch files is processed.

Per axis and 1-s window (2,000 samples):
  time domain  : mean, RMS (AC), peak, peak-to-peak, crest factor, kurtosis, skewness
  frequency    : band energy fractions 0-50 / 50-150 / 150-300 / 300-500 / 500-1000 Hz,
                 dominant frequency, spectral centroid
-> 14 features x 3 axes = 42 float32 values per second instead of 6,000 samples.

Outputs
  data/processed/bosch_features_1s.parquet   (window-level features, DERIVED)
  data/processed/bosch_features_file.parquet (file-level aggregates, DERIVED)
  data/samples/bosch_sample_raw.parquet      (small REAL raw excerpt: one good + one bad file)
  docs/results/edge_reduction.json           (measured reduction ratios)
  docs/figures/edge_*.png

    python python/edge/bosch_features.py
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import Patch
from scipy import signal, stats
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import style  # noqa: E402
from utils.paths import BOSCH_DIR, FIGURES_DIR, PROCESSED_DIR, REPO_ROOT, SAMPLES_DIR  # noqa: E402

FS = 2000                      # Hz, Bosch sampling rate
WIN = FS                       # 1-second windows
AXES = ["x", "y", "z"]
BANDS = [(0, 50), (50, 150), (150, 300), (300, 500), (500, 1000)]
NAME_RE = re.compile(r"(M\d{2})_([A-Za-z]{3})_(\d{4})_(OP\d{2})_(\d{3})\.h5$")
RESULTS_DIR = REPO_ROOT / "docs" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
FEATURE_NAMES = (["mean", "rms", "peak", "p2p", "crest", "kurtosis", "skewness"]
                 + [f"band_{lo}_{hi}" for lo, hi in BANDS] + ["dom_freq", "centroid"])


def window_features(x: np.ndarray) -> np.ndarray:
    """x: (n_windows, WIN) one axis -> (n_windows, 14) features. Fully vectorised."""
    mean = x.mean(axis=1)
    ac = x - mean[:, None]
    rms = np.sqrt((ac ** 2).mean(axis=1))
    peak = np.abs(ac).max(axis=1)
    p2p = x.max(axis=1) - x.min(axis=1)
    crest = peak / np.maximum(rms, 1e-9)
    kurt = stats.kurtosis(ac, axis=1, fisher=True)
    skew = stats.skew(ac, axis=1)
    spec = np.abs(np.fft.rfft(ac * np.hanning(WIN), axis=1)) ** 2   # 1 Hz bins, 0..1000 Hz
    freqs = np.fft.rfftfreq(WIN, 1 / FS)
    total = spec[:, 1:].sum(axis=1) + 1e-12
    bands = [spec[:, (freqs >= lo) & (freqs < hi) & (freqs > 0)].sum(axis=1) / total for lo, hi in BANDS]
    dom = freqs[1:][spec[:, 1:].argmax(axis=1)]
    centroid = (spec[:, 1:] * freqs[1:]).sum(axis=1) / total
    return np.column_stack([mean, rms, peak, p2p, crest, kurt, skew, *bands, dom, centroid]).astype(np.float32)


def list_files() -> pd.DataFrame:
    rows = []
    for f in sorted(BOSCH_DIR.glob("M0*/OP*/*/*.h5")):
        m = NAME_RE.search(f.name)
        # file names repeat across good/ and bad/ folders, so the id is the relative path
        rows.append({"path": f, "file": "/".join(f.parts[-4:]), "machine": f.parts[-4], "operation": f.parts[-3],
                     "label": f.parts[-2], "month": m.group(2), "year": int(m.group(3))})
    return pd.DataFrame(rows)


def extract_all(files: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out, raw_bytes_disk, raw_samples = [], 0, 0
    t0 = time.perf_counter()
    for i, r in enumerate(files.itertuples()):
        with h5py.File(r.path, "r") as h:
            a = h["vibration_data"][:].astype(np.float32)
        raw_bytes_disk += r.path.stat().st_size
        raw_samples += len(a)
        n = len(a) // WIN
        if n == 0:
            continue
        a = a[: n * WIN].reshape(n, WIN, 3)
        feats = np.hstack([window_features(a[:, :, k]) for k in range(3)])
        df = pd.DataFrame(feats, columns=[f"{ax}_{f}" for ax in AXES for f in FEATURE_NAMES])
        df.insert(0, "window_s", np.arange(n, dtype=np.int32))
        for col in ["year", "month", "label", "operation", "machine", "file"]:
            df.insert(0, col, getattr(r, col))
        out.append(df)
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(files)} files, {time.perf_counter() - t0:.0f} s")
    feats = pd.concat(out, ignore_index=True)
    for c in ["machine", "operation", "label", "month", "file"]:
        feats[c] = feats[c].astype("category")
    stats_ = {"files": len(files), "raw_samples_per_axis": int(raw_samples), "raw_bytes_on_disk_h5": int(raw_bytes_disk),
              "raw_hours": raw_samples / FS / 3600, "windows": len(feats),
              "extraction_seconds": round(time.perf_counter() - t0, 1)}
    return feats, stats_


def file_level(feats: pd.DataFrame) -> pd.DataFrame:
    num = [c for c in feats.columns if c[:2] in ("x_", "y_", "z_")]
    g = feats.groupby("file", observed=True)
    agg = g[num].agg(["mean", "std", "max"])
    agg.columns = [f"{a}__{b}" for a, b in agg.columns]
    meta = g[["machine", "operation", "label", "month", "year"]].first()
    meta["duration_s"] = g.size()
    return meta.join(agg).reset_index()


def reduction(stats_: dict, feats_path: Path) -> dict:
    # Bosch stores float64; a gateway would transmit float32, so float32 is the conservative baseline
    raw_bps = FS * 3 * 4                         # float32 x 3 axes
    feat_bps = len(FEATURE_NAMES) * 3 * 4        # 42 float32 per second
    fleet = 100
    red = {
        **stats_,
        "raw_bytes_per_second_float64_as_stored": FS * 3 * 8,
        "raw_bytes_per_second_float32": raw_bps,
        "feature_bytes_per_second_float32": feat_bps,
        "reduction_ratio_per_second": raw_bps / feat_bps,
        "raw_bytes_in_memory_float32": stats_["raw_samples_per_axis"] * 3 * 4,
        "features_parquet_bytes": feats_path.stat().st_size,
        "measured_reduction_vs_raw_float32": stats_["raw_samples_per_axis"] * 12 / feats_path.stat().st_size,
        "measured_reduction_vs_h5_on_disk": stats_["raw_bytes_on_disk_h5"] / feats_path.stat().st_size,
        "fleet_raw_mbps": fleet * raw_bps * 8 / 1e6,
        "fleet_feature_mbps": fleet * feat_bps * 8 / 1e6,
        "fleet_raw_TB_per_year": fleet * raw_bps * 365 * 86400 / 1e12,
        "fleet_feature_TB_per_year": fleet * feat_bps * 365 * 86400 / 1e12,
    }
    return red


def separability(feats: pd.DataFrame) -> pd.DataFrame:
    """Univariate ROC-AUC of each window feature for good vs bad (|AUC-0.5| shows separation)."""
    y = (feats.label == "bad").astype(int).to_numpy()
    rows = []
    for c in [c for c in feats.columns if c[:2] in ("x_", "y_", "z_")]:
        v = feats[c].to_numpy()
        ok = np.isfinite(v)
        auc = roc_auc_score(y[ok], v[ok])
        rows.append({"feature": c, "auc": auc, "separation": abs(auc - 0.5) * 2})
    return pd.DataFrame(rows).sort_values("separation", ascending=False)


# ------------------------------------------------------------------ figures
def pick_pair(files: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """A bad file and a good file of the same machine + operation (fair comparison)."""
    bad = files[files.label == "bad"].iloc[0]
    good = files[(files.label == "good") & (files.machine == bad.machine) & (files.operation == bad.operation)].iloc[0]
    return good, bad


def load(path: Path) -> np.ndarray:
    with h5py.File(path, "r") as h:
        return h["vibration_data"][:]


def fig_waveform_vs_features(good: pd.Series, bad: pd.Series, feats: pd.DataFrame) -> None:
    fig, axes = plt.subplots(3, 2, figsize=(12, 7.5), sharex="col",
                             gridspec_kw={"height_ratios": [1.3, 1, 1]})
    for col, (r, color) in enumerate([(good, style.LABEL_COLORS["good"]), (bad, style.LABEL_COLORS["bad"])]):
        a = load(r.path)
        t = np.arange(len(a)) / FS
        axes[0, col].plot(t, a[:, 2], lw=0.35, color=color)
        axes[0, col].set_title(f"{r.label.upper()}: {r.file}  (raw Z, 2 kHz)", fontsize=10)
        axes[0, col].set_ylabel("Acceleration (raw units)")
        f = feats[feats.file == r.file]
        axes[1, col].plot(f.window_s + 0.5, f.z_rms, color=color, marker="o", ms=3)
        axes[1, col].set_ylabel("Z RMS (1-s feature)")
        axes[2, col].plot(f.window_s + 0.5, f.z_kurtosis, color=color, marker="o", ms=3)
        axes[2, col].set_ylabel("Z kurtosis (1-s)")
        axes[2, col].set_xlabel("Time (s)")
        n_raw = len(a) * 3
        axes[0, col].text(0.99, 0.95, f"{n_raw:,} raw values -> {len(f) * 42:,} feature values",
                          transform=axes[0, col].transAxes, ha="right", va="top", fontsize=8.5, color=style.INK_2)
    fig.suptitle("Edge demo - raw 2 kHz vibration vs 1-second features (same machine & operation)", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "REAL data: Bosch CNC Machining dataset (CC-BY-4.0). Features DERIVED at the edge.")
    style.save(fig, FIGURES_DIR / "edge_waveform_vs_features")


def fig_spectrogram(good: pd.Series, bad: pd.Series) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.2), sharey=True)
    for ax, r in zip(axes, [good, bad]):
        a = load(r.path)[:, 2]
        f, t, s = signal.spectrogram(a - a.mean(), fs=FS, nperseg=512, noverlap=384)
        im = ax.pcolormesh(t, f, 10 * np.log10(s + 1e-12), shading="auto", cmap="Blues",
                           vmin=np.percentile(10 * np.log10(s + 1e-12), 5))
        ax.set_title(f"{r.label.upper()}: {r.file}", fontsize=10)
        ax.set_xlabel("Time (s)")
        ax.grid(False)
    axes[0].set_ylabel("Frequency (Hz)")
    cb = fig.colorbar(im, ax=axes, shrink=0.9, pad=0.01)
    cb.set_label("Power spectral density (dB)")
    fig.suptitle("Edge demo - spectrogram of Z-axis vibration (good vs bad)", x=0.01, ha="left")
    style.source_note(fig, "REAL data: Bosch CNC Machining dataset, 2 kHz. Welch segments of 512 samples.", y=-0.04)
    style.save(fig, FIGURES_DIR / "edge_spectrogram_good_vs_bad")


def fig_embedding(fl: pd.DataFrame, feats: pd.DataFrame) -> dict:
    num_w = [c for c in feats.columns if c[:2] in ("x_", "y_", "z_")]
    rng = np.random.default_rng(0)
    bad_idx = np.flatnonzero(feats.label.to_numpy() == "bad")
    good_idx = np.flatnonzero(feats.label.to_numpy() == "good")
    sel = np.concatenate([bad_idx, rng.choice(good_idx, size=min(len(good_idx), 3 * len(bad_idx)), replace=False)])
    w = feats.iloc[sel]
    Xw = StandardScaler().fit_transform(np.nan_to_num(w[num_w].to_numpy()))
    num_f = [c for c in fl.columns if "__" in c]
    Xf = StandardScaler().fit_transform(np.nan_to_num(fl[num_f].to_numpy()))

    pca_f = PCA(n_components=2, random_state=0).fit(Xf)
    Pf = pca_f.transform(Xf)
    tsne = TSNE(n_components=2, perplexity=40, init="pca", random_state=0).fit_transform(Xw)

    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))
    markers = {"M01": "o", "M02": "s", "M03": "^"}
    for lab in ["good", "bad"]:
        m = fl.label == lab
        for mach, mk in markers.items():
            mm = m & (fl.machine == mach)
            axes[0].scatter(Pf[mm, 0], Pf[mm, 1], s=14 if lab == "good" else 30, marker=mk, alpha=0.55 if lab == "good" else 0.95,
                            color=style.LABEL_COLORS[lab], edgecolor=style.SURFACE, linewidth=0.5)
        mw = (w.label == lab).to_numpy()
        axes[1].scatter(tsne[mw, 0], tsne[mw, 1], s=3 if lab == "good" else 5, alpha=0.4 if lab == "good" else 0.7,
                        color=style.LABEL_COLORS[lab], linewidth=0)
    axes[0].set_title("PCA of file-level features (1,702 operations)", fontsize=10)
    axes[0].set_xlabel(f"PC1 ({pca_f.explained_variance_ratio_[0]:.0%} var.)")
    axes[0].set_ylabel(f"PC2 ({pca_f.explained_variance_ratio_[1]:.0%} var.)")
    axes[1].set_title(f"t-SNE of 1-s window features (n={len(w):,})", fontsize=10)
    axes[1].set_xticks([]), axes[1].set_yticks([])
    # per-machine colouring of the same file-level PCA: shows the machine shift the paper describes
    for k, mach in enumerate(markers):
        mm = (fl.machine == mach).to_numpy()
        axes[2].scatter(Pf[mm, 0], Pf[mm, 1], s=10, alpha=0.6, color=style.SERIES[[0, 1, 2][k]], label=mach, linewidth=0)
    axes[2].set_title("Same PCA coloured by machine (domain shift)", fontsize=10)
    axes[2].set_xlabel("PC1"), axes[2].set_ylabel("PC2")
    axes[2].legend(title="Machine", loc="best")
    handles = [Patch(color=style.LABEL_COLORS["good"], label="good"), Patch(color=style.LABEL_COLORS["bad"], label="bad")]
    axes[0].legend(handles=handles, title="Label", loc="best")
    axes[1].legend(handles=handles, title="Label", loc="best")
    fig.suptitle("Edge demo - good vs bad operations in feature space", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "REAL data: Bosch CNC Machining. Features DERIVED; good windows subsampled 3:1 for t-SNE.")
    style.save(fig, FIGURES_DIR / "edge_feature_space_pca_tsne")
    return {"pca_file_level_var_explained": pca_f.explained_variance_ratio_.round(3).tolist(), "tsne_points": len(w)}


def fig_feature_boxes(feats: pd.DataFrame, sep: pd.DataFrame) -> None:
    top = sep.feature.head(6).tolist()
    fig, axes = plt.subplots(1, 6, figsize=(15, 3.8))
    for ax, c in zip(axes, top):
        data = [feats.loc[feats.label == lab, c].dropna().to_numpy() for lab in ["good", "bad"]]
        bp = ax.boxplot(data, tick_labels=["good", "bad"], showfliers=False, patch_artist=True, widths=0.55,
                        medianprops={"color": style.INK})
        for patch, lab in zip(bp["boxes"], ["good", "bad"]):
            patch.set_facecolor(style.LABEL_COLORS[lab]), patch.set_alpha(0.75), patch.set_edgecolor(style.SURFACE)
        auc = sep.set_index("feature").loc[c, "auc"]
        ax.set_title(f"{c}\nAUC {auc:.2f}", fontsize=9)
        ax.grid(axis="x", visible=False)
    fig.suptitle("Edge demo - six most discriminative 1-s features (univariate ROC-AUC, good vs bad)", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, "REAL data: Bosch CNC Machining. Whiskers 1.5 IQR, outliers hidden. Units: raw accel. units / Hz / ratio.")
    style.save(fig, FIGURES_DIR / "edge_top_features_boxplot")


def fig_reduction(red: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.8))
    vals = [red["raw_bytes_per_second_float32"], red["feature_bytes_per_second_float32"]]
    b = axes[0].barh(["Raw 2 kHz x 3 axes", "Edge features (42 / s)"], vals,
                     color=[style.SERIES[7], style.SERIES[2]], height=0.55)
    axes[0].set_xscale("log")
    axes[0].set_xlabel("Bytes per machine-second (log)")
    axes[0].set_title(f"Per machine: {red['reduction_ratio_per_second']:.0f}x less data", fontsize=10)
    for bar, v in zip(b, vals):
        axes[0].text(v * 1.1, bar.get_y() + bar.get_height() / 2, f"{v:,} B", va="center", fontsize=9, color=style.INK_2)
    axes[0].set_xlim(50, vals[0] * 8)
    vals2 = [red["fleet_raw_TB_per_year"], red["fleet_feature_TB_per_year"]]
    b2 = axes[1].barh(["Raw", "Edge features"], vals2, color=[style.SERIES[7], style.SERIES[2]], height=0.55)
    axes[1].set_xscale("log")
    axes[1].set_xlabel("TB per year, 100-machine fleet (log)")
    axes[1].set_title(f"Fleet uplink: {red['fleet_raw_mbps']:.1f} Mbps -> {red['fleet_feature_mbps']:.2f} Mbps", fontsize=10)
    for bar, v in zip(b2, vals2):
        axes[1].text(v * 1.1, bar.get_y() + bar.get_height() / 2, f"{v:,.2f} TB", va="center", fontsize=9, color=style.INK_2)
    axes[1].set_xlim(vals2[1] / 3, vals2[0] * 8)
    for ax in axes:
        ax.grid(axis="y", visible=False)
    fig.suptitle("Edge demo - measured data reduction from feature extraction", x=0.01, ha="left")
    fig.tight_layout()
    style.source_note(fig, f"Measured on all {red['files']:,} Bosch files ({red['raw_hours']:.1f} h of 2 kHz data): "
                           f"{red['measured_reduction_vs_raw_float32']:.0f}x vs raw float32, "
                           f"{red['measured_reduction_vs_h5_on_disk']:.0f}x vs HDF5 on disk (features stored as Parquet+Zstd).")
    style.save(fig, FIGURES_DIR / "edge_data_reduction")


def save_samples(good: pd.Series, bad: pd.Series) -> None:
    frames = []
    for r in (good, bad):
        a = load(r.path)[: 10 * FS]  # first 10 s
        frames.append(pd.DataFrame({"file": r.file, "label": r.label, "machine": r.machine, "operation": r.operation,
                                    "t_s": np.arange(len(a)) / FS, "acc_x": a[:, 0], "acc_y": a[:, 1], "acc_z": a[:, 2]}))
    pd.concat(frames).to_parquet(SAMPLES_DIR / "bosch_sample_raw.parquet", compression="zstd", index=False)


def main() -> None:
    style.apply()
    files = list_files()
    print(f"Bosch files: {len(files)}  ({(files.label == 'bad').sum()} bad)")
    feats, stats_ = extract_all(files)
    fpath = PROCESSED_DIR / "bosch_features_1s.parquet"
    feats.to_parquet(fpath, compression="zstd", index=False)
    fl = file_level(feats)
    fl.to_parquet(PROCESSED_DIR / "bosch_features_file.parquet", compression="zstd", index=False)

    red = reduction(stats_, fpath)
    sep = separability(feats)
    sep.to_csv(RESULTS_DIR / "edge_feature_separability.csv", index=False)

    good, bad = pick_pair(files)
    save_samples(good, bad)
    fig_waveform_vs_features(good, bad, feats)
    fig_spectrogram(good, bad)
    emb = fig_embedding(fl, feats)
    fig_feature_boxes(feats, sep)
    fig_reduction(red)
    red.update(emb)
    red["top_features_auc"] = sep.head(6).set_index("feature").auc.round(3).to_dict()
    (RESULTS_DIR / "edge_reduction.json").write_text(json.dumps(red, indent=2, default=float))
    print(json.dumps(red, indent=2, default=float))


if __name__ == "__main__":
    main()
