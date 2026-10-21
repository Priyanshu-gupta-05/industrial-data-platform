"""One visual style for every figure in the project (report, slides, dashboard).

Palette: validated categorical order (CVD-safe on adjacent pairs), fixed status
colours that are never reused for series, recessive grid/axes. Categorical hues
are assigned in fixed order to stable entities (e.g. plant P1/P2/P3 always get
slots 1/2/3), never by rank.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

# Stable entity -> colour mappings (colour follows the entity, never its rank)
PLANT_COLORS = {1: SERIES[0], 2: SERIES[1], 3: SERIES[2],
                "P1": SERIES[0], "P2": SERIES[1], "P3": SERIES[2]}
LABEL_COLORS = {"good": SERIES[0], "bad": SERIES[7]}  # good/bad operations
MACHINE_STATUS_COLORS = {"RUNNING": STATUS["good"], "IDLE": "#c3c2b7", "ALARM": STATUS["critical"],
                         "MAINTENANCE": STATUS["warning"], "OFF": "#52514e"}
# ISO 10816-3-like vibration zones (mm/s RMS) for group 2 machines, rigid foundation
ISO_ZONES = [(0.0, 1.4, "A good", STATUS["good"]), (1.4, 2.8, "B acceptable", "#9fd89f"),
             (2.8, 4.5, "C alert", STATUS["warning"]), (4.5, 11.0, "D danger", STATUS["critical"])]


def apply() -> None:
    """Apply the project matplotlib style globally."""
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "figure.dpi": 110, "savefig.dpi": 300, "savefig.bbox": "tight",
        "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"], "font.size": 10,
        "axes.titlesize": 12, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelsize": 10, "axes.labelcolor": INK_2, "axes.edgecolor": AXIS,
        "axes.linewidth": 0.8, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "axes.axisbelow": True,
        "axes.prop_cycle": mpl.cycler(color=SERIES),
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK_2, "ytick.labelcolor": INK_2,
        "legend.frameon": False, "legend.fontsize": 9,
        "lines.linewidth": 2.0, "lines.markersize": 5,
        "text.color": INK, "figure.titlesize": 13, "figure.titleweight": "bold",
    })


def save(fig: plt.Figure, path: Path, svg: bool = False) -> Path:
    """Save at 300 dpi PNG (optionally SVG too) and close the figure."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path.with_suffix(".png"))
    if svg:
        fig.savefig(path.with_suffix(".svg"))
    plt.close(fig)
    return path.with_suffix(".png")


def source_note(fig: plt.Figure, text: str, y: float = -0.02) -> None:
    """Small provenance footnote at the bottom-left of a figure (real / benchmark / derived)."""
    fig.text(0.01, y, text, fontsize=7.5, color=MUTED, ha="left", va="top")
