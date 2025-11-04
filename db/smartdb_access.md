### Here is a step by step process to grant access to Smartdb Database

---

1) Run as a user that can sudo 
```shell
sudo -s db/reset_smartdb
```

2) Stop writers (ignore errors if not running)
```shell
systemctl stop smart-monitor 2>/dev/null || true
systemctl stop smart-monitor-gui 2>/dev/null || true

```

3) Terminate any open sessions to smartdb
```shell
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'smartdb' AND pid <> pg_backend_pid();
"
```
4) Drop & recreate database
```shell
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS smartdb;"
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE smartdb;"

```
5) Ensure app role exists and set password
```shell
sudo -u postgres psql -d smartdb -v ON_ERROR_STOP=1 -c "
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smart') THEN
    CREATE ROLE smart LOGIN;
  ELSE
    ALTER ROLE smart LOGIN;
  END IF;
END
\$\$;
"
sudo -u postgres psql -d smartdb -v ON_ERROR_STOP=1 -c "ALTER ROLE smart WITH ENCRYPTED PASSWORD 'smartpass';"

```
6) Make smart the owner of DB & schema (so migrations/ALTERs work)
```shell
sudo -u postgres psql -d postgres -v ON_ERROR_STOP=1 -c "ALTER DATABASE smartdb OWNER TO smart;"
sudo -u postgres psql -d smartdb  -v ON_ERROR_STOP=1 -c "ALTER SCHEMA public OWNER TO smart;"

```
7) Apply your schema as the app role (so all objects are owned by smart)
```shell
PGPASSWORD='smartpass' psql -h 127.0.0.1 -U smart -d smartdb -v ON_ERROR_STOP=1 -f /vagrant/Smart-Monitor/db/schema_pg.sql

```
8) (Optional) Grant privileges (not strictly needed if smart owns everything)
```shell
sudo -u postgres psql -d smartdb -v ON_ERROR_STOP=1 -c "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO smart;"
sudo -u postgres psql -d smartdb -v ON_ERROR_STOP=1 -c "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO smart;"
sudo -u postgres psql -d smartdb -v ON_ERROR_STOP=1 -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO smart;"
sudo -u postgres psql -d smartdb -v ON_ERROR_STOP=1 -c "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO smart;"

```
9) Quick smoke test as smart
```shell
PGPASSWORD='smartpass' psql -h 127.0.0.1 -U smart -d smartdb -v ON_ERROR_STOP=1 -c "
INSERT INTO alerts(hostname,severity,source,message)
VALUES ('reset-check','info','reset','fresh database created');
SELECT COUNT(*) AS alerts_cnt FROM alerts;
"

```
10) Start writers back up
```shell
sudo systemctl start smart-monitor smart-monitor-gui

```
11) Verify ownership (optional)
```shell
sudo -u postgres psql -d smartdb -c "SELECT d.datname, r.rolname AS owner FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname='smartdb';"
sudo -u postgres psql -d smartdb -c "SELECT tablename, tableowner FROM pg_tables WHERE schemaname='public' ORDER BY tablename;"
sudo -u postgres psql -d smartdb -c "SELECT c.relname AS sequence, r.rolname AS owner FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_roles r ON r.oid=c.relowner WHERE n.nspname='public' AND c.relkind='S' ORDER BY c.relname;"

```