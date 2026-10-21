-- =====================================================================
-- Part D (bonus) - advanced analytics: OEE, MTBF/MTTR, shifts, alarm Pareto,
-- trends with window functions, vibration anomalies, dashboard views.
-- Run with python/07_run_sql.py (results -> sql/results/<name>.csv).
-- =====================================================================

-- @name a1_oee_per_machine
-- OEE = Availability x Performance x Quality (each from sums, not averages of ratios).
--   Availability = running minutes / planned production minutes (planned = all hours except OFF)
--   Performance  = actual parts / ideal parts at nominal cycle time in the running minutes
--   Quality      = good parts / all parts
WITH k AS (
    SELECT machine_id,
           SUM(running_minutes)                                       AS run_min,
           60.0 * COUNT(*) FILTER (WHERE machine_status <> 'OFF')     AS planned_min,
           SUM(production_count)                                      AS parts,
           SUM(ideal_count)                                           AS ideal_parts,
           SUM(reject_count)                                          AS rejects
    FROM core.machine_data GROUP BY machine_id
)
SELECT m.machine_code, p.plant_code, m.machine_type,
       ROUND((run_min / planned_min)::numeric, 4)                     AS availability,
       ROUND(LEAST(parts / NULLIF(ideal_parts, 0), 1)::numeric, 4)    AS performance,
       ROUND(((parts - rejects)::numeric / NULLIF(parts, 0)), 4)      AS quality,
       ROUND((run_min / planned_min * LEAST(parts / NULLIF(ideal_parts, 0), 1)
              * (parts - rejects) / NULLIF(parts, 0))::numeric, 4)    AS oee
FROM k JOIN core.machine m USING (machine_id) JOIN core.plant p ON p.plant_id = m.plant_id
ORDER BY oee;

-- @name a2_oee_per_plant_month
-- OEE per plant per month (IST), plus the plant's full-year figure via GROUPING SETS.
WITH k AS (
    SELECT p.plant_code, date_trunc('month', md.ts AT TIME ZONE 'Asia/Kolkata')::date AS month,
           SUM(running_minutes) AS run_min, 60.0 * COUNT(*) FILTER (WHERE machine_status <> 'OFF') AS planned_min,
           SUM(production_count) AS parts, SUM(ideal_count) AS ideal_parts, SUM(reject_count) AS rejects
    FROM core.machine_data md JOIN core.plant p ON p.plant_id = md.plant_id
    WHERE md.ts < TIMESTAMPTZ '2026-01-01 00:00+05:30'
    GROUP BY GROUPING SETS ((p.plant_code, date_trunc('month', md.ts AT TIME ZONE 'Asia/Kolkata')::date),
                            (p.plant_code))
)
SELECT plant_code, COALESCE(month::text, 'FULL YEAR') AS month,
       ROUND((run_min / planned_min)::numeric, 4) AS availability,
       ROUND(LEAST(parts / ideal_parts, 1)::numeric, 4) AS performance,
       ROUND(((parts - rejects)::numeric / parts), 4) AS quality,
       ROUND((run_min / planned_min * LEAST(parts / ideal_parts, 1) * (parts - rejects) / parts)::numeric, 4) AS oee
FROM k ORDER BY plant_code, month NULLS LAST;

-- @name a3_mtbf_mttr_per_machine
-- MTBF = running hours / number of failures; MTTR = mean length of the MAINTENANCE island
-- that starts within 2 h after each failure (gaps-and-islands on status).
WITH maint_runs AS (
    SELECT machine_id, ts,
           ts - (ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY ts)) * INTERVAL '1 hour' AS island
    FROM core.machine_data WHERE machine_status = 'MAINTENANCE'
), maint_islands AS (
    SELECT machine_id, MIN(ts) AS start_ts, COUNT(*) AS hours FROM maint_runs GROUP BY machine_id, island
), repairs AS (
    SELECT f.machine_id, f.ts AS failure_ts, mi.hours AS repair_hours
    FROM core.event f
    JOIN LATERAL (SELECT hours FROM maint_islands mi
                  WHERE mi.machine_id = f.machine_id AND mi.start_ts > f.ts
                    AND mi.start_ts <= f.ts + INTERVAL '2 hours'
                  ORDER BY mi.start_ts LIMIT 1) mi ON TRUE
    WHERE f.event_type = 'FAILURE'
), run AS (
    SELECT machine_id, SUM(running_minutes) / 60.0 AS running_hours FROM core.machine_data GROUP BY machine_id
)
SELECT m.machine_code, p.plant_code,
       COUNT(r.failure_ts)                                   AS failures,
       ROUND(run.running_hours::numeric, 0)                  AS running_hours,
       ROUND((run.running_hours / NULLIF(COUNT(r.failure_ts), 0))::numeric, 0) AS mtbf_hours,
       ROUND(AVG(r.repair_hours)::numeric, 1)                AS mttr_hours,
       ROUND((1 - AVG(r.repair_hours) / NULLIF(run.running_hours / NULLIF(COUNT(r.failure_ts), 0)
              + AVG(r.repair_hours), 0))::numeric, 4)        AS inherent_availability
FROM core.machine m
JOIN core.plant p ON p.plant_id = m.plant_id
JOIN run USING (machine_id)
LEFT JOIN repairs r USING (machine_id)
GROUP BY m.machine_code, p.plant_code, run.running_hours
ORDER BY mtbf_hours NULLS LAST;

-- @name a4_shift_production
-- Shift-wise production and quality per plant (A 06-14, B 14-22, C 22-06 IST).
SELECT p.plant_code, md.shift,
       SUM(md.production_count) AS parts,
       SUM(md.reject_count)     AS rejects,
       ROUND(100.0 * SUM(md.reject_count) / NULLIF(SUM(md.production_count), 0), 3) AS reject_rate_pct,
       ROUND(SUM(md.running_minutes)::numeric / 60, 0) AS running_hours,
       COUNT(*) FILTER (WHERE md.alarm) AS alarm_hours,
       ROUND(100.0 * SUM(md.production_count) / SUM(SUM(md.production_count)) OVER (PARTITION BY p.plant_code), 2)
           AS share_of_plant_output_pct
FROM core.machine_data md JOIN core.plant p ON p.plant_id = md.plant_id
GROUP BY p.plant_code, md.shift ORDER BY p.plant_code, md.shift;

-- @name a5_alarm_pareto
-- Alarm Pareto: events per alarm type with cumulative share (80/20 view).
WITH c AS (
    SELECT e.alarm_code, COUNT(*) AS events
    FROM core.event e WHERE e.event_type IN ('ERROR', 'FAILURE') GROUP BY e.alarm_code
)
SELECT am.alarm_code, am.alarm_name, am.severity, c.events,
       ROUND(100.0 * c.events / SUM(c.events) OVER (), 2) AS pct,
       ROUND(100.0 * SUM(c.events) OVER (ORDER BY c.events DESC, am.alarm_code
                                         ROWS UNBOUNDED PRECEDING) / SUM(c.events) OVER (), 2) AS cumulative_pct
FROM c JOIN core.alarm_master am USING (alarm_code)
ORDER BY c.events DESC;

-- @name a6_daily_trend_window
-- Daily fleet output with 7-day moving average, day-over-day change (LAG) and
-- rank of the day within its month (window functions over an aggregate).
WITH d AS (
    SELECT (ts AT TIME ZONE 'Asia/Kolkata')::date AS day,
           SUM(production_count) AS parts, SUM(reject_count) AS rejects,
           COUNT(*) FILTER (WHERE alarm) AS alarm_hours
    FROM core.machine_data GROUP BY 1
)
SELECT day, parts, rejects, alarm_hours,
       ROUND(AVG(parts) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 0) AS parts_ma7,
       parts - LAG(parts) OVER (ORDER BY day) AS dod_change,
       RANK() OVER (PARTITION BY date_trunc('month', day) ORDER BY parts DESC) AS rank_in_month
FROM d ORDER BY day;

-- @name a7_vibration_anomalies
-- Vibration anomalies vs each machine's rolling 7-day (168 h) baseline of running hours:
-- z = (v - mean_prev168) / std_prev168, anomaly if z > 3. Then: how many anomalies were
-- followed by a failure on the same machine within 48 h (early-warning value).
WITH base AS (
    SELECT machine_id, ts, vibration,
           AVG(vibration)         OVER w AS mu,
           STDDEV_SAMP(vibration) OVER w AS sd
    FROM core.machine_data
    WHERE machine_status = 'RUNNING'
    WINDOW w AS (PARTITION BY machine_id ORDER BY ts ROWS BETWEEN 168 PRECEDING AND 1 PRECEDING)
), anom AS (
    SELECT machine_id, ts, vibration, mu, (vibration - mu) / NULLIF(sd, 0) AS z
    FROM base WHERE (vibration - mu) / NULLIF(sd, 0) > 3
), flagged AS (
    SELECT a.*, EXISTS (SELECT 1 FROM core.event e
                        WHERE e.machine_id = a.machine_id AND e.event_type = 'FAILURE'
                          AND e.ts > a.ts AND e.ts <= a.ts + INTERVAL '48 hours') AS failure_within_48h
    FROM anom a
)
SELECT m.machine_code, COUNT(*) AS anomalies,
       COUNT(*) FILTER (WHERE failure_within_48h) AS followed_by_failure_48h,
       ROUND(100.0 * COUNT(*) FILTER (WHERE failure_within_48h) / COUNT(*), 1) AS precision_pct,
       ROUND(MAX(z)::numeric, 2) AS max_z, ROUND(MAX(vibration)::numeric, 2) AS max_vibration_mm_s
FROM flagged JOIN core.machine m USING (machine_id)
GROUP BY m.machine_code ORDER BY anomalies DESC;

-- @name a8_tool_wear_vs_quality
-- Reject rate by tool-wear band: shows the wear -> scrap relationship built from UMich/AI4I.
SELECT width_bucket(tool_wear_min, 0, 240, 8) AS wear_band,
       MIN(tool_wear_min)::int || '-' || MAX(tool_wear_min)::int AS wear_range_min,
       SUM(production_count) AS parts, SUM(reject_count) AS rejects,
       ROUND(100.0 * SUM(reject_count) / NULLIF(SUM(production_count), 0), 3) AS reject_rate_pct
FROM core.machine_data WHERE production_count > 0
GROUP BY 1 ORDER BY 1;

-- @name a9_create_dashboard_views
-- Materialized views for the dashboard (refresh after each load):
--   mv_machine_daily : one row per machine per IST day
--   v_machine_health  : latest 24 h health snapshot per machine (0-100 score)
CREATE MATERIALIZED VIEW analytics.mv_machine_daily AS
SELECT md.machine_id, md.plant_id, (md.ts AT TIME ZONE 'Asia/Kolkata')::date AS day,
       SUM(production_count) AS parts, SUM(reject_count) AS rejects, SUM(ideal_count) AS ideal_parts,
       SUM(running_minutes) AS run_min, 60.0 * COUNT(*) FILTER (WHERE machine_status <> 'OFF') AS planned_min,
       AVG(temperature) FILTER (WHERE running_minutes > 0) AS avg_temp,
       AVG(vibration)   FILTER (WHERE running_minutes > 0) AS avg_vib,
       MAX(vibration) AS max_vib, AVG(current) FILTER (WHERE running_minutes > 0) AS avg_current,
       SUM(alarm_count) AS alarms, MAX(tool_wear_min) AS max_tool_wear
FROM core.machine_data md GROUP BY 1, 2, 3;
CREATE UNIQUE INDEX ON analytics.mv_machine_daily (machine_id, day);

CREATE VIEW analytics.v_machine_health AS
WITH last24 AS (
    SELECT machine_id, AVG(vibration) FILTER (WHERE running_minutes > 0) AS vib,
           AVG(temperature) FILTER (WHERE running_minutes > 0) AS temp,
           SUM(alarm_count) AS alarms, MAX(tool_wear_min) AS wear
    FROM core.machine_data
    WHERE ts > (SELECT MAX(ts) FROM core.machine_data) - INTERVAL '24 hours'
    GROUP BY machine_id
)
SELECT machine_id, vib, temp, alarms, wear,
       GREATEST(0, LEAST(100, ROUND((100
           - 25 * GREATEST(0, (vib - 1.8) / 1.2)       -- vibration above zone-B centre
           - 10 * GREATEST(0, (temp - 40) / 5)          -- temperature above 40 deg C
           - 15 * LEAST(alarms, 3)                      -- recent alarms
           - 10 * wear / 240)::numeric, 0))) AS health_score
FROM last24;

-- @name a10_view_check
SELECT 'mv_machine_daily' AS object, COUNT(*) AS rows FROM analytics.mv_machine_daily
UNION ALL SELECT 'v_machine_health', COUNT(*) FROM analytics.v_machine_health
UNION ALL SELECT 'v_machine_data_required', COUNT(*) FROM analytics.v_machine_data_required;
