"""Fetch the four public datasets into RAW_DATA_DIR (default: ../raw_datasets).

Idempotent: datasets that are already present are skipped.

    python python/00_download_datasets.py

Datasets
  1. Bosch CNC Machining (real production plant, CC-BY-4.0)          ~1.8 GB, git clone
  2. UMich SMART CNC Mill Tool Wear (real CNC machine)                git clone
  3. Microsoft Azure Predictive Maintenance (benchmark, simulated)   git clone
  4. AI4I 2020 Predictive Maintenance (synthetic benchmark, UCI 601)  zip download
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.paths import AI4I_CSV, AI4I_DIR, RAW_DIR  # noqa: E402

REPOS = {
    "CNC_Machining": "https://github.com/boschresearch/CNC_Machining.git",
    "toolwear_cncmilling": "https://github.com/flyinginte/toolwear_cncmilling.git",
    "telemetry": "https://github.com/avidunixuser/telemetry.git",
}
AI4I_URL = "https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip"
# Optional local copy (e.g. a manual download in the Downloads folder)
AI4I_LOCAL_CANDIDATES = [
    Path.home() / "Downloads" / "ai4i+2020+predictive+maintenance+dataset" / "ai4i2020.csv",
]


def clone(name: str, url: str) -> None:
    target = RAW_DIR / name
    checked_out = target.exists() and any(p.name != ".git" for p in target.iterdir())
    if checked_out:
        print(f"[skip] {name} already cloned at {target}")
        return
    if target.exists():  # interrupted clone: only an empty/partial .git is left
        print(f"[warn] {target} looks like an interrupted clone; delete it and re-run")
        sys.exit(1)
    print(f"[clone] {url} -> {target}")
    subprocess.run(["git", "clone", "--depth", "1", url, str(target)], check=True)


def fetch_ai4i() -> None:
    if AI4I_CSV.exists():
        print(f"[skip] AI4I already at {AI4I_CSV}")
        return
    AI4I_DIR.mkdir(parents=True, exist_ok=True)
    for cand in AI4I_LOCAL_CANDIDATES:
        if cand.exists():
            shutil.copy2(cand, AI4I_CSV)
            print(f"[copy] AI4I from {cand}")
            return
    zip_path = AI4I_DIR / "ai4i2020.zip"
    print(f"[download] {AI4I_URL}")
    urllib.request.urlretrieve(AI4I_URL, zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        member = next(m for m in zf.namelist() if m.endswith("ai4i2020.csv"))
        with zf.open(member) as src, open(AI4I_CSV, "wb") as dst:
            shutil.copyfileobj(src, dst)
    zip_path.unlink()
    print(f"[ok] AI4I extracted to {AI4I_CSV}")


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Raw data directory: {RAW_DIR}")
    for name, url in REPOS.items():
        clone(name, url)
    fetch_ai4i()
    print("Done. Run python/01_verify_datasets.py next.")


if __name__ == "__main__":
    main()
