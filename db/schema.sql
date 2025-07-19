---- schema.sql

-- Table for system resource monitoring (CPU, memory, disk, etc.)
CREATE TABLE IF NOT EXISTS system_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT NOT NULL,
    os_platform TEXT,
    cpu_usage REAL,
    memory_usage REAL,
    disk_usage REAL,
    temperature REAL,
    uptime INTEGER,               -- in seconds
    process_count INTEGER,
    load_average REAL,
    inode_usage REAL
);

-- Table for network connectivity logs
CREATE TABLE IF NOT EXISTS network_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT NOT NULL,       -- machine performing the test
    target TEXT NOT NULL,         -- IP or domain being tested
    method TEXT NOT NULL,         -- ping, nslookup, traceroute
    result TEXT,                  -- raw output or summary
    latency_ms REAL,              -- optional for ping
    packet_loss_percent REAL,     -- optional for ping/traceroute
    status TEXT                   -- success, fail, unreachable
);

-- Table to log process status --
CREATE TABLE IF NOT EXISTS process_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT NOT NULL,
    os_platform TEXT,
    pid INTEGER,
    process_name TEXT,
    raw_status TEXT,
    normalized_status TEXT,
    cpu_percent REAL,
    memory_percent REAL
);

-- Table for service status monitoring
CREATE TABLE IF NOT EXISTS service_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT NOT NULL,
    os_platform TEXT NOT NULL,
    service_name TEXT NOT NULL,
    raw_status TEXT NOT NULL,                 -- running, stopped, paused, etc.
    normalized_status TEXT NOT NULL,           -- human readble status
    sub_state TEXT,                           -- systemd SubState (e.g. running, dead)
    service_type TEXT,                        -- systemd Type (e.g. simple, forking)
    unit_file_state TEXT,                     -- enabled, static, masked, linked
    recoverable BOOLEAN DEFAULT FALSE         -- Whether it’s safe to restart
);

-- Table to log system alerts and anomalies
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT,
    severity TEXT NOT NULL,       -- info, warning, critical
    source TEXT NOT NULL,         -- CPU, Memory, Service, Network, etc.
    message TEXT                  -- human-readable alert
);

-- Table to log recovery actions --
CREATE TABLE IF NOT EXISTS recovery_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT,
    os_platform TEXT NOT NULL,
    service_name TEXT NOT NULL,
    result TEXT,                 -- success or fail
    error_message TEXT           -- optional error detail
);

-- Table to log restart attempts --
CREATE TABLE IF NOT EXISTS restart_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    hostname TEXT NOT NULL,
    service_name TEXT NOT NULL
)