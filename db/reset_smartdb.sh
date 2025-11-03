#!/bin/bash 
#Run script with admin rights ---> sudo -s db/reset_smartdb.sh
set -euo pipefail

DB_NAME="${DB_NAME:-smartdb}"
ADMIN_USER="${ADMIN_USER:-postgres}"      # superuser to administrate
APP_ROLE="${APP_ROLE:-smart}"
APP_PASS="${APP_PASS:-smartpass}"
SCHEMA_FILE="${SCHEMA_FILE:-/vagrant/Smart-Monitor/db/schema_pg.sql}"

echo ">>> Stop writers ..."
systemctl stop smart-monitor >/dev/null 2>&1 || true
systemctl stop smart-monitor-gui >/dev/null 2>&1 || true
echo ">>> (Reminder) Stop Windows writer if running:  nssm stop SmartMonitor"

echo ">>> Terminate sessions to ${DB_NAME} ..."
sudo -u "${ADMIN_USER}" psql -v ON_ERROR_STOP=1 -d postgres <<'SQL'
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'smartdb' AND pid <> pg_backend_pid();
SQL

echo ">>> Drop & recreate ${DB_NAME} ..."
sudo -u "${ADMIN_USER}" psql -v ON_ERROR_STOP=1 -d postgres <<'SQL'
DROP DATABASE IF EXISTS smartdb;
CREATE DATABASE smartdb;
SQL

echo ">>> Ensure app role exists + can login (md5 password) ..."
sudo -u "${ADMIN_USER}" psql -v ON_ERROR_STOP=1 -d smartdb <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='smart') THEN
    CREATE ROLE smart LOGIN;
  ELSE
    ALTER ROLE smart LOGIN;
  END IF;
END$$;
SQL
sudo -u "${ADMIN_USER}" psql -v ON_ERROR_STOP=1 -d smartdb -c \
  "ALTER ROLE ${APP_ROLE} WITH ENCRYPTED PASSWORD '${APP_PASS}';"

echo ">>> Apply schema fresh ..."
sudo -u "${ADMIN_USER}" psql -v ON_ERROR_STOP=1 -d smartdb -f "${SCHEMA_FILE}"

echo ">>> Grant privileges to ${APP_ROLE} ..."
sudo -u "${ADMIN_USER}" psql -v ON_ERROR_STOP=1 -d smartdb <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO smart;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO smart;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO smart;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO smart;
SQL

echo ">>> Smoke test as app role ..."
PGPASSWORD="${APP_PASS}" psql -v ON_ERROR_STOP=1 -h 127.0.0.1 -U "${APP_ROLE}" -d smartdb <<'SQL'
INSERT INTO alerts(hostname,severity,source,message)
VALUES ('reset-check','info','reset','fresh database created');
SELECT COUNT(*) as alerts_cnt FROM alerts;
SQL

echo ">>> Done. Start writers when ready:"
echo "    Linux: systemctl start smart-monitor smart-monitor-gui"
echo "    Windows: nssm start SmartMonitor"

