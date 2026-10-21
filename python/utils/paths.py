"""Central path configuration so every script resolves data locations the same way.

Raw datasets live OUTSIDE the repository (they are large and keep their own
licences). By default they sit in a sibling folder `../raw_datasets/`; override
with the environment variable RAW_DATA_DIR.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = Path(os.environ.get("RAW_DATA_DIR", REPO_ROOT.parent / "raw_datasets"))

# Raw dataset locations (as produced by python/00_download_datasets.py)
BOSCH_DIR = RAW_DIR / "CNC_Machining" / "data"
UMICH_DIR = RAW_DIR / "toolwear_cncmilling" / "experiments"
AZURE_DIR = RAW_DIR / "telemetry" / "data"
AI4I_DIR = RAW_DIR / "ai4i2020"
AI4I_CSV = AI4I_DIR / "ai4i2020.csv"

# Repository data folders
DATA_DIR = REPO_ROOT / "data"
REFERENCE_DIR = DATA_DIR / "reference"
PROCESSED_DIR = DATA_DIR / "processed"
SAMPLES_DIR = DATA_DIR / "samples"
INTERIM_DIR = DATA_DIR / "interim"  # git-ignored, large intermediates

DIAGRAMS_DIR = REPO_ROOT / "diagrams"
FIGURES_DIR = REPO_ROOT / "docs" / "figures"
SQL_DIR = REPO_ROOT / "sql"
SQL_RESULTS_DIR = SQL_DIR / "results"

for _d in (REFERENCE_DIR, PROCESSED_DIR, SAMPLES_DIR, INTERIM_DIR, FIGURES_DIR, SQL_RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
