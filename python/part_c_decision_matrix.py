"""Part C - INR cost model, weighted decision matrix and sensitivity analysis.

1. Indicative monthly cost (INR) for AWS ap-south-1, Azure Central India and GCP asia-south1, for
     S1  raw 1 Hz (10 sensors) + raw 100 Hz vibration to the cloud          (assignment case)
     S2  raw 1 Hz + edge vibration FEATURES (42 values / s, measured in Part A)
     S3  raw 2 kHz tri-axial accelerometer to the cloud (what the Bosch sensors produce)
   Prices: data/reference/cloud_prices.json (list prices accessed 2026-10-21, docs/sources.md).
   Payload sizes: measured JSON sizes from Part A (docs/results/part_a_mqtt_payloads.json).
2. Ten-criterion weighted decision matrix (weights = 100 %, scores 1-5 with evidence).
   The cost score is computed from the S2 cost model (cheapest = 5, others scaled).
3. Sensitivity: +/-5-point weight shifts per criterion, alternative weight profiles, and a
   Monte-Carlo perturbation of weights (Dirichlet) and scores (+/-0.5).

Outputs: docs/results/part_c_*.csv|json, docs/decision_matrix.xlsx, docs/cost_model.md,
         docs/figures/part_c_*.png

    python python/part_c_decision_matrix.py
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import style  # noqa: E402
from utils.paths import FIGURES_DIR, REFERENCE_DIR, REPO_ROOT  # noqa: E402

RES = REPO_ROOT / "docs" / "results"
P = json.loads((REFERENCE_DIR / "cloud_prices.json").read_text())
FX = P["fx"]["usd_inr"]
H = P["hours_per_month"]                      # 720 h = standard 30-day month
MACHINES, SECONDS_MONTH = 100, 30 * 86400
CLOUDS = ["AWS", "Azure", "GCP"]
CLOUD_COLORS = {"AWS": style.SERIES[1], "Azure": style.SERIES[0], "GCP": style.SERIES[2]}
RETENTION_MONTHS = 12

# ------------------------------------------------------------------ scenarios (per machine-second)
mq = json.loads((RES / "part_a_mqtt_payloads.json").read_text())["messages"]
slow_b = mq["json_batched_10_sensors"]["payload_bytes"]               # 10 sensors @ 1 Hz, measured
fast_b = mq["json_batched_100Hz_1s_block"]["payload_bytes"]           # 100 samples @ 100 Hz, measured
feat_b = 42 * 12 + 60                                                 # 42 features in JSON (~12 B each) + envelope
raw2k_b = 3 * 2000 * 7 + 80                                           # 6,000 values, ~7 B each in JSON
single_b = mq["json_single_value"]["payload_bytes"]                   # one JSON message per reading, measured
SCEN = {   # bytes per message, messages per machine-second, storage compression
    "S0 raw, one message per reading": {"bytes": single_b, "msgs": 110, "compress": 6.9},
    "S1 raw 1 Hz + raw 100 Hz": {"bytes": slow_b + fast_b, "msgs": 1, "compress": 6.9},
    "S2 raw 1 Hz + edge features": {"bytes": slow_b + feat_b, "msgs": 1, "compress": 6.9},
    "S3 raw 2 kHz tri-axial": {"bytes": slow_b + raw2k_b, "msgs": 1, "compress": 5.0},
}
# compression: 6.9x Parquet+Zstd measured on real UMich signals; ~5x measured on Bosch 2 kHz raw (Part A)


def monthly_cost(cloud: str, msg_bytes: float, compress: float, msgs_per_s: int = 1) -> dict:
    """USD per month by component; msgs_per_s messages per machine per second."""
    msgs = MACHINES * SECONDS_MONTH * msgs_per_s           # 259.2 M messages / month when batched per second
    bytes_month = msgs * msg_bytes
    stored_gb = bytes_month * RETENTION_MONTHS / compress / 1e9       # steady state at 12-month retention
    c = {}
    if cloud == "AWS":
        a = P["aws"]
        metered = msgs * math.ceil(msg_bytes / (a["iot_core_msg_meter_kb"] * 1024)) / 1e6   # millions
        # published volume tiers: first 1,000 M at $1.05, next 4,000 M at $0.84, beyond at $0.74 per million [S18]
        tiers = [(1000, 1.05), (4000, 0.84), (float("inf"), 0.74)]
        left, msg_cost = metered, 0.0
        for size, price in tiers:
            take = min(left, size)
            msg_cost += take * price
            left -= take
        c["Ingestion (IoT Core msgs + rules)"] = msg_cost + \
            msgs / 1e6 * (a["iot_core_rules_per_million"] + a["iot_core_actions_per_million"])
        c["Stream processing (Kinesis, 2 shards)"] = 2 * a["kinesis_shard_hour"] * H + \
            msgs * math.ceil(msg_bytes / 25600) / 1e6 * a["kinesis_put_per_million_units"]
        c["Data lake storage (S3)"] = stored_gb * a["s3_standard_gb_month"]
        c["PostgreSQL (2 vCPU burstable + 128 GB)"] = a["rds_postgres_t4g_medium_hour"] * H + 128 * a["postgres_storage_gb_month"]
    elif cloud == "Azure":
        z = P["azure"]
        per_day = msgs / 30 * math.ceil(msg_bytes / (z["iot_hub_msg_meter_kb"] * 1024))
        options = {t: math.ceil(per_day / z[f"iot_hub_{t}_msgs_per_day"]) * z[f"iot_hub_{t}_unit_month"]
                   for t in ("s1", "s2", "s3")}
        tier = min(options, key=options.get)
        c["Ingestion (IoT Hub " + tier.upper() + ")"] = options[tier]
        c["Stream processing (Event Hubs 2 TU)"] = 2 * z["event_hubs_tu_hour"] * H + msgs / 1e6 * z["event_hubs_ingress_per_million"]
        c["Data lake storage (ADLS Gen2 Hot)"] = stored_gb * z["adls_hot_gb_month"]
        c["PostgreSQL (2 vCPU burstable + 128 GB)"] = z["postgres_flex_b2s_hour"] * H + 128 * z["postgres_storage_gb_month"]
    else:
        g = P["gcp"]
        c["Ingestion (Pub/Sub + 3 broker VMs)"] = bytes_month / 2 ** 40 * g["pubsub_per_tib"] + 3 * g["mqtt_broker_vm_month"]
        c["Stream processing (Dataflow, assumed 1 worker)"] = 0.07 * H      # assumption: not retrievable
        c["Data lake storage (Cloud Storage)"] = stored_gb * g["gcs_standard_gb_month"]
        c["PostgreSQL (2 vCPU + 4 GiB + 128 GB)"] = (2 * g["cloudsql_vcpu_hour"] + 4 * g["cloudsql_gib_hour"]) * H + 128 * 0.17
    return c


def cost_model() -> pd.DataFrame:
    rows = []
    for s, v in SCEN.items():
        for cl in CLOUDS:
            for comp, usd in monthly_cost(cl, v["bytes"], v["compress"], v["msgs"]).items():
                rows.append({"scenario": s, "cloud": cl, "component": comp, "usd_month": usd, "inr_month": usd * FX})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ decision matrix
CRITERIA = [
    # name, weight, AWS, Azure, GCP, justification (AWS | Azure | GCP)
    ("Industrial IoT & OT connectivity", 15, 4, 5, 2,
     "SiteWise Edge reads OPC UA, but IoT Events retired and Monitor in maintenance [S3][S8][S10] | "
     "IoT Operations OPC UA connector with asset discovery, certificates, write-back [S33] | "
     "no first-party IIoT since IoT Core retired; partner (Litmus MC) required [S58][S60][S63]"),
    ("Edge computing & offline operation", 12, 4, 4, 2,
     "Greengrass V2 + SiteWise Edge, documented outage buffering; processing pack in maintenance [S9][S10][S12] | "
     "IoT Operations / IoT Edge 1.6 LTS; needs Kubernetes, 72 h offline limit [S32][S34][S36] | "
     "partner edge (MC/Litmus); GDC India availability unknown [S63][S67]"),
    ("Security, compliance & India residency", 12, 4, 4, 3,
     "all IoT services in Mumbai; X.509 device identity; no IEC 62443 product certification found [S13]-[S15][S26] | "
     "OT-grade PKI in IoT Operations, Defender for IoT OT monitoring; Arc control plane and Defender cloud mode outside India [S32][S34][S55] | "
     "storage pinning to India regions; edge security delegated to partner [S63][S72]"),
    ("Indicative cost (INR)", 13, None, None, None, "computed from the S2 cost model: cheapest = 5, others = 5 x cheapest / cost"),
    ("Time-series storage & data lake", 10, 4, 5, 4,
     "S3 + Timestream for InfluxDB (LiveAnalytics closed) [S6][S7][S21] | "
     "ADLS Gen2 + Eventhouse/ADX native time-series with KQL [S40][S42][S49] | "
     "Cloud Storage + BigQuery/Bigtable, strong but not time-series native [S64][S69]"),
    ("Stream processing & analytics", 10, 3, 5, 4,
     "Kinesis + Athena assembled after IoT Analytics retired [S2][S22] | "
     "Eventstreams no-code windows/dedup + KQL + Power BI [S40][S42] | "
     "Dataflow + BigQuery: strongest analytics, code-first [S70][S75]"),
    ("AI/ML", 10, 5, 4, 5,
     "SageMaker (general knowledge) | Azure ML, Fabric notebooks, KQL anomaly detection [S40][S42] | "
     "Vertex AI + BigQuery ML (general knowledge)"),
    ("Integration (MES/ERP/SAP, Microsoft 365, OPC UA)", 8, 3, 5, 4,
     "SAP via AppFlow, Siemens Industrial Edge hosting [S10][S27] | "
     "Power BI / M365 / Entra native, OPC UA connector, SAP mirroring (preview) [S33][S40][S57] | "
     "best SAP connector (no charge), OPC UA via partner [S63][S77]"),
    ("Scalability", 5, 5, 5, 5,
     "IoT Core tiers past 5 B msg/month [S18] | IoT Hub S3 = 300 M msg/day/unit, ADX millions of events/s [S42][S46] | "
     "Pub/Sub autoscaling, brokers rated for millions of devices [S60]"),
    ("Ease of use & skills availability", 5, 3, 4, 3,
     "IIoT stack now a set of parts after retirements [S1][S3][S8] | "
     "Fabric SaaS + common Microsoft skills; Kubernetes for IoT Operations [S32][S40] | "
     "must own broker or buy edge; BigQuery simple [S60][S63]"),
]


def matrix(cost_s2: pd.Series) -> pd.DataFrame:
    rows = []
    for name, w, a, z, g, why in CRITERIA:
        if a is None:
            a, z, g = (round(5 * cost_s2.min() / cost_s2[c] * 2) / 2 for c in CLOUDS)   # nearest 0.5
        rows.append({"criterion": name, "weight": w, "AWS": a, "Azure": z, "GCP": g, "evidence": why})
    m = pd.DataFrame(rows)
    assert m.weight.sum() == 100
    return m


def totals(m: pd.DataFrame, w: np.ndarray | None = None) -> pd.Series:
    w = m.weight.to_numpy() if w is None else w
    return pd.Series({c: float((m[c].to_numpy() * w).sum() / w.sum()) for c in CLOUDS})


def sensitivity(m: pd.DataFrame) -> dict:
    base = totals(m)
    shifts = []
    for i, r in m.iterrows():
        for d in (-5, +5):
            w = m.weight.to_numpy(dtype=float).copy()
            w[i] = max(w[i] + d, 0)
            t = totals(m, w)
            shifts.append({"criterion": r.criterion, "shift": d, **t.to_dict(), "winner": t.idxmax(),
                           "azure_margin": t["Azure"] - t.drop("Azure").max()})
    profiles = {
        "Baseline (scenario)": m.weight.to_numpy(float),
        "Cost-heavy (cost 35)": None, "Capability-heavy (cost 3)": None, "OT/edge-first": None,
        "Analytics/AI-first": None, "Equal weights": np.full(len(m), 10.0),
    }
    idx = {r.criterion: i for i, r in m.iterrows()}
    def prof(changes):
        w = m.weight.to_numpy(float).copy()
        for k, v in changes.items():
            w[idx[k]] = v
        return w
    profiles["Cost-heavy (cost 35)"] = prof({"Indicative cost (INR)": 35})
    profiles["Capability-heavy (cost 3)"] = prof({"Indicative cost (INR)": 3})
    profiles["OT/edge-first"] = prof({"Industrial IoT & OT connectivity": 25, "Edge computing & offline operation": 20,
                                      "AI/ML": 5, "Stream processing & analytics": 5})
    profiles["Analytics/AI-first"] = prof({"AI/ML": 25, "Stream processing & analytics": 20,
                                           "Industrial IoT & OT connectivity": 8, "Edge computing & offline operation": 6})
    prof_rows = [{"profile": k, **totals(m, w).to_dict(), "winner": totals(m, w).idxmax()} for k, w in profiles.items()]

    rng = np.random.default_rng(0)
    N = 10_000
    wins = {c: 0 for c in CLOUDS}
    S = m[CLOUDS].to_numpy(float)
    W = rng.dirichlet(m.weight.to_numpy(float) / 100 * 50, size=N)       # concentration 50
    noise = rng.uniform(-0.5, 0.5, size=(N,) + S.shape)
    t_all = np.einsum("nk,nkc->nc", W, np.clip(S[None] + noise, 1, 5))
    for k in t_all.argmax(axis=1):
        wins[CLOUDS[k]] += 1
    mc = {"runs": N, "win_share": {c: wins[c] / N for c in CLOUDS},
          "azure_minus_best_other_p05_p50_p95": np.percentile(t_all[:, 1] - np.delete(t_all, 1, axis=1).max(axis=1),
                                                              [5, 50, 95]).round(3).tolist(),
          "method": "weights ~ Dirichlet(50 x baseline share), scores + U(-0.5, 0.5) clipped to 1-5"}
    return {"base": base.to_dict(), "shifts": pd.DataFrame(shifts), "profiles": pd.DataFrame(prof_rows), "mc": mc,
            "mc_totals": t_all}


# ------------------------------------------------------------------ outputs
def write_excel(m: pd.DataFrame, cost: pd.DataFrame) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Decision matrix"
    hdr = ["Criterion", "Weight (%)", "AWS score", "Azure score", "GCP score",
           "AWS weighted", "Azure weighted", "GCP weighted", "Evidence (AWS | Azure | GCP)"]
    ws.append(hdr)
    for r in m.itertuples():
        i = ws.max_row + 1
        ws.append([r.criterion, r.weight, r.AWS, r.Azure, r.GCP,
                   f"=B{i}*C{i}/100", f"=B{i}*D{i}/100", f"=B{i}*E{i}/100", r.evidence])
    n = ws.max_row
    ws.append(["TOTAL", f"=SUM(B2:B{n})", "", "", "", f"=SUM(F2:F{n})", f"=SUM(G2:G{n})", f"=SUM(H2:H{n})",
               "Weighted score out of 5; weights must total 100"])
    bold = Font(bold=True)
    fill = PatternFill("solid", fgColor="DDE8F7")
    for cell in ws[1] + ws[ws.max_row]:
        cell.font = bold
        cell.fill = fill
    for col, wdt in zip("ABCDEFGHI", [40, 11, 10, 11, 10, 12, 13, 12, 120]):
        ws.column_dimensions[col].width = wdt
    for row in ws.iter_rows(min_row=2, max_col=9):
        row[8].alignment = Alignment(wrap_text=True, vertical="top")
        for c in row[5:8]:
            c.number_format = "0.000"
    ws2 = wb.create_sheet("Cost model (INR)")
    piv = cost.pivot_table(index=["scenario", "component"], columns="cloud", values="inr_month", aggfunc="sum").reset_index()
    ws2.append(["Scenario", "Component"] + CLOUDS)
    for r in piv.itertuples(index=False):
        ws2.append([r[0], r[1]] + [None if pd.isna(x) else round(float(x), 0) for x in r[2:]])
    ws2.append([])
    ws2.append([f"USD->INR {FX} ({P['fx']['date']}, RBI/FBIL reference rate, docs/sources.md {P['fx']['source']}). "
                "Indicative list prices; excludes networking, support, taxes, edge hardware."])
    for col, wdt in zip("ABCDE", [30, 46, 14, 14, 14]):
        ws2.column_dimensions[col].width = wdt
    for cell in ws2[1]:
        cell.font = bold
        cell.fill = fill
    wb.save(REPO_ROOT / "docs" / "decision_matrix.xlsx")


def figures(m: pd.DataFrame, sens: dict, cost: pd.DataFrame) -> None:
    # 1. weighted totals stacked by criterion
    fig, ax = plt.subplots(figsize=(11, 4.6))
    left = np.zeros(3)
    cmap = plt.get_cmap("tab20c")
    for i, r in m.iterrows():
        vals = np.array([r[c] * r.weight / 100 for c in CLOUDS])
        ax.barh(CLOUDS, vals, left=left, color=cmap(i / len(m)), edgecolor=style.SURFACE, linewidth=1.5,
                label=f"{r.criterion} ({r.weight}%)")
        left += vals
    for y, (c, v) in enumerate(zip(CLOUDS, left)):
        ax.text(v + 0.04, y, f"{v:.2f} / 5", va="center", fontweight="bold")
    ax.set_xlim(0, 5.4)
    ax.set_xlabel("Weighted score (out of 5)")
    ax.set_title("Part C - weighted decision matrix: contribution of each criterion")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=3, fontsize=8)
    ax.grid(axis="y", visible=False)
    style.source_note(fig, "Scores 1-5 with evidence in docs/part_c_decision.md; cost score from the INR cost model.", y=-0.38)
    style.save(fig, FIGURES_DIR / "part_c_weighted_scores")

    # 2. sensitivity: profiles + Monte Carlo margin distribution
    fig, ax = plt.subplots(1, 2, figsize=(14, 4.6), gridspec_kw={"width_ratios": [1.3, 1]})
    pr = sens["profiles"].set_index("profile")[CLOUDS]
    y = np.arange(len(pr))
    for k, c in enumerate(CLOUDS):
        ax[0].barh(y + (k - 1) * 0.26, pr[c], height=0.25, color=CLOUD_COLORS[c], label=c)
    ax[0].set_yticks(y, pr.index)
    ax[0].invert_yaxis()
    ax[0].set_xlim(2, 5)
    ax[0].set_xlabel("Weighted score (out of 5)")
    pw = sens["profiles"]
    others = pw[pw.winner != "Azure"]
    ax[0].set_title(f"Azure leads in {(pw.winner == 'Azure').sum()} of {len(pw)} weight profiles"
                    + (f"; {', '.join(others.winner + ' in ' + others.profile)}" if len(others) else ""), fontsize=11)
    ax[0].legend(loc="lower right")
    ax[0].grid(axis="y", visible=False)
    t = sens["mc_totals"]
    margin = t[:, 1] - np.delete(t, 1, axis=1).max(axis=1)
    ax[1].hist(margin, bins=60, color=style.SERIES[0], alpha=0.85)
    ax[1].axvline(0, color=style.STATUS["critical"], lw=1.5, ls="--")
    ax[1].set_xlabel("Azure score minus best alternative")
    ax[1].set_ylabel("Monte-Carlo runs")
    ax[1].set_title(f"Monte Carlo (10,000 runs): Azure wins {sens['mc']['win_share']['Azure']:.1%}")
    fig.tight_layout()
    style.source_note(fig, "Weights ~ Dirichlet around the baseline; each score perturbed by U(-0.5, +0.5).")
    style.save(fig, FIGURES_DIR / "part_c_sensitivity")

    # 3. cost model
    tot = cost.groupby(["scenario", "cloud"]).inr_month.sum().unstack()[CLOUDS] / 1e5
    fig, ax = plt.subplots(figsize=(11, 4.4))
    x = np.arange(len(tot))
    for k, c in enumerate(CLOUDS):
        b = ax.bar(x + (k - 1) * 0.26, tot[c], width=0.25, color=CLOUD_COLORS[c], label=c)
        for bar, v in zip(b, tot[c]):
            ax.text(bar.get_x() + bar.get_width() / 2, v * 1.04, f"{v:,.1f}", ha="center", fontsize=8.5, color=style.INK_2)
    ax.set_xticks(x, tot.index)
    ax.set_yscale("log")
    ax.set_ylabel("INR lakh per month (log)")
    ax.set_title("Indicative monthly cloud cost by data strategy (100 machines, 12-month retention)")
    ax.legend()
    ax.grid(axis="x", visible=False)
    style.source_note(fig, f"List prices accessed 2026-10-21 (India regions where published); 1 USD = INR {FX}. "
                           "Indicative; excludes networking, support, taxes, edge hardware.")
    style.save(fig, FIGURES_DIR / "part_c_cost_model")


def cost_markdown(cost: pd.DataFrame) -> str:
    piv = cost.pivot_table(index=["scenario", "component"], columns="cloud", values="inr_month", aggfunc="sum")
    lines = ["| Scenario | Component | AWS (₹/month) | Azure (₹/month) | GCP (₹/month) |", "|---|---|---:|---:|---:|"]
    for (s, comp), r in piv.iterrows():
        cells = ["" if pd.isna(r[c]) else f"{r[c]:,.0f}" for c in CLOUDS]
        lines.append(f"| {s} | {comp} | " + " | ".join(cells) + " |")
    tot = cost.groupby(["scenario", "cloud"]).inr_month.sum().unstack()[CLOUDS]
    lines += ["", "| Scenario | AWS total | Azure total | GCP total |", "|---|---:|---:|---:|"]
    for s, r in tot.iterrows():
        lines.append(f"| {s} | ₹{r.AWS:,.0f} | ₹{r.Azure:,.0f} | ₹{r.GCP:,.0f} |")
    return "\n".join(lines)


def main() -> None:
    style.apply()
    cost = cost_model()
    cost.to_csv(RES / "part_c_cost_model.csv", index=False)
    s2 = cost[cost.scenario.str.startswith("S2")].groupby("cloud").inr_month.sum()
    m = matrix(s2)
    m.to_csv(RES / "part_c_decision_matrix.csv", index=False)
    sens = sensitivity(m)
    sens["shifts"].to_csv(RES / "part_c_sensitivity_shifts.csv", index=False)
    sens["profiles"].to_csv(RES / "part_c_sensitivity_profiles.csv", index=False)
    tot = cost.groupby(["scenario", "cloud"]).inr_month.sum().unstack()
    out = {"usd_inr": FX, "fx_date": P["fx"]["date"], "scenario_bytes_per_machine_second": {k: v["bytes"] for k, v in SCEN.items()},
           "monthly_inr_totals": tot.round(0).to_dict("index"),
           "batching_saving_inr_month_S0_minus_S1": (tot.loc["S0 raw, one message per reading"] - tot.loc["S1 raw 1 Hz + raw 100 Hz"]).round(0).to_dict(),
           "edge_saving_inr_month_S1_minus_S2": (tot.loc["S1 raw 1 Hz + raw 100 Hz"] - tot.loc["S2 raw 1 Hz + edge features"]).round(0).to_dict(),
           "edge_saving_inr_month_S3_minus_S2": (tot.loc["S3 raw 2 kHz tri-axial"] - tot.loc["S2 raw 1 Hz + edge features"]).round(0).to_dict(),
           "weighted_totals": sens["base"], "monte_carlo": sens["mc"],
           "profiles_winners": sens["profiles"].set_index("profile").winner.to_dict(),
           "weight_shift_winner_changes": int((sens["shifts"].winner != "Azure").sum())}
    (RES / "part_c_summary.json").write_text(json.dumps(out, indent=2))
    (RES / "part_c_cost_tables.md").write_text(cost_markdown(cost), encoding="utf-8")
    write_excel(m, cost)
    figures(m, sens, cost)
    print(m[["criterion", "weight", "AWS", "Azure", "GCP"]].to_string(index=False))
    print("weighted:", {k: round(v, 3) for k, v in sens["base"].items()})
    print(sens["profiles"][["profile", *CLOUDS, "winner"]].round(3).to_string(index=False))
    print("MC:", sens["mc"]["win_share"], sens["mc"]["azure_minus_best_other_p05_p50_p95"],
          "| shift winner changes:", out["weight_shift_winner_changes"])
    print((tot / 1e5).round(2).to_string())


if __name__ == "__main__":
    main()
