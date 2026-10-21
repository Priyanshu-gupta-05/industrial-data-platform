"""Indicative business impact in INR of (1) predictive maintenance and (2) wear-based tool changes.

All money values are ASSUMPTIONS (stated below and saved to docs/results/business_assumptions.csv);
volumes come from the project's own data and model results. Indicative only.

    python python/ml/business_impact.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from common import FIGURES_DIR, PROCESSED_DIR, RESULTS_DIR, save_json, style

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import REFERENCE_DIR, SQL_RESULTS_DIR  # noqa: E402

A = {  # ---- assumptions (INR) -------------------------------------------------------
    "downtime_cost_inr_per_machine_hour": 5000,     # lost contribution margin, Tier-1 machining cell
    "unplanned_repair_premium_inr": 25000,          # expedited spares, overtime, collateral damage
    "planned_intervention_hours": 3.0,              # planned replacement when warned (scheduled maint 2-4 h)
    "false_alarm_cost_inr": 2500,                   # 0.5 h inspection + technician time
    "realistic_event_recall": 0.60,                 # conservative real-world recall (benchmark shows ~1.0)
    "realistic_precision": 0.50,                    # conservative real-world precision
    "tool_change_policy_wear_min": 150,             # proposed wear-based change point (min)
    "tool_cost_inr": 3500,                          # carbide tool / insert set per change
    "scrap_cost_share_of_part_value": 0.6,          # material + processing lost per rejected part
    "part_value_inr": {"Engine block": 9000, "Cylinder head": 6500, "Crankcase": 5000, "Gear shaft": 1200,
                       "Helical gear": 900, "Differential housing": 2500, "Gear shaft (finish grind)": 1500,
                       "Brake disc": 700, "Steering knuckle": 1800, "Wheel hub": 1100},
}


def pdm_savings() -> dict:
    mtbf = pd.read_csv(SQL_RESULTS_DIR / "a3_mtbf_mttr_per_machine.csv")
    failures = int(mtbf.failures.sum())
    mttr = float((mtbf.mttr_hours * mtbf.failures).sum() / failures)
    caught = failures * A["realistic_event_recall"]
    false_alarms = caught * (1 / A["realistic_precision"] - 1)
    hours_saved = caught * max(mttr - A["planned_intervention_hours"], 0)
    gross = hours_saved * A["downtime_cost_inr_per_machine_hour"] + caught * A["unplanned_repair_premium_inr"]
    cost = false_alarms * A["false_alarm_cost_inr"]
    return {"failures_per_year": failures, "mttr_hours": mttr, "failures_caught": caught,
            "false_alarms": false_alarms, "downtime_hours_saved": hours_saved,
            "gross_saving_inr": gross, "false_alarm_cost_inr": cost, "net_saving_inr": gross - cost}


def tool_policy_savings() -> dict:
    md = pd.read_parquet(PROCESSED_DIR / "machine_data.parquet",
                         columns=["machine_id", "part_family_id", "production_count", "tool_wear_min", "reject_probability"])
    calib = json.loads((REFERENCE_DIR / "calibration.json").read_text())["reject_model"]
    parts = pd.read_csv(REFERENCE_DIR / "part_master.csv").set_index("part_family_id")["part_name"]
    value = md.part_family_id.map(parts).map(A["part_value_inr"]) * A["scrap_cost_share_of_part_value"]
    p = md.reject_probability.clip(1e-6, 1 - 1e-6).to_numpy(dtype=float)
    logit = np.log(p / (1 - p))
    w = md.tool_wear_min.to_numpy(dtype=float)
    # counterfactual: the tool is replaced at the policy point, so wear never exceeds it
    w_cf = np.where(w > A["tool_change_policy_wear_min"], w - A["tool_change_policy_wear_min"], w)
    logit_cf = logit + calib["b_wear_full_life"] * (w_cf - w) / 240
    p_cf = np.minimum(1 / (1 + np.exp(-logit_cf)), 0.2)
    prod = md.production_count.to_numpy()
    rej, rej_cf = (prod * p).sum(), (prod * p_cf).sum()
    scrap_saved = ((p - p_cf) * prod * value.to_numpy()).sum()
    # extra tools: current changes counted from the sawtooth resets; policy shortens life to 150 min
    resets = int((md.groupby("machine_id").tool_wear_min.diff() < 0).sum())
    mean_life = float(md.groupby("machine_id").tool_wear_min.max().mean())
    extra_tools = resets * (mean_life / A["tool_change_policy_wear_min"] - 1)
    tool_cost = extra_tools * A["tool_cost_inr"]
    return {"expected_rejects_current": rej, "expected_rejects_policy": rej_cf,
            "reject_rate_current_pct": 100 * rej / prod.sum(), "reject_rate_policy_pct": 100 * rej_cf / prod.sum(),
            "scrap_saving_inr": scrap_saved, "tool_changes_current": resets, "extra_tool_changes": extra_tools,
            "extra_tool_cost_inr": tool_cost, "net_saving_inr": scrap_saved - tool_cost}


def main() -> None:
    style.apply()
    pdm, tool = pdm_savings(), tool_policy_savings()
    save_json("business_impact", {"assumptions": A, "predictive_maintenance": pdm, "tool_change_policy": tool,
                                  "total_net_saving_inr_per_year": pdm["net_saving_inr"] + tool["net_saving_inr"]})
    rows = [(k, v) for k, v in A.items() if k != "part_value_inr"] + [(f"part_value_inr: {k}", v)
                                                                       for k, v in A["part_value_inr"].items()]
    pd.DataFrame(rows, columns=["assumption", "value"]).to_csv(RESULTS_DIR / "business_assumptions.csv", index=False)

    lakh = 1e5
    items = [("PdM: downtime avoided", pdm["downtime_hours_saved"] * A["downtime_cost_inr_per_machine_hour"]),
             ("PdM: repair premium avoided", pdm["failures_caught"] * A["unplanned_repair_premium_inr"]),
             ("PdM: false-alarm cost", -pdm["false_alarm_cost_inr"]),
             ("Tools: scrap avoided", tool["scrap_saving_inr"]),
             ("Tools: extra tool cost", -tool["extra_tool_cost_inr"])]
    total = sum(v for _, v in items)
    fig, ax = plt.subplots(figsize=(11, 4.4))
    run = 0.0
    for i, (lab, v) in enumerate(items):
        color = style.STATUS["good"] if v >= 0 else style.STATUS["critical"]
        ax.bar(i, v / lakh, bottom=run / lakh, color=color, width=0.6)
        ax.text(i, (run + max(v, 0)) / lakh + 0.6, f"{v / lakh:+,.1f}", ha="center", fontsize=9, color=style.INK_2)
        run += v
    ax.bar(len(items), total / lakh, color=style.SERIES[0], width=0.6)
    ax.text(len(items), total / lakh + 0.6, f"{total / lakh:,.1f}", ha="center", fontsize=9, fontweight="bold")
    ax.set_xticks(range(len(items) + 1), [l for l, _ in items] + ["Net per year"], fontsize=9, rotation=12)
    ax.set_ylabel("INR lakh per year")
    ax.set_title("Indicative annual impact for the 100-machine fleet (INR lakh)")
    ax.grid(axis="x", visible=False)
    style.source_note(fig, "Indicative. Volumes from project data/models; INR values are stated assumptions "
                           "(docs/results/business_assumptions.csv). Real-world PdM recall 60 %, precision 50 % assumed.")
    style.save(fig, FIGURES_DIR / "ml_business_impact_inr")
    print(f"PdM net Rs {pdm['net_saving_inr'] / lakh:,.1f} lakh ({pdm['failures_caught']:.0f} failures caught, "
          f"{pdm['downtime_hours_saved']:,.0f} h saved) | tools net Rs {tool['net_saving_inr'] / lakh:,.1f} lakh "
          f"(reject {tool['reject_rate_current_pct']:.2f}% -> {tool['reject_rate_policy_pct']:.2f}%) | "
          f"total Rs {total / lakh:,.1f} lakh")


if __name__ == "__main__":
    main()
