"""Automated MQTT demo: real data -> edge gateway -> broker -> cloud subscriber -> PostgreSQL,
with two failure scenarios, and an end-to-end zero-loss check.

Timeline (wall-clock seconds):
   0-10  normal operation
  10-20  cloud subscriber OFFLINE   -> broker queues messages for its persistent session
  20-28  subscriber back            -> queued messages delivered
  28-40  WAN OUTAGE (broker down)   -> gateway buffers in its SQLite outbox
  40-    link restored              -> outbox flushed in order, all rows land in PostgreSQL

Outputs: docs/results/mqtt_demo_log.csv, docs/results/mqtt_demo_summary.json,
         docs/figures/edge_mqtt_store_and_forward.png

    python python/edge/run_mqtt_demo.py
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud_subscriber import CloudSubscriber  # noqa: E402
from edge_gateway import EdgeGateway, Outbox  # noqa: E402
from mqtt_broker import BrokerThread  # noqa: E402
from utils import style  # noqa: E402
from utils.db import connect  # noqa: E402
from utils.paths import FIGURES_DIR, REPO_ROOT  # noqa: E402

RESULTS = REPO_ROOT / "docs" / "results"
REPLAY_SECONDS, SPEED = 50, 5.0
PHASES = [(0, "normal"), (10, "subscriber offline"), (20, "subscriber back"), (28, "WAN outage (broker down)"),
          (40, "link restored")]


def db_rows() -> int:
    with connect() as c:
        return c.execute("SELECT COUNT(*) FROM edge.mqtt_ingest").fetchone()[0]


def main() -> None:
    style.apply()
    broker = BrokerThread()
    broker.start()
    sub = CloudSubscriber()
    with connect(autocommit=True) as c:
        c.execute("TRUNCATE edge.mqtt_ingest")
    outbox = Outbox()
    outbox.reset()
    gw = EdgeGateway(speed=SPEED, outbox=outbox)
    sub.start()
    time.sleep(1)
    gw_thread = threading.Thread(target=gw.run, args=(REPLAY_SECONDS,), daemon=True)
    gw_thread.start()

    log, t0, phase = [], time.time(), "normal"
    while gw_thread.is_alive() or time.time() - t0 < REPLAY_SECONDS + 5:
        t = time.time() - t0
        if phase == "normal" and t >= 10:
            sub.stop(); phase = "subscriber offline"; print(f"[{t:5.1f}s] cloud subscriber OFFLINE")
        elif phase == "subscriber offline" and t >= 20:
            sub.start(); phase = "subscriber back"; print(f"[{t:5.1f}s] cloud subscriber back ONLINE")
        elif phase == "subscriber back" and t >= 28:
            broker.stop(); phase = "WAN outage (broker down)"; print(f"[{t:5.1f}s] WAN OUTAGE: broker down")
        elif phase == "WAN outage (broker down)" and t >= 40:
            broker.start(); phase = "link restored"; print(f"[{t:5.1f}s] link RESTORED")
        total, pending = outbox.counts()
        log.append({"t_s": round(t, 2), "phase": phase, "produced": total, "outbox_pending": pending,
                    "subscriber_received": sub.received, "rows_in_postgres": db_rows()})
        time.sleep(0.5)
        if t > REPLAY_SECONDS + 60:
            break
    time.sleep(3)
    sub.stop()
    broker.stop()

    total, pending = outbox.counts()
    rows = db_rows()
    with connect() as c:
        dup = c.execute("SELECT COUNT(*) - COUNT(DISTINCT msg_id) FROM edge.mqtt_ingest").fetchone()[0]
        per_topic = dict(c.execute("SELECT topic, COUNT(*) FROM edge.mqtt_ingest GROUP BY topic").fetchall())
        lat = c.execute("SELECT percentile_cont(ARRAY[0.5, 0.99]) WITHIN GROUP "
                        "(ORDER BY EXTRACT(EPOCH FROM received_at - ts)) FROM edge.mqtt_ingest").fetchone()[0]
    df = pd.DataFrame(log)
    df.to_csv(RESULTS / "mqtt_demo_log.csv", index=False)
    summary = {"messages_produced": total, "outbox_unsent_at_end": pending, "rows_in_postgres": rows,
               "duplicates_in_postgres": dup, "lost": total - rows, "per_topic": per_topic,
               "max_outbox_backlog": int(df.outbox_pending.max()),
               "end_to_end_latency_s_p50_p99": [round(float(x), 3) for x in lat],
               "note": "latency includes time spent buffered during the outage and subscriber-offline phases"}
    (RESULTS / "mqtt_demo_summary.json").write_text(json.dumps(summary, indent=2))

    fig, ax = plt.subplots(figsize=(12, 4.4))
    shades = {"subscriber offline": style.STATUS["warning"], "WAN outage (broker down)": style.STATUS["critical"]}
    for (start, name), (end, _) in zip(PHASES, PHASES[1:] + [(df.t_s.max(), "")]):
        if name in shades:
            ax.axvspan(start, end, color=shades[name], alpha=0.12, lw=0)
            ax.text((start + end) / 2, df.produced.max() * 1.02, name, ha="center", fontsize=9, color=style.INK_2)
    ax.plot(df.t_s, df.produced, color=style.SERIES[0], label="messages produced at the edge")
    ax.plot(df.t_s, df.rows_in_postgres, color=style.SERIES[2], label="rows in PostgreSQL (cloud)")
    ax.plot(df.t_s, df.outbox_pending, color=style.SERIES[1], label="gateway outbox backlog")
    ax.set_xlabel("Demo time (s)")
    ax.set_ylabel("Messages")
    ax.set_ylim(0, df.produced.max() * 1.1)
    ax.set_title(f"MQTT store-and-forward: {total} produced, {rows} stored, {total - rows} lost, {dup} duplicates")
    ax.legend(loc="center right")
    style.source_note(fig, "REAL data replayed (UMich 10 Hz blocks, Bosch 1-s features) at 5x speed. "
                           "Broker: amqtt (local). Subscriber: persistent session, QoS 1, idempotent inserts.")
    style.save(fig, FIGURES_DIR / "edge_mqtt_store_and_forward")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
