"""Run every named query in sql/03_required_queries.sql and sql/04_advanced_queries.sql.

Blocks start with "-- @name <id>". Result sets are saved to sql/results/<id>.csv together
with a run log (sql/results/_run_log.csv: rows returned and execution time per query).

    python python/07_run_sql.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.db import connect  # noqa: E402
from utils.paths import SQL_DIR, SQL_RESULTS_DIR  # noqa: E402

FILES = ["03_required_queries.sql", "04_advanced_queries.sql"]


def blocks(sql_text: str) -> list[tuple[str, str]]:
    parts = re.split(r"^-- @name\s+(\S+)\s*$", sql_text, flags=re.M)
    return [(parts[i], parts[i + 1].strip()) for i in range(1, len(parts), 2)]


def main() -> None:
    log = []
    with connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DROP MATERIALIZED VIEW IF EXISTS analytics.mv_machine_daily CASCADE;"
                    "DROP VIEW IF EXISTS analytics.v_machine_health CASCADE;")
        for fname in FILES:
            for name, sql in blocks((SQL_DIR / fname).read_text()):
                t0 = time.perf_counter()
                cur.execute(sql)
                ms = (time.perf_counter() - t0) * 1000
                rows = 0
                if cur.description:
                    df = pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])
                    df.to_csv(SQL_RESULTS_DIR / f"{name}.csv", index=False)
                    rows = len(df)
                    print(f"\n=== {name}  ({rows} rows, {ms:.0f} ms)")
                    print(df.head(5).to_string(index=False))
                else:
                    print(f"\n=== {name}  (executed, {ms:.0f} ms)")
                log.append({"file": fname, "query": name, "rows": rows, "ms": round(ms, 1)})
    pd.DataFrame(log).to_csv(SQL_RESULTS_DIR / "_run_log.csv", index=False)


if __name__ == "__main__":
    main()
