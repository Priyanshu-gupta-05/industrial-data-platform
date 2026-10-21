"""Create the schema and bulk-load everything into PostgreSQL with COPY.

  raw.*  : the four source datasets as published (traceability for every derived value)
  core.* : reference tables, fleet fact table (876,100 rows) and events
Idempotent: the schema script drops/recreates core and analytics; raw tables are replaced.

    python python/06_load_postgres.py
"""
from __future__ import annotations

import io
import re
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.db import connect  # noqa: E402
from utils.paths import (AI4I_CSV, AZURE_DIR, PROCESSED_DIR, REFERENCE_DIR, REPO_ROOT,  # noqa: E402
                         SQL_RESULTS_DIR, UMICH_DIR)


def copy_df(cur, table: str, df: pd.DataFrame) -> None:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    cols = ", ".join(f'"{c}"' for c in df.columns)
    with cur.copy(f"COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, NULL '')") as cp:
        cp.write(buf.getvalue())


def pg_type(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(s):
        return "BIGINT"
    if pd.api.types.is_float_dtype(s):
        return "DOUBLE PRECISION"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "TIMESTAMP"
    return "TEXT"


def load_raw(cur, name: str, df: pd.DataFrame) -> int:
    df = df.copy()
    df.columns = [re.sub(r"[^a-z0-9]+", "_", c.lower()).strip("_") for c in df.columns]
    cur.execute(f"DROP TABLE IF EXISTS raw.{name}")
    cur.execute(f"CREATE TABLE raw.{name} ({', '.join(f'{c} {pg_type(df[c])}' for c in df.columns)})")
    copy_df(cur, f"raw.{name}", df)
    return len(df)


def raw_sources() -> dict[str, pd.DataFrame]:
    a = {n: pd.read_csv(AZURE_DIR / f"{n}.csv", parse_dates=["datetime"] if n != "machines" else None)
         for n in ("telemetry", "errors", "maint", "failures", "machines")}
    exps = pd.concat([pd.read_csv(f).assign(experiment=int(f.stem.split("_")[1]))
                      for f in sorted(UMICH_DIR.glob("experiment_*.csv"))], ignore_index=True)
    bosch = pd.read_parquet(PROCESSED_DIR / "bosch_features_file.parquet")
    bosch = bosch.astype({c: "string" for c in ["file", "machine", "operation", "label", "month"]})
    return {"azure_telemetry": a["telemetry"], "azure_errors": a["errors"], "azure_maint": a["maint"],
            "azure_failures": a["failures"], "azure_machines": a["machines"],
            "ai4i": pd.read_csv(AI4I_CSV), "umich_train": pd.read_csv(UMICH_DIR / "train.csv"),
            "umich_experiment": exps, "bosch_features_file": bosch}


def main() -> None:
    t0 = time.perf_counter()
    with connect() as conn, conn.cursor() as cur:
        cur.execute((REPO_ROOT / "sql" / "01_schema.sql").read_text())
        ref = lambda n: pd.read_csv(REFERENCE_DIR / n)  # noqa: E731
        copy_df(cur, "core.plant", ref("plant.csv"))
        copy_df(cur, "core.shop_floor", ref("shop_floor.csv"))
        copy_df(cur, "core.machine_type", ref("machine_type.csv"))
        copy_df(cur, "core.part_family", ref("part_master.csv"))
        m = ref("machine_master.csv")
        copy_df(cur, "core.machine", m[["machine_id", "machine_code", "plant_id", "shop_floor_id", "machine_type",
                                        "part_family_id", "controller", "uns_topic_root", "azure_model", "age_years",
                                        "commissioning_year"]])
        am = ref("alarm_master.csv")
        copy_df(cur, "core.alarm_master", am[["alarm_code", "alarm_name", "severity", "related_sensor", "source_event",
                                              "source_table", "n_events", "dominant_signal", "dominant_z",
                                              "mapping_note"]])

        md = pd.read_parquet(PROCESSED_DIR / "machine_data.parquet")
        md["ts"] = md["ts"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
        t1 = time.perf_counter()
        copy_df(cur, "core.machine_data", md)
        copy_secs = time.perf_counter() - t1
        ev = pd.read_parquet(PROCESSED_DIR / "events.parquet")
        ev["ts"] = ev["ts"].dt.strftime("%Y-%m-%d %H:%M:%S%z")
        copy_df(cur, "core.event", ev[["machine_id", "ts", "event_type", "source_code", "alarm_code", "source",
                                       "source_ts_2015"]])

        raw_counts = {name: load_raw(cur, name, df) for name, df in raw_sources().items()}
        conn.commit()

    with connect(autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("ANALYZE")
        cur.execute("""
            SELECT n.nspname || '.' || c.relname AS table_name, c.reltuples::bigint AS rows,
                   pg_total_relation_size(c.oid) AS total_bytes, pg_relation_size(c.oid) AS heap_bytes
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' AND n.nspname IN ('raw', 'core') ORDER BY total_bytes DESC""")
        sizes = pd.DataFrame(cur.fetchall(), columns=["table_name", "rows", "total_bytes", "heap_bytes"])
    sizes["bytes_per_row_incl_indexes"] = (sizes.total_bytes / sizes.rows.clip(lower=1)).round(1)
    sizes.to_csv(SQL_RESULTS_DIR / "00_table_sizes.csv", index=False)
    print(sizes.to_string(index=False))
    print(f"\nmachine_data COPY: {len(md):,} rows in {copy_secs:.1f} s ({len(md) / copy_secs:,.0f} rows/s); "
          f"raw tables: {sum(raw_counts.values()):,} rows; total {time.perf_counter() - t0:.0f} s")


if __name__ == "__main__":
    main()
