-- schema_pg.sql

-- system_metrics
CREATE TABLE IF NOT EXISTS system_metrics (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"   TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname      TEXT NOT NULL,
  os_platform   TEXT,
  cpu_usage     DOUBLE PRECISION,
  memory_usage  DOUBLE PRECISION,
  disk_usage    DOUBLE PRECISION,
  temperature   DOUBLE PRECISION,
  uptime        BIGINT,
  process_count INTEGER,
  load_average  DOUBLE PRECISION,
  inode_usage   DOUBLE PRECISION,
  swap_usage    DOUBLE PRECISION
);

-- network_logs
CREATE TABLE IF NOT EXISTS network_logs (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"         TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname            TEXT NOT NULL,
  target              TEXT NOT NULL,
  method              TEXT NOT NULL,
  result              TEXT,
  latency_ms          DOUBLE PRECISION,
  packet_loss_percent DOUBLE PRECISION,
  status              TEXT
);

-- process_status
CREATE TABLE IF NOT EXISTS process_status (
  id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"       TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname          TEXT NOT NULL,
  os_platform       TEXT,
  pid               INTEGER,
  process_name      TEXT,
  raw_status        TEXT,
  normalized_status TEXT,
  cpu_percent       DOUBLE PRECISION,
  memory_percent    DOUBLE PRECISION
);

-- service_status (Postgres, schema-safe)
CREATE TABLE IF NOT EXISTS service_status (
  id                 BIGSERIAL PRIMARY KEY,
  "timestamp"        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  hostname           TEXT NOT NULL,
  os_platform        TEXT NOT NULL,
  service_name       TEXT NOT NULL,
  raw_status         TEXT NOT NULL,
  normalized_status  TEXT NOT NULL,
  sub_state          TEXT,
  service_type       TEXT,
  unit_file_state    TEXT,
  recoverable        BOOLEAN NOT NULL DEFAULT FALSE,
  ts_epoch           BIGINT GENERATED ALWAYS AS (EXTRACT(EPOCH FROM "timestamp")) STORED
);

CREATE INDEX IF NOT EXISTS idx_ss_host_os_svc_ts
  ON service_status(hostname, os_platform, service_name, ts_epoch DESC);

CREATE INDEX IF NOT EXISTS idx_ss_status_ts
  ON service_status(normalized_status, ts_epoch DESC);



-- alerts
CREATE TABLE IF NOT EXISTS alerts (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp" TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname    TEXT,
  severity    TEXT NOT NULL,
  source      TEXT NOT NULL,
  message     TEXT
);

-- recovery_logs
CREATE TABLE IF NOT EXISTS recovery_logs (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"   TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname      TEXT,
  os_platform   TEXT NOT NULL,
  service_name  TEXT NOT NULL,
  result        TEXT,
  error_message TEXT
);

-- restart_attempts
CREATE TABLE IF NOT EXISTS restart_attempts (
  id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"  TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname     TEXT NOT NULL,
  service_name TEXT NOT NULL
);

-- smart_health
CREATE TABLE IF NOT EXISTS smart_health (
  id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp" TIMESTAMPTZ NOT NULL DEFAULT now(),
  hostname    TEXT NOT NULL,
  device      TEXT NOT NULL,
  health      TEXT,
  model       TEXT,
  temp_c      DOUBLE PRECISION,
  output      TEXT
);

-- ─────────────────────────────────────────────
-- Kubernetes v1: Cluster API health
-- Focus: can Smart-Monitor talk to the API?
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS k8s_cluster_health (
  id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"   TIMESTAMPTZ NOT NULL DEFAULT now(),
  cluster_name  TEXT NOT NULL,        -- e.g. 'kind-smart-monitor'
  api_reachable BOOLEAN NOT NULL,     -- TRUE if API responded successfully
  k8s_version   TEXT                  -- e.g. 'v1.34.0'
);

CREATE INDEX IF NOT EXISTS idx_k8s_cluster_health_name_ts
  ON k8s_cluster_health (cluster_name, "timestamp" DESC);

-- ─────────────────────────────────────────────
-- Kubernetes v1: Critical pod failures
-- Focus: CrashLoopBackOff, ImagePullBackOff, OOMKilled, long Pending
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS k8s_pod_health (
  id                      BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  "timestamp"             TIMESTAMPTZ NOT NULL DEFAULT now(),

  cluster_name            TEXT NOT NULL,
  namespace               TEXT NOT NULL,
  pod_name                TEXT NOT NULL,

  phase                   TEXT,       -- Running / Pending / Failed / Unknown

  -- High-level categorization of the problem:
  -- 'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull',
  -- 'OOMKilled', 'LongPending', 'Other'
  problem_type            TEXT,
  problem_reason          TEXT,       -- reason from container state / event
  problem_message         TEXT,       -- human-readable message from K8s

  total_restart_count     INTEGER,    -- sum of restartCount across containers

  last_exit_code          INTEGER,    -- from lastState.terminated.exitCode
  last_termination_reason TEXT,       -- e.g. 'OOMKilled', 'Error'
  last_termination_oom    BOOLEAN     -- TRUE if last termination was OOMKilled
);

CREATE INDEX IF NOT EXISTS idx_k8s_pod_health_cluster_ns_pod_ts
  ON k8s_pod_health (cluster_name, namespace, pod_name, "timestamp" DESC);

CREATE INDEX IF NOT EXISTS idx_k8s_pod_health_problem_ts
  ON k8s_pod_health (problem_type, "timestamp" DESC);

