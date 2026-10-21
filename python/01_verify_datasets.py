"""Verify that all four raw datasets are present and load correctly.

Prints shape / schema / label summaries for each dataset and writes a
machine-readable inventory to data/reference/dataset_inventory.csv.

    python python/01_verify_datasets.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import h5py
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.paths import AI4I_CSV, AZURE_DIR, BOSCH_DIR, REFERENCE_DIR, UMICH_DIR  # noqa: E402

BOSCH_NAME_RE = re.compile(r"(M\d{2})_([A-Za-z]{3})_(\d{4})_(OP\d{2})_(\d{3})\.h5$")


def verify_bosch() -> dict:
    files = sorted(BOSCH_DIR.glob("M0*/OP*/*/*.h5"))
    if not files:
        raise FileNotFoundError(f"No Bosch .h5 files under {BOSCH_DIR}")
    rows = []
    for f in files:
        m = BOSCH_NAME_RE.search(f.name)
        rows.append({
            "machine": f.parts[-4], "operation": f.parts[-3], "label": f.parts[-2],
            "month": m.group(2) if m else None, "year": int(m.group(3)) if m else None,
            "bytes": f.stat().st_size,
        })
    idx = pd.DataFrame(rows)
    # Open a sample of files to confirm array layout
    with h5py.File(files[0], "r") as h:
        arr = h["vibration_data"]
        shape, dtype = arr.shape, arr.dtype
    total_samples = 0
    for f in files:
        with h5py.File(f, "r") as h:
            total_samples += h["vibration_data"].shape[0]
    print("\n=== 1. Bosch CNC Machining (REAL production plant, CC-BY-4.0) ===")
    print(f"files: {len(files)}  (good={int((idx.label == 'good').sum())}, bad={int((idx.label == 'bad').sum())})")
    print(f"first file: {files[0].name} -> key 'vibration_data' shape={shape} dtype={dtype}")
    print(f"total tri-axial samples: {total_samples:,}  (= {total_samples / 2000 / 3600:.1f} h at 2 kHz)")
    print(f"size on disk: {idx.bytes.sum() / 1e9:.2f} GB")
    print(idx.groupby(["machine", "label"]).size().unstack(fill_value=0))
    return {"dataset": "Bosch CNC Machining", "nature": "real", "files": len(files),
            "rows": total_samples, "bytes": int(idx.bytes.sum())}


def verify_umich() -> dict:
    train = pd.read_csv(UMICH_DIR / "train.csv")
    exps = sorted(UMICH_DIR.glob("experiment_*.csv"))
    n_rows, cols = 0, None
    for f in exps:
        df = pd.read_csv(f)
        n_rows += len(df)
        cols = df.columns if cols is None else cols
    print("\n=== 2. UMich SMART CNC Mill Tool Wear (REAL CNC machine) ===")
    print(f"train.csv: {train.shape}, columns={list(train.columns)}")
    print(train["tool_condition"].value_counts().to_dict(),
          "| passed_visual_inspection:", train["passed_visual_inspection"].value_counts(dropna=False).to_dict())
    print(f"experiments: {len(exps)} files, {n_rows:,} rows x {len(cols)} columns at 100 ms")
    print("spindle columns:", [c for c in cols if c.startswith("S1_")])
    return {"dataset": "UMich SMART CNC Mill Tool Wear", "nature": "real", "files": len(exps) + 1,
            "rows": n_rows, "bytes": sum(f.stat().st_size for f in exps)}


def verify_azure() -> dict:
    tel = pd.read_csv(AZURE_DIR / "telemetry.csv", parse_dates=["datetime"])
    others = {n: pd.read_csv(AZURE_DIR / f"{n}.csv") for n in ("machines", "errors", "maint", "failures")}
    print("\n=== 3. Microsoft Azure Predictive Maintenance (BENCHMARK, simulated by Microsoft) ===")
    print(f"telemetry: {tel.shape}, machines={tel.machineID.nunique()}, "
          f"{tel.datetime.min()} -> {tel.datetime.max()}")
    print(tel.describe().loc[["mean", "min", "max"], ["volt", "rotate", "pressure", "vibration"]].round(2))
    for n, df in others.items():
        print(f"{n}: {df.shape} columns={list(df.columns)}")
    print("error IDs:", sorted(others["errors"].errorID.unique()),
          "| failure components:", sorted(others["failures"].failure.unique()))
    return {"dataset": "Microsoft Azure Predictive Maintenance", "nature": "benchmark (simulated)",
            "files": 5, "rows": len(tel), "bytes": sum((AZURE_DIR / f"{n}.csv").stat().st_size
                                                        for n in ["telemetry", *others])}


def verify_ai4i() -> dict:
    df = pd.read_csv(AI4I_CSV)
    print("\n=== 4. AI4I 2020 Predictive Maintenance (SYNTHETIC benchmark, UCI 601, CC-BY-4.0) ===")
    print(f"shape: {df.shape}")
    print("Type:", df["Type"].value_counts().to_dict(),
          "| failures:", {c: int(df[c].sum()) for c in ["Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF"]})
    return {"dataset": "AI4I 2020 Predictive Maintenance", "nature": "benchmark (synthetic)",
            "files": 1, "rows": len(df), "bytes": AI4I_CSV.stat().st_size}


def main() -> None:
    results, failed = [], []
    for fn in (verify_bosch, verify_umich, verify_azure, verify_ai4i):
        try:
            results.append(fn())
        except Exception as exc:  # report every failure, don't stop at the first
            failed.append(f"{fn.__name__}: {exc}")
    inv = pd.DataFrame(results)
    inv.to_csv(REFERENCE_DIR / "dataset_inventory.csv", index=False)
    print("\n=== Inventory ===")
    print(inv.to_string(index=False))
    if failed:
        print("\nFAILED:\n  " + "\n  ".join(failed))
        sys.exit(1)
    print("\nAll four datasets loaded successfully.")


if __name__ == "__main__":
    main()
