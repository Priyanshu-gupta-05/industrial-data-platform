"""Cloud-side subscriber: consumes the UNS topics and writes them into PostgreSQL.

Persistent session (clean_session=False, fixed client id, QoS 1): while this subscriber is
offline the broker queues its messages and delivers them on reconnect. QoS 1 is
at-least-once, so inserts are idempotent (msg_id primary key, ON CONFLICT DO NOTHING).

    python python/edge/cloud_subscriber.py
"""
from __future__ import annotations

import json
import queue
import sys
import threading
import time
from pathlib import Path

import paho.mqtt.client as mqtt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.db import connect  # noqa: E402

HOST, PORT = "127.0.0.1", 1883
DDL = """
CREATE SCHEMA IF NOT EXISTS edge;
CREATE TABLE IF NOT EXISTS edge.mqtt_ingest (
    msg_id       UUID PRIMARY KEY,
    topic        TEXT        NOT NULL,
    machine_code TEXT        NOT NULL,
    ts           TIMESTAMPTZ NOT NULL,          -- gateway timestamp (edge clock)
    received_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload      JSONB       NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mqtt_ingest_machine_ts ON edge.mqtt_ingest (machine_code, ts);
"""


class CloudSubscriber:
    def __init__(self) -> None:
        self.q: queue.Queue = queue.Queue()
        self.received = 0
        self.stop_event = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="cloud-ingest-01", clean_session=False)
        self.client.username_pw_set("cloud-ingest-01")
        self.client.on_connect = lambda c, u, f, rc, p: c.subscribe("tier1/+/+/+/#", qos=1)
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=2)
        with connect(autocommit=True) as conn:
            conn.execute(DDL)

    def _on_message(self, client, userdata, msg):
        if msg.topic.endswith("/status"):
            return
        self.received += 1
        self.q.put((msg.topic, json.loads(msg.payload)))

    def _writer(self) -> None:
        with connect(autocommit=True) as conn:
            while not (self.stop_event.is_set() and self.q.empty()):
                batch = []
                try:
                    batch.append(self.q.get(timeout=0.3))
                    while len(batch) < 500:
                        batch.append(self.q.get_nowait())
                except queue.Empty:
                    pass
                if batch:
                    with conn.cursor() as cur:
                        cur.executemany(
                            "INSERT INTO edge.mqtt_ingest (msg_id, topic, machine_code, ts, payload) "
                            "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (msg_id) DO NOTHING",
                            [(p["msg_id"], t, p["machine"], p["ts"], json.dumps(p)) for t, p in batch])

    def start(self) -> None:
        self.stop_event.clear()
        self.writer = threading.Thread(target=self._writer, daemon=True)
        self.writer.start()
        self.client.connect_async(HOST, PORT, keepalive=5)
        self.client.loop_start()

    def stop(self) -> None:
        """Go offline (session kept at the broker)."""
        self.client.disconnect()
        self.client.loop_stop()
        self.stop_event.set()
        self.writer.join(timeout=10)


if __name__ == "__main__":
    s = CloudSubscriber()
    s.start()
    print(f"Cloud subscriber connected to {HOST}:{PORT}, writing to edge.mqtt_ingest (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(2)
            print("messages received:", s.received)
    except KeyboardInterrupt:
        s.stop()
