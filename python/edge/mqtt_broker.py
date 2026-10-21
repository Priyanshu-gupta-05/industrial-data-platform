"""Local MQTT broker (pure-Python amqtt) standing in for the cloud ingestion endpoint.

Mosquitto is the production choice at the edge; amqtt is used so the demo needs no install.

    python python/edge/mqtt_broker.py            # runs until Ctrl+C
"""
from __future__ import annotations

import asyncio
import logging
import threading

from amqtt.broker import Broker

HOST, PORT = "127.0.0.1", 1883
CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": f"{HOST}:{PORT}"}},
    # Clients must identify themselves (username). The broker only queues QoS 1 messages for
    # identified, persistent sessions, which is what makes "subscriber offline" lossless.
    # Production: X.509 client certificates / per-device credentials over TLS (port 8883).
    "auth": {"allow-anonymous": False, "plugins": ["auth_anonymous"]},
    "topic-check": {"enabled": False},
}
logging.getLogger("amqtt").setLevel(logging.ERROR)
logging.getLogger("transitions").setLevel(logging.ERROR)


class BrokerThread:
    """Runs the broker on its own asyncio loop so a demo can stop/start it (simulated WAN outage)."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.broker: Broker | None = None

    def _run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout=15)

    def start(self) -> None:
        async def _start():
            self.broker = Broker(CONFIG, loop=self.loop)
            await self.broker.start()
        self._run(_start())

    def stop(self) -> None:
        if self.broker:
            self._run(self.broker.shutdown())
            self.broker = None


if __name__ == "__main__":
    async def main():
        b = Broker(CONFIG)
        await b.start()
        print(f"MQTT broker listening on {HOST}:{PORT} (Ctrl+C to stop)")
        await asyncio.Event().wait()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
