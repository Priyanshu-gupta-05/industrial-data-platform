"""PostgreSQL connection helper. Credentials come from .env (never committed) or PG* env vars."""
from __future__ import annotations

import os

import psycopg

from .paths import REPO_ROOT


def _load_env() -> dict:
    env = {}
    f = REPO_ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("PG")})
    return env


def connect(autocommit: bool = False) -> psycopg.Connection:
    e = _load_env()
    return psycopg.connect(host=e.get("PGHOST", "localhost"), port=e.get("PGPORT", "5432"),
                           dbname=e.get("PGDATABASE", "industrial"), user=e.get("PGUSER", "idp_user"),
                           password=e.get("PGPASSWORD"), autocommit=autocommit,
                           options="-c TimeZone=Asia/Kolkata")  # plants are in IST
