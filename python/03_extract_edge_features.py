"""Pipeline step 03: edge feature extraction (Bosch) + small real samples for the repo.

Runs python/edge/bosch_features.py (all 1,702 Bosch files -> 1-s features) and copies
one short UMich experiment to data/samples/ so the repo carries a small REAL sample.

    python python/03_extract_edge_features.py
"""
from __future__ import annotations

import runpy
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.paths import SAMPLES_DIR, UMICH_DIR  # noqa: E402

if __name__ == "__main__":
    shutil.copy2(UMICH_DIR / "experiment_05.csv", SAMPLES_DIR / "umich_experiment_05_sample.csv")
    shutil.copy2(UMICH_DIR / "train.csv", SAMPLES_DIR / "umich_train.csv")
    runpy.run_path(str(Path(__file__).resolve().parent / "edge" / "bosch_features.py"), run_name="__main__")
