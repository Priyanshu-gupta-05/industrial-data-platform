"""Edge gateway: replays REAL machine data and publishes it over MQTT with store-and-forward.

Streams (Unified Namespace / ISA-95 style topics: enterprise/site/area/machine/...):
  tier1/manesar/chassis/turn-03/spindle/telemetry      UMich 10 Hz spindle + axis signals, 1-s blocks
  tier1/chakan/powertrain/hmc-07/vibration/features     Bosch 1-s vibration features (42 values)
  tier1/<site>/gateway/status                           birth "online" / last-will "offline" (retained)

Store-and-forward: every message is written to a local SQLite outbox FIRST, then published with
QoS 1. A row is marked sent only when the broker acknowledges it (PUBACK). While the link is
down the outbox grows; on reconnect the backlog is flushed in order. Nothing is lost.

    python python/edge/edge_gateway.py --speed 5      # replay 5x faster than real time
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
import time
import uuid
from pathlib import Path

import pandas as pd
import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.paths import PROCESSED_DIR, SAMPLES_DIR, UMICH_DIR  # noqa: E402

HOST, PORT = "127.0.0.1", 1883
BUFFER_DB = Path(__file__).resolve().parent / "buffer" / "outbox.db"
UMICH_TOPIC = "tier1/manesar/chassis/turn-03/spindle/telemetry"
BOSCH_TOPIC = "tier1/chakan/powertrain/hmc-07/vibration/features"
UMICH_COLS = ["S1_ActualVelocity", "S1_CurrentFeedback", "S1_OutputPower", "X1_CurrentFeedback",
              "Y1_CurrentFeedback", "M1_CURRENT_FEEDRATE"]


def load_streams() -> tuple[pd.DataFrame, pd.DataFrame]:
    src = UMICH_DIR / "experiment_05.csv"
    if not src.exists():  # fall back to the small sample committed in the repo
        src = SAMPLES_DIR / "umich_experiment_05_sample.csv"
    umich = pd.read_csv(src)
    bosch = pd.read_parquet(PROCESSED_DIR / "bosch_features_1s.parquet")
    bosch = bosch[bosch.file == bosch.file.iloc[0]].reset_index(drop=True)
    return umich, bosch


class Outbox:
    """SQLite store-and-forward buffer (survives gateway restarts)."""

    def __init__(self, path: Path = BUFFER_DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS outbox (seq INTEGER PRIMARY KEY AUTOINCREMENT, msg_id TEXT UNIQUE, "
                        "topic TEXT, payload TEXT, created REAL, sent REAL)")
        self.lock = threading.Lock()

    def put(self, topic: str, payload: dict) -> None:
        with self.lock:
            self.db.execute("INSERT INTO outbox (msg_id, topic, payload, created) VALUES (?, ?, ?, ?)",
                            (payload["msg_id"], topic, json.dumps(payload, separators=(",", ":")), time.time()))

    def pending(self, limit: int = 200) -> list[tuple]:
        with self.lock:
            return self.db.execute("SELECT seq, topic, payload FROM outbox WHERE sent IS NULL ORDER BY seq LIMIT ?",
                                   (limit,)).fetchall()

    def mark_sent(self, seq: int) -> None:
        with self.lock:
            self.db.execute("UPDATE outbox SET sent = ? WHERE seq = ?", (time.time(), seq))

    def counts(self) -> tuple[int, int]:
        with self.lock:
            return self.db.execute("SELECT COUNT(*), COUNT(*) FILTER (WHERE sent IS NULL) FROM outbox").fetchone()

    def reset(self) -> None:
        with self.lock:
            self.db.execute("DELETE FROM outbox")


class EdgeGateway:
    def __init__(self, speed: float = 5.0, outbox: Outbox | None = None) -> None:
        self.speed = speed
        self.outbox = outbox or Outbox()
        self.inflight: dict[int, int] = {}   # paho mid -> outbox seq
        self.stop_event = threading.Event()
        self.connected = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="edge-gw-01", clean_session=True)
        self.client.username_pw_set("edge-gw-01")
        self.client.will_set("tier1/gateway/edge-gw-01/status", "offline", qos=1, retain=True)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = lambda c, u, f, rc, p: self.connected.clear()
        self.client.on_publish = self._on_publish
        self.client.reconnect_delay_set(min_delay=1, max_delay=2)

    def _on_connect(self, client, userdata, flags, rc, props):
        if rc == 0:
            client.publish("tier1/gateway/edge-gw-01/status", "online", qos=1, retain=True)
            self.inflight.clear()      # unacked messages stay unsent in the outbox and are resent
            self.connected.set()

    def _on_publish(self, client, userdata, mid, rc, props):
        seq = self.inflight.pop(mid, None)
        if seq is not None:
            self.outbox.mark_sent(seq)

    def _forwarder(self) -> None:
        """Flush the outbox in order whenever the link is up."""
        while not self.stop_event.is_set():
            if not self.connected.is_set():
                time.sleep(0.2)
                continue
            rows = [r for r in self.outbox.pending() if r[0] not in self.inflight.values()]
            for seq, topic, payload in rows:
                if not self.connected.is_set():
                    break
                info = self.client.publish(topic, payload, qos=1)
                if info.rc == mqtt.MQTT_ERR_SUCCESS:
                    self.inflight[info.mid] = seq
            time.sleep(0.05)

    def _produce(self, umich: pd.DataFrame, bosch: pd.DataFrame, duration_s: float) -> None:
        """Replay: every replayed second -> one UMich 1-s block (10 samples) + one Bosch feature row."""
        t_start, i = time.time(), 0
        while not self.stop_event.is_set() and time.time() - t_start < duration_s:
            ts = pd.Timestamp.now(tz="Asia/Kolkata").isoformat(timespec="milliseconds")
            block = umich.iloc[(i * 10) % (len(umich) - 10):(i * 10) % (len(umich) - 10) + 10]
            self.outbox.put(UMICH_TOPIC, {"msg_id": str(uuid.uuid4()), "ts": ts, "machine": "P3-TURN-03",
                                          "fs_hz": 10, "source": "UMich SMART (REAL, replayed)",
                                          "signals": {c: block[c].round(4).tolist() for c in UMICH_COLS}})
            row = bosch.iloc[i % len(bosch)]
            feats = {c: round(float(row[c]), 5) for c in bosch.columns if c[:2] in ("x_", "y_", "z_")}
            self.outbox.put(BOSCH_TOPIC, {"msg_id": str(uuid.uuid4()), "ts": ts, "machine": "P1-HMC-07",
                                          "source": "Bosch CNC (REAL, edge features)", "features": feats})
            i += 1
            time.sleep(1.0 / self.speed)

    def run(self, duration_s: float = 60.0) -> None:
        umich, bosch = load_streams()
        self.client.connect_async(HOST, PORT, keepalive=5)
        self.client.loop_start()
        fwd = threading.Thread(target=self._forwarder, daemon=True)
        fwd.start()
        self._produce(umich, bosch, duration_s)
        # drain the backlog after the replay ends (up to 30 s)
        t0 = time.time()
        while self.outbox.counts()[1] > 0 and time.time() - t0 < 30:
            time.sleep(0.2)
        self.stop_event.set()
        self.client.loop_stop()
        self.client.disconnect()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--speed", type=float, default=5.0, help="replay speed-up factor")
    ap.add_argument("--duration", type=float, default=60.0, help="seconds of wall-clock replay")
    a = ap.parse_args()
    gw = EdgeGateway(speed=a.speed)
    print(f"Edge gateway publishing to {HOST}:{PORT} (outbox {BUFFER_DB})")
    threading.Thread(target=lambda: [print("outbox total/pending:", gw.outbox.counts()) or time.sleep(2)
                                     for _ in iter(int, 1)], daemon=True).start()
    gw.run(a.duration)
