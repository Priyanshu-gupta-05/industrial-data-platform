"""Part A - Data volume, storage, bandwidth and MEASURED compression.

1. Data-point volumes per second/hour/day/month(30 d)/year(365 d) for:
     - fleet: 100 machines x 10 sensors x 1 Hz
     - one vibration sensor at 100 Hz (one machine)
     - fleet: one 100 Hz vibration sensor on all 100 machines
     - combined design point (10 x 1 Hz + 1 x 100 Hz per machine)
     - raw tri-axial 2 kHz accelerometer on every machine (what the Bosch
       real data looks like if streamed unprocessed)
2. Storage and bandwidth under stated byte sizes, incl. JSON-over-MQTT payloads
   that are actually serialised and measured.
3. Real compression ratios measured by writing REAL data (UMich 10 Hz CNC
   signals, Bosch 2 kHz vibration) and the Azure benchmark telemetry as
   CSV, CSV+gzip, Parquet (none / Snappy / Zstd).

Outputs: docs/results/part_a_*.csv|json and docs/figures/part_a_*.png

    python python/part_a_data_volume.py
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

import h5py
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import style  # noqa: E402
from utils.paths import AZURE_DIR, BOSCH_DIR, FIGURES_DIR, INTERIM_DIR, REPO_ROOT, UMICH_DIR  # noqa: E402

RESULTS_DIR = REPO_ROOT / "docs" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

SECONDS = {"second": 1, "hour": 3600, "day": 86_400, "month (30 d)": 30 * 86_400, "year (365 d)": 365 * 86_400}

SCENARIOS = [
    # name, machines, sensors per machine, Hz per sensor
    ("Fleet 1 Hz: 100 machines x 10 sensors x 1 Hz", 100, 10, 1),
    ("Single vibration sensor @ 100 Hz (1 machine)", 1, 1, 100),
    ("Fleet vibration: 100 machines x 1 sensor x 100 Hz", 100, 1, 100),
    ("Design point: 10 x 1 Hz + 1 x 100 Hz per machine", 100, None, None),
    ("Raw accelerometer: 100 machines x 3 axes x 2 kHz", 100, 3, 2000),
]

# Byte-size assumptions (stated explicitly in the report)
BYTES_BINARY = {"timestamp (int64 epoch ns)": 8, "value (float64)": 8, "machine_id (int16)": 2, "sensor_id (int16)": 2}
BYTES_PER_POINT_BINARY = sum(BYTES_BINARY.values())          # 20 B narrow/long record
BYTES_PER_POINT_VALUE_ONLY = 8                                # value only, timestamps implicit (fixed rate)
MQTT_FIXED_HEADER = 2                                         # 1 B control + >=1 B remaining length
TCP_IP_OVERHEAD = 40                                          # IPv4 20 B + TCP 20 B per packet (no options)


def points_per_second(machines: int, sensors: int | None, hz: int | None) -> int:
    if sensors is None:  # design point: 10 sensors @1 Hz + 1 vibration @100 Hz
        return machines * (10 * 1 + 1 * 100)
    return machines * sensors * hz


def volume_table() -> pd.DataFrame:
    rows = []
    for name, m, s, hz in SCENARIOS:
        pps = points_per_second(m, s, hz)
        rows.append({"scenario": name, **{f"points per {k}": pps * v for k, v in SECONDS.items()}})
    return pd.DataFrame(rows)


def mqtt_payloads() -> dict:
    """Serialise realistic JSON messages and measure their size (not guessed)."""
    topic_single = "tier1/chakan/powertrain/hmc-07/spindle_temperature"
    single = {"ts": "2025-03-14T09:26:53.120Z", "machine": "P1-HMC-07", "sensor": "spindle_temperature",
              "value": 41.27, "unit": "degC", "q": "GOOD"}
    topic_batch = "tier1/chakan/powertrain/hmc-07/telemetry"
    batch = {"ts": "2025-03-14T09:26:53.000Z", "machine": "P1-HMC-07", "values": {
        "spindle_temperature": 41.27, "coolant_temperature": 24.81, "spindle_vibration": 1.92,
        "spindle_rpm": 6120, "spindle_current": 21.4, "feed_axis_load": 37.5, "hydraulic_pressure": 61.2,
        "coolant_flow": 18.4, "power_kw": 11.83, "door_cycle_status": 1}}
    topic_vib = "tier1/chakan/powertrain/hmc-07/spindle_vibration/raw"
    rng = np.random.default_rng(0)
    vib = {"ts0": "2025-03-14T09:26:53.000Z", "machine": "P1-HMC-07", "fs_hz": 100, "unit": "mm/s",
           "v": [round(float(x), 3) for x in rng.normal(0, 1.5, 100)]}
    out = {}
    for key, topic, msg, n_points in [("json_single_value", topic_single, single, 1),
                                      ("json_batched_10_sensors", topic_batch, batch, 10),
                                      ("json_batched_100Hz_1s_block", topic_vib, vib, 100)]:
        payload = len(json.dumps(msg, separators=(",", ":")).encode())
        mqtt = MQTT_FIXED_HEADER + 2 + len(topic.encode()) + payload  # PUBLISH QoS0: header + topic len + topic + payload
        out[key] = {"topic": topic, "payload_bytes": payload, "mqtt_publish_bytes": mqtt,
                    "points_per_message": n_points, "bytes_per_point_on_wire": round((mqtt + TCP_IP_OVERHEAD) / n_points, 2)}
    return out


def storage_bandwidth_table(mqtt: dict) -> pd.DataFrame:
    rows = []
    b_slow = mqtt["json_batched_10_sensors"]["bytes_per_point_on_wire"]
    b_fast = mqtt["json_batched_100Hz_1s_block"]["bytes_per_point_on_wire"]
    for name, m, s, hz in SCENARIOS:
        pps = points_per_second(m, s, hz)
        if hz is None:  # design point: 10 slow points + 100 fast points per machine-second
            batched = (10 * b_slow + 100 * b_fast) / 110
        else:
            batched = b_fast if hz >= 100 else b_slow
        for enc, bpp in [("Binary value only (8 B)", BYTES_PER_POINT_VALUE_ONLY),
                         ("Binary narrow record (20 B)", BYTES_PER_POINT_BINARY),
                         ("JSON/MQTT one value per message", mqtt["json_single_value"]["bytes_per_point_on_wire"]),
                         ("JSON/MQTT batched (per machine-second)", round(batched, 2))]:
            bps = pps * bpp
            rows.append({"scenario": name, "encoding": enc, "bytes_per_point": bpp,
                         "bandwidth_mbps": bps * 8 / 1e6,
                         "GB_per_day": bps * 86_400 / 1e9,
                         "TB_per_month": bps * 30 * 86_400 / 1e12,
                         "TB_per_year": bps * 365 * 86_400 / 1e12})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- measured compression
def _write_formats(df: pd.DataFrame, stem: str) -> dict:
    tmp = INTERIM_DIR / "compression"
    tmp.mkdir(parents=True, exist_ok=True)
    sizes = {}
    raw_bytes = int(sum(df[c].to_numpy().nbytes for c in df.columns))
    sizes["In-memory binary (numpy)"] = raw_bytes
    csv = tmp / f"{stem}.csv"
    df.to_csv(csv, index=False)
    sizes["CSV"] = csv.stat().st_size
    with open(csv, "rb") as src, gzip.open(tmp / f"{stem}.csv.gz", "wb", compresslevel=6) as dst:
        shutil.copyfileobj(src, dst)
    sizes["CSV + gzip"] = (tmp / f"{stem}.csv.gz").stat().st_size
    table = pa.Table.from_pandas(df, preserve_index=False)
    for label, comp, level in [("Parquet (uncompressed)", "none", None), ("Parquet + Snappy", "snappy", None),
                               ("Parquet + Zstd (level 3)", "zstd", 3), ("Parquet + Zstd (level 9)", "zstd", 9)]:
        p = tmp / f"{stem}_{label.split()[-1].strip('()')}_{comp}{level or ''}.parquet"
        pq.write_table(table, p, compression=comp, compression_level=level)
        sizes[label] = p.stat().st_size
    return sizes


def load_umich() -> pd.DataFrame:
    frames = [pd.read_csv(f).assign(experiment=int(f.stem.split("_")[1]))
              for f in sorted(UMICH_DIR.glob("experiment_*.csv"))]
    df = pd.concat(frames, ignore_index=True)
    return df.drop(columns=["Machining_Process"])  # keep numeric sensor/control signals


def load_bosch_raw(n_files: int = 40) -> pd.DataFrame:
    files = sorted(BOSCH_DIR.glob("M01/OP*/good/*.h5"))[:n_files]
    arrs = []
    for f in files:
        with h5py.File(f, "r") as h:
            arrs.append(h["vibration_data"][:])
    a = np.concatenate(arrs)
    t = np.arange(len(a), dtype=np.int64) * 500_000  # 2 kHz -> 500 us steps, in ns
    return pd.DataFrame({"t_ns": t, "acc_x": a[:, 0], "acc_y": a[:, 1], "acc_z": a[:, 2]})


def compression_table() -> pd.DataFrame:
    datasets = [("UMich CNC 10 Hz signals (REAL)", "umich", load_umich)]
    azure = pd.read_csv(AZURE_DIR / "telemetry.csv", parse_dates=["datetime"])
    azure["datetime"] = azure["datetime"].astype("int64")
    datasets.append(("Azure PdM hourly telemetry (BENCHMARK)", "azure", lambda: azure))
    if any(BOSCH_DIR.glob("M01/OP*/good/*.h5")):
        datasets.append(("Bosch 2 kHz tri-axial vibration (REAL)", "bosch", load_bosch_raw))
    else:
        print("[warn] Bosch data not found; skipping 2 kHz compression measurement")
    rows = []
    for label, stem, loader in datasets:
        df = loader()
        sizes = _write_formats(df, stem)
        for fmt, b in sizes.items():
            rows.append({"dataset": label, "rows": len(df), "columns": df.shape[1], "format": fmt, "bytes": b,
                         "ratio_vs_csv": sizes["CSV"] / b, "ratio_vs_binary": sizes["In-memory binary (numpy)"] / b})
        print(f"[measured] {label}: {len(df):,} rows; CSV {sizes['CSV'] / 1e6:.1f} MB -> "
              f"Parquet+Zstd3 {sizes['Parquet + Zstd (level 3)'] / 1e6:.1f} MB")
    shutil.rmtree(INTERIM_DIR / "compression", ignore_errors=True)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- figures
def fig_volume(vol: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.2))
    y = vol["points per year (365 d)"].to_numpy()
    labels = vol["scenario"].tolist()
    colors = [style.SERIES[0], style.SERIES[1], style.SERIES[1], style.SERIES[2], style.SERIES[7]]
    bars = ax.barh(labels[::-1], y[::-1], color=colors[::-1], height=0.6)
    ax.set_xscale("log")
    ax.set_xlabel("Data points per year (log scale)")
    ax.set_title("Part A - Yearly data points by acquisition scenario")
    for b, v in zip(bars, y[::-1]):
        ax.text(v * 1.15, b.get_y() + b.get_height() / 2, f"{v / 1e9:,.2f} bn" if v >= 1e9 else f"{v / 1e6:,.1f} M",
                va="center", fontsize=9, color=style.INK_2)
    ax.set_xlim(1e8, y.max() * 12)
    ax.grid(axis="y", visible=False)
    style.source_note(fig, "Computed: standard month = 30 days, year = 365 days, 24x7 operation.")
    style.save(fig, FIGURES_DIR / "part_a_volume_per_year")


def fig_bandwidth(sb: pd.DataFrame) -> None:
    keep = sb[sb.scenario.str.startswith(("Fleet 1 Hz", "Fleet vibration", "Design point", "Raw accelerometer"))]
    piv = keep.pivot(index="scenario", columns="encoding", values="bandwidth_mbps")
    order = ["Binary value only (8 B)", "Binary narrow record (20 B)", "JSON/MQTT batched (per machine-second)",
             "JSON/MQTT one value per message"]
    piv = piv.loc[[s for s, *_ in SCENARIOS if s in piv.index], order]  # keep scenario order
    fig, ax = plt.subplots(figsize=(10, 4.6))
    n = len(order)
    width = 0.8 / n
    x = np.arange(len(piv))
    for i, enc in enumerate(order):
        ax.bar(x + (i - (n - 1) / 2) * width, piv[enc], width=width - 0.02, color=style.SERIES[i], label=enc)
    ax.set_yscale("log")
    ax.set_xticks(x, [s.split(":")[0] for s in piv.index], fontsize=9)
    ax.set_ylabel("Sustained uplink bandwidth (Mbps, log)")
    ax.set_title("Part A - Fleet uplink bandwidth by payload encoding")
    ax.axhline(100, color=style.STATUS["critical"], lw=1, ls="--")
    ax.text(len(piv) - 0.5, 115, "100 Mbps typical plant ILL uplink", ha="right", fontsize=8, color=style.INK_2)
    ax.legend(ncol=2, loc="upper left")
    style.source_note(fig, "Computed. JSON sizes measured by serialising realistic messages; +40 B TCP/IP per message.")
    style.save(fig, FIGURES_DIR / "part_a_bandwidth_by_encoding")


def fig_compression(comp: pd.DataFrame) -> None:
    fmts = ["CSV", "CSV + gzip", "Parquet (uncompressed)", "Parquet + Snappy", "Parquet + Zstd (level 3)",
            "Parquet + Zstd (level 9)"]
    ds = comp.dataset.unique()
    fig, axes = plt.subplots(1, len(ds), figsize=(4.2 * len(ds), 4.2), sharey=False)
    axes = np.atleast_1d(axes)
    for ax, d in zip(axes, ds):
        sub = comp[(comp.dataset == d)].set_index("format").loc[fmts]
        mb = sub["bytes"] / 1e6
        bars = ax.bar(range(len(fmts)), mb, color=[style.SEQ_BLUE[2]] * 2 + [style.SERIES[0]] * 4, width=0.65)
        for b, r in zip(bars, sub["ratio_vs_csv"]):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{r:.1f}x", ha="center", va="bottom",
                    fontsize=8.5, color=style.INK_2)
        short = ["CSV", "CSV+gzip", "Parquet", "Parquet+Snappy", "Parquet+Zstd L3", "Parquet+Zstd L9"]
        ax.set_xticks(range(len(fmts)), short, rotation=35, ha="right", fontsize=8.5)
        ax.set_title(d, fontsize=10)
        ax.set_ylabel("File size (MB)")
    fig.suptitle("Part A - Measured file size and compression ratio vs CSV (labels)", x=0.01, ha="left")
    style.source_note(fig, "Measured by writing the real/benchmark datasets in each format (pyarrow).", y=-0.08)
    style.save(fig, FIGURES_DIR / "part_a_measured_compression")


def main() -> None:
    style.apply()
    vol = volume_table()
    mqtt = mqtt_payloads()
    sb = storage_bandwidth_table(mqtt)
    comp = compression_table()

    vol.to_csv(RESULTS_DIR / "part_a_volume.csv", index=False)
    sb.to_csv(RESULTS_DIR / "part_a_storage_bandwidth.csv", index=False)
    comp.to_csv(RESULTS_DIR / "part_a_compression_measured.csv", index=False)
    (RESULTS_DIR / "part_a_mqtt_payloads.json").write_text(json.dumps(
        {"byte_assumptions": BYTES_BINARY, "tcp_ip_overhead_bytes": TCP_IP_OVERHEAD, "messages": mqtt}, indent=2))

    fig_volume(vol)
    fig_bandwidth(sb)
    fig_compression(comp)

    pd.set_option("display.float_format", lambda v: f"{v:,.2f}")
    print("\n" + vol.set_index("scenario").map(lambda v: f"{v:,.0f}").to_string())
    print("\nMQTT payloads (measured):", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "topic"}
                                                     for k, v in mqtt.items()}, indent=1))
    print("\n" + sb[sb.encoding.str.startswith("Binary narrow")][["scenario", "bandwidth_mbps", "GB_per_day",
                                                                  "TB_per_year"]].to_string(index=False))
    print("\n" + comp.pivot(index="format", columns="dataset", values="ratio_vs_csv").to_string())


if __name__ == "__main__":
    main()
