-- =====================================================================
-- Industrial Data Platform - PostgreSQL schema (PostgreSQL 16/17)
--   raw       : source datasets loaded as-is (traceability)
--   core      : master data + integrated fleet fact table
--   analytics : views / materialized views for the dashboard
-- Rerunnable: drops and recreates core + analytics objects.
-- =====================================================================

-- All plants are in India: show TIMESTAMPTZ values in IST for every client (psql, pgAdmin, Python)
DO $$ BEGIN EXECUTE format('ALTER DATABASE %I SET timezone = %L', current_database(), 'Asia/Kolkata'); END $$;

CREATE SCHEMA IF NOT EXISTS raw;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS analytics;

DROP SCHEMA IF EXISTS analytics CASCADE;
CREATE SCHEMA analytics;
DROP TABLE IF EXISTS core.machine_data, core.event, core.machine, core.part_family,
                     core.machine_type, core.shop_floor, core.plant, core.alarm_master CASCADE;
DROP TYPE IF EXISTS core.machine_status_t CASCADE;

-- Machine status as an ENUM: compact (4 bytes), self-validating, ordered
CREATE TYPE core.machine_status_t AS ENUM ('RUNNING', 'IDLE', 'ALARM', 'MAINTENANCE', 'OFF');

-- ---------------------------------------------------------------- master data
CREATE TABLE core.plant (
    plant_id     SMALLINT PRIMARY KEY,
    plant_code   VARCHAR(4)   NOT NULL UNIQUE,
    plant_name   VARCHAR(80)  NOT NULL,
    location     VARCHAR(80)  NOT NULL,
    state        VARCHAR(40)  NOT NULL,
    latitude     NUMERIC(8,5) CHECK (latitude BETWEEN -90 AND 90),
    longitude    NUMERIC(8,5) CHECK (longitude BETWEEN -180 AND 180),
    slug         VARCHAR(20)  NOT NULL UNIQUE
);

CREATE TABLE core.shop_floor (
    shop_floor_id          SMALLINT PRIMARY KEY,
    plant_id               SMALLINT NOT NULL REFERENCES core.plant,
    slug                   VARCHAR(20) NOT NULL,
    shop_floor_name        VARCHAR(80) NOT NULL,
    first_machine_id       SMALLINT NOT NULL,
    last_machine_id        SMALLINT NOT NULL CHECK (last_machine_id >= first_machine_id),
    anchoring_real_dataset VARCHAR(120)
);

CREATE TABLE core.machine_type (
    machine_type     VARCHAR(8) PRIMARY KEY,
    description      VARCHAR(60) NOT NULL,
    rpm_min          INTEGER NOT NULL CHECK (rpm_min > 0),
    rpm_max          INTEGER NOT NULL CHECK (rpm_max > rpm_min),
    rated_power_kw   NUMERIC(6,2) NOT NULL CHECK (rated_power_kw > 0),
    supply_voltage_v SMALLINT NOT NULL,
    power_factor     NUMERIC(3,2) NOT NULL CHECK (power_factor BETWEEN 0 AND 1),
    rated_current_a  NUMERIC(6,1) NOT NULL
);

CREATE TABLE core.part_family (
    part_family_id      SMALLINT PRIMARY KEY,
    part_code           VARCHAR(6)  NOT NULL UNIQUE,
    part_name           VARCHAR(60) NOT NULL,
    plant_id            SMALLINT    NOT NULL REFERENCES core.plant,
    machine_type        VARCHAR(8)  NOT NULL REFERENCES core.machine_type,
    cycle_time_min      NUMERIC(5,2) NOT NULL CHECK (cycle_time_min > 0),
    cycle_time_low_min  NUMERIC(5,2) NOT NULL,
    cycle_time_high_min NUMERIC(5,2) NOT NULL,
    material            VARCHAR(40),
    CHECK (cycle_time_low_min <= cycle_time_min AND cycle_time_min <= cycle_time_high_min)
);

CREATE TABLE core.machine (
    machine_id         SMALLINT PRIMARY KEY CHECK (machine_id BETWEEN 1 AND 100),
    machine_code       VARCHAR(16) NOT NULL UNIQUE,
    plant_id           SMALLINT    NOT NULL REFERENCES core.plant,
    shop_floor_id      SMALLINT    NOT NULL REFERENCES core.shop_floor,
    machine_type       VARCHAR(8)  NOT NULL REFERENCES core.machine_type,
    part_family_id     SMALLINT    NOT NULL REFERENCES core.part_family,
    controller         VARCHAR(40) NOT NULL,
    uns_topic_root     VARCHAR(80) NOT NULL UNIQUE,   -- MQTT Unified Namespace root
    azure_model        VARCHAR(10),                   -- traceability to Azure PdM machines.csv
    age_years          SMALLINT CHECK (age_years >= 0),
    commissioning_year SMALLINT
);

CREATE TABLE core.alarm_master (
    alarm_code      VARCHAR(8) PRIMARY KEY,
    alarm_name      VARCHAR(80) NOT NULL,
    severity        VARCHAR(10) NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'CRITICAL')),
    related_sensor  VARCHAR(40),
    source_event    VARCHAR(10) NOT NULL UNIQUE,      -- Azure errorID / failure component
    source_table    VARCHAR(10) NOT NULL,
    n_events        INTEGER,
    dominant_signal VARCHAR(12),
    dominant_z      REAL,
    mapping_note    TEXT
);
COMMENT ON TABLE core.alarm_master IS 'Illustrative mapping of Azure PdM benchmark events to CNC alarm names (named after the dominant pre-event telemetry shift).';

-- ---------------------------------------------------------------- fact table
-- One row per machine per hour. Columns other than machine_id / source_ts_2015 are DERIVED
-- (see data/DATA_PROVENANCE.md).
CREATE TABLE core.machine_data (
    machine_id             SMALLINT    NOT NULL REFERENCES core.machine,
    ts                     TIMESTAMPTZ NOT NULL,
    plant_id               SMALLINT    NOT NULL REFERENCES core.plant,
    part_family_id         SMALLINT    NOT NULL REFERENCES core.part_family,
    shift                  CHAR(1)     NOT NULL CHECK (shift IN ('A', 'B', 'C')),
    temperature            REAL        CHECK (temperature BETWEEN -20 AND 150),        -- deg C
    vibration              REAL        CHECK (vibration >= 0),                         -- mm/s RMS
    rpm                    REAL        CHECK (rpm >= 0),                               -- rev/min
    current                REAL        CHECK (current >= 0),                           -- A
    production_count       INTEGER     NOT NULL DEFAULT 0 CHECK (production_count >= 0),
    reject_count           INTEGER     NOT NULL DEFAULT 0 CHECK (reject_count >= 0),
    machine_status         core.machine_status_t NOT NULL,
    alarm                  BOOLEAN     NOT NULL DEFAULT FALSE,
    alarm_code             VARCHAR(8)  REFERENCES core.alarm_master,
    alarm_count            SMALLINT    NOT NULL DEFAULT 0 CHECK (alarm_count >= 0),
    tool_wear_min          REAL        CHECK (tool_wear_min >= 0),
    running_minutes        REAL        NOT NULL CHECK (running_minutes BETWEEN 0 AND 60),
    spindle_load_pct       REAL        CHECK (spindle_load_pct BETWEEN 0 AND 150),
    power_kw               REAL        CHECK (power_kw >= 0),
    hydraulic_pressure_bar REAL,
    ambient_c              REAL,
    ideal_count            REAL        CHECK (ideal_count >= 0),
    reject_probability     REAL        CHECK (reject_probability BETWEEN 0 AND 1),
    source_ts_2015         TIMESTAMP   NOT NULL,                                       -- Azure source row
    PRIMARY KEY (machine_id, ts),
    CHECK (reject_count <= production_count),
    CHECK (alarm = (alarm_code IS NOT NULL))
);
-- PK already gives a (machine_id, ts) B-tree; add time-first and plant/time access paths
CREATE INDEX ix_machine_data_ts        ON core.machine_data (ts);
CREATE INDEX ix_machine_data_plant_ts  ON core.machine_data (plant_id, ts);
CREATE INDEX ix_machine_data_alarm     ON core.machine_data (machine_id, ts) WHERE alarm;   -- partial: ~0.5 % of rows

CREATE TABLE core.event (
    event_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    machine_id     SMALLINT    NOT NULL REFERENCES core.machine,
    ts             TIMESTAMPTZ NOT NULL,
    event_type     VARCHAR(24) NOT NULL CHECK (event_type IN ('ERROR', 'FAILURE', 'REPAIR', 'SCHEDULED_MAINTENANCE')),
    source_code    VARCHAR(10) NOT NULL,
    alarm_code     VARCHAR(8)  REFERENCES core.alarm_master,
    source         VARCHAR(16) NOT NULL,
    source_ts_2015 TIMESTAMP   NOT NULL
);
CREATE INDEX ix_event_machine_ts ON core.event (machine_id, ts);

-- View exposing the assignment's required column names exactly
CREATE VIEW analytics.v_machine_data_required AS
SELECT md.machine_id       AS "Machine_ID",
       md.ts               AS "Timestamp",
       md.temperature      AS "Temperature",
       md.vibration        AS "Vibration",
       md.rpm              AS "RPM",
       md.current          AS "Current",
       md.production_count AS "Production_Count",
       md.machine_status   AS "Machine_Status",
       md.alarm            AS "Alarm",
       md.alarm_code       AS "Alarm_Code",
       md.reject_count     AS "Reject_Count"
FROM core.machine_data md;

-- =====================================================================
-- PRODUCTION PATH (commented): TimescaleDB on the same schema.
-- Plain PostgreSQL is the working default for this project.
-- =====================================================================
-- CREATE EXTENSION IF NOT EXISTS timescaledb;
-- -- Convert the fact table into a hypertable partitioned by time (7-day chunks)
-- SELECT create_hypertable('core.machine_data', by_range('ts', INTERVAL '7 days'), migrate_data => TRUE);
--
-- -- Continuous aggregate: daily KPIs per machine, refreshed automatically
-- CREATE MATERIALIZED VIEW analytics.cagg_machine_daily
-- WITH (timescaledb.continuous) AS
-- SELECT machine_id, time_bucket(INTERVAL '1 day', ts) AS day,
--        SUM(production_count) AS parts, SUM(reject_count) AS rejects,
--        AVG(temperature) AS avg_temp, AVG(vibration) AS avg_vib, MAX(vibration) AS max_vib,
--        SUM(running_minutes) / 60.0 AS running_h
-- FROM core.machine_data GROUP BY machine_id, day WITH NO DATA;
-- SELECT add_continuous_aggregate_policy('analytics.cagg_machine_daily',
--        start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour', schedule_interval => INTERVAL '1 hour');
--
-- -- Native columnar compression after 30 days (typically 90 %+ smaller for sensor data)
-- ALTER TABLE core.machine_data SET (timescaledb.compress,
--        timescaledb.compress_segmentby = 'machine_id', timescaledb.compress_orderby = 'ts DESC');
-- SELECT add_compression_policy('core.machine_data', INTERVAL '30 days');
-- -- Retention: keep hourly detail for 2 years (daily aggregates kept indefinitely)
-- SELECT add_retention_policy('core.machine_data', INTERVAL '730 days');
