-- =====================================================================
-- Part D - the eight required analytical queries on core.machine_data
-- Each query is preceded by "-- @name <id>" so python/07_run_sql.py can
-- run it and save the result to sql/results/<id>.csv.
-- One row = one machine-hour. Timestamps are TIMESTAMPTZ; days are IST.
-- =====================================================================

-- @name q1_avg_temperature_per_machine
-- Q1. Average temperature per machine.
-- Logic: average only over hours when the spindle actually ran (RUNNING or ALARM
-- hours with running minutes > 0); a stopped machine's temperature would bias the mean.
SELECT m.machine_id, m.machine_code, p.plant_code,
       ROUND(AVG(md.temperature)::numeric, 2) AS avg_temperature_c,
       ROUND(MAX(md.temperature)::numeric, 2) AS max_temperature_c,
       COUNT(*)                               AS running_hours
FROM core.machine_data md
JOIN core.machine m USING (machine_id)
JOIN core.plant p   ON p.plant_id = m.plant_id
WHERE md.running_minutes > 0
GROUP BY m.machine_id, m.machine_code, p.plant_code
ORDER BY avg_temperature_c DESC;

-- @name q2_machine_most_parts
-- Q2. Machine that produced the most parts (ties kept with FETCH ... WITH TIES).
-- Logic: total production_count over the whole year per machine, highest first.
-- Cycle time differs by part family, so short-cycle machines (brake discs) lead.
SELECT m.machine_id, m.machine_code, pf.part_name, pf.cycle_time_min,
       SUM(md.production_count) AS total_parts
FROM core.machine_data md
JOIN core.machine m      USING (machine_id)
JOIN core.part_family pf ON pf.part_family_id = m.part_family_id
GROUP BY m.machine_id, m.machine_code, pf.part_name, pf.cycle_time_min
ORDER BY total_parts DESC
FETCH FIRST 1 ROWS WITH TIES;

-- @name q3_highest_avg_vibration
-- Q3. Machine with the highest average vibration (mm/s RMS) while running,
-- with its ISO 10816-3 zone. Top 10 shown for context; rank 1 is the answer.
SELECT RANK() OVER (ORDER BY AVG(md.vibration) DESC) AS rnk,
       m.machine_id, m.machine_code, m.machine_type,
       ROUND(AVG(md.vibration)::numeric, 3) AS avg_vibration_mm_s,
       ROUND(MAX(md.vibration)::numeric, 3) AS max_vibration_mm_s,
       CASE WHEN AVG(md.vibration) < 1.4 THEN 'A (good)'
            WHEN AVG(md.vibration) < 2.8 THEN 'B (acceptable)'
            WHEN AVG(md.vibration) < 4.5 THEN 'C (alert)'
            ELSE 'D (danger)' END AS iso_zone_of_average
FROM core.machine_data md
JOIN core.machine m USING (machine_id)
WHERE md.running_minutes > 0
GROUP BY m.machine_id, m.machine_code, m.machine_type
ORDER BY avg_vibration_mm_s DESC
LIMIT 10;

-- @name q4_alarm_count_per_machine
-- Q4. Alarm count per machine.
-- Logic: alarm_count = number of alarm events in the hour (an hour can hold more than one);
-- alarm_hours = hours flagged with an alarm; critical = failure-class alarms.
SELECT m.machine_id, m.machine_code,
       SUM(md.alarm_count)                                         AS alarm_events,
       COUNT(*) FILTER (WHERE md.alarm)                            AS alarm_hours,
       COUNT(*) FILTER (WHERE am.severity = 'CRITICAL')            AS critical_alarm_hours
FROM core.machine_data md
JOIN core.machine m            USING (machine_id)
LEFT JOIN core.alarm_master am ON am.alarm_code = md.alarm_code
GROUP BY m.machine_id, m.machine_code
ORDER BY alarm_events DESC, m.machine_id;

-- @name q5_parts_on_selected_day
-- Q5. Parts produced on a selected day (parameter: change the date in params).
-- Logic: the day is an IST calendar day [00:00, 24:00) Asia/Kolkata; half-open range keeps
-- the index on ts usable (no function applied to the column). Per plant + fleet total.
WITH params AS (SELECT DATE '2025-06-16' AS selected_day)          -- <== SELECTED DAY
SELECT COALESCE(p.plant_code, 'ALL') AS plant,
       SUM(md.production_count)       AS parts_produced,
       SUM(md.reject_count)           AS parts_rejected,
       (SELECT selected_day FROM params) AS selected_day
FROM core.machine_data md
JOIN core.plant p ON p.plant_id = md.plant_id
CROSS JOIN params
WHERE md.ts >= (params.selected_day::timestamp AT TIME ZONE 'Asia/Kolkata')
  AND md.ts <  ((params.selected_day + 1)::timestamp AT TIME ZONE 'Asia/Kolkata')
GROUP BY ROLLUP (p.plant_code)
ORDER BY plant;

-- @name q6_longest_operating_duration
-- Q6. Machine with the longest continuous operating duration.
-- Logic (gaps and islands): consecutive RUNNING hours of the same machine form an island.
-- ts - row_number() * 1 hour is constant inside an island, so it is the island key.
-- Total running hours (sum of running_minutes / 60) is reported alongside.
WITH runs AS (
    SELECT machine_id, ts,
           ts - (ROW_NUMBER() OVER (PARTITION BY machine_id ORDER BY ts)) * INTERVAL '1 hour' AS island
    FROM core.machine_data
    WHERE machine_status = 'RUNNING'
), islands AS (
    SELECT machine_id, MIN(ts) AS run_start, MAX(ts) + INTERVAL '1 hour' AS run_end,
           COUNT(*) AS run_hours
    FROM runs GROUP BY machine_id, island
), totals AS (
    SELECT machine_id, ROUND(SUM(running_minutes)::numeric / 60, 1) AS total_running_hours
    FROM core.machine_data GROUP BY machine_id
)
SELECT RANK() OVER (ORDER BY i.run_hours DESC) AS rnk,
       m.machine_code, i.run_start, i.run_end, i.run_hours AS longest_uninterrupted_running_hours,
       ROUND(i.run_hours / 24.0, 1) AS days, t.total_running_hours
FROM (SELECT DISTINCT ON (machine_id) * FROM islands ORDER BY machine_id, run_hours DESC) i
JOIN core.machine m USING (machine_id)
JOIN totals t       USING (machine_id)
ORDER BY rnk, m.machine_code
LIMIT 10;

-- @name q7_avg_rpm_while_running
-- Q7. Average RPM while running, per machine (and its machine type's nominal range).
-- Logic: only RUNNING hours; rpm is the mean spindle speed during the running minutes.
SELECT m.machine_id, m.machine_code, m.machine_type,
       ROUND(AVG(md.rpm)::numeric, 0) AS avg_rpm_running,
       mt.rpm_min, mt.rpm_max
FROM core.machine_data md
JOIN core.machine m       USING (machine_id)
JOIN core.machine_type mt ON mt.machine_type = m.machine_type
WHERE md.machine_status = 'RUNNING'
GROUP BY m.machine_id, m.machine_code, m.machine_type, mt.rpm_min, mt.rpm_max
ORDER BY m.machine_id;

-- @name q8_highest_rejection_rate
-- Q8. Machine with the highest rejection rate = SUM(reject_count) / SUM(production_count).
-- Ratio of sums (not average of hourly ratios), so low-volume hours are not over-weighted.
SELECT RANK() OVER (ORDER BY SUM(md.reject_count)::numeric / NULLIF(SUM(md.production_count), 0) DESC) AS rnk,
       m.machine_code, pf.part_name,
       SUM(md.production_count) AS produced, SUM(md.reject_count) AS rejected,
       ROUND(100.0 * SUM(md.reject_count) / NULLIF(SUM(md.production_count), 0), 3) AS rejection_rate_pct
FROM core.machine_data md
JOIN core.machine m      USING (machine_id)
JOIN core.part_family pf ON pf.part_family_id = m.part_family_id
GROUP BY m.machine_code, pf.part_name
ORDER BY rnk
LIMIT 10;
