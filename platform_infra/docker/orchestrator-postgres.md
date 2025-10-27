## Smart-Monitor Orchestrator — Cross-OS + Postgres

---

### What we are running 

- DB: postgres:15 (Docker on Linux VM/host)

- Linux Orchestrator image: ghcr.io/anselem-okeke/smartmon-orchestrator:1.0.0-linux

- Windows Orchestrator image: ghcr.io/anselem-okeke/smartmon-orchestrator:1.0.0-win

- Docker network (Linux): smartnet

- Linux host IP: 192.168.56.11 (VirtualBox/host-only)
- Both Windows and Linux VM should be host-only adapter

- Published DB port for Windows clients: 5435 (host → container 5432)

### Rule of thumb

- Linux↔Linux on same Docker network → use db:5432 in DATABASE_URL (no host port).

- Windows container → Linux DB → use Linux host IP + published port (e.g., 192.168.56.11:5435).

---

### 1) Prepare Linux network
```shell
docker network create smartnet || true
```
### 2) Run PostgreSQL on Linux
> - Option A — Supports both Linux & Windows clients (publish a host port)
> ```shell
> docker rm -f db 2>/dev/null
> docker run -d --name db --network smartnet -p 5435:5432 \
>  -e POSTGRES_USER=smart \
>  -e POSTGRES_PASSWORD=smartpass \
>  -e POSTGRES_DB=smartdb \
>  -v pgdata:/var/lib/postgresql/data \
>  postgres:15 \
>  -c 'listen_addresses=*' \
>  -c 'password_encryption=scram-sha-256'
>```
> -  Allow remote clients for initial testing (tighten later)
> ```shell
> docker exec -u postgres db bash -lc \
>  "echo \"host all all 0.0.0.0/0 scram-sha-256\" >> /var/lib/postgresql/data/pg_hba.conf && \
>   psql -U postgres -c 'SELECT pg_reload_conf();'"
>```
> - Enable UFW (Linux firewall)
> ```shell
> sudo ufw allow 5435/tcp
>```
> - Add port to IPtables
> ```shell
> sudo iptables -I INPUT  -i enp0s8 -p tcp --dport 5435 -j ACCEPT
> sudo iptables -I OUTPUT -o enp0s8 -p tcp --sport 5435 -j ACCEPT
>```
> - Health Check
> ```shell
> docker ps
> docker logs db --since=1m
> docker exec db pg_isready -U smart -d smartdb
> sudo ss -ltnp | grep 5435
>```
> - Option B — Linux only (no host port) 
> ```shell
> docker rm -f db 2>/dev/null
> docker run -d --name db --network smartnet \
>  -e POSTGRES_USER=smart \
>  -e POSTGRES_PASSWORD=smartpass \
>  -e POSTGRES_DB=smartdb \
>  -v pgdata:/var/lib/postgresql/data \
>  postgres:15
>```

### 3) Run Linux Orchestrator (same network as DB)
> - Only one orchestrator should initialize the schema.
> ```shell
> docker rm -f orchestrator 2>/dev/null
> docker run -d --name orchestrator --network smartnet \
>  -e SMARTMON_API_KEY=dev-secret \
>  -e SMARTMON_INIT_PG=1 \   # ← this instance creates/migrates schema
>  -e DATABASE_URL='postgresql://smart:smartpass@db:5432/smartdb' \
>  -e SMARTCTL=/usr/sbin/smartctl \
>  ghcr.io/anselem-okeke/smartmon-orchestrator:1.0.0-linux
>```
> - With privilege
> ```shell
> docker run -d \
>  --name orchestrator --user 0:0 \
>  --network smartnet \
>  --cap-add SYS_ADMIN \
>  --cap-add SYS_RAWIO \
>  --privileged \
>  -e DATABASE_URL="postgresql://smart:smartpass@db:5432/smartdb" \
>  -e SMARTMON_API_KEY=dev-secret \
>  -e SMARTMON_INIT_PG=1 \
>  -e SMARTCTL=/usr/sbin/smartctl \
>  ghcr.io/anselem-okeke/smartmon-orchestrator:1.0.0-linux
>```
> -  Quick checks
> ```shell
> docker logs -f orchestrator
> docker exec -it orchestrator sh -lc 'getent hosts db && nc -zv db 5432 || true'
>```

### 4) Run Windows Orchestrator (connect via Linux host IP)
> - Windows containers can’t join Linux Docker networks. Use the Linux host IP + published port
> ```shell
> docker rm -f orchestrator 2>$null; docker run -d --name orchestrator -e SMARTMON_API_KEY=dev-secret -e "SMARTCTL=C:\Program Files\smartmontools\bin\smartctl.exe" -e SMARTMON_INIT_PG=0 -e "DATABASE_URL=postgresql://smart:smartpass@192.168.56.11:5435/smartdb" ghcr.io/anselem-okeke/smartmon-orchestrator:1.0.0-win
>```
> - Connectivity sanity from Windows
> ```shell
> Test-NetConnection 192.168.56.11 -Port 5435
>```

### 5) DB visibility & quick queries
> - Open psql inside the DB container
> ```shell
> docker exec -it db psql -U smart -d smartdb
>```
> - Helpful psql commands
> ```shell
> \dt
> \d service_status
> SELECT * FROM service_status ORDER BY timestamp DESC LIMIT 20;
> SELECT os_platform, hostname, COUNT(*) FROM service_status GROUP BY os_platform, hostname ORDER BY 3 DESC;
>```

### 6) Proving Windows writes to Postgres
> - From inside the Windows container (PowerShell)
> ```shell
> docker exec -it orchestrator "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile
> $py = @'
> import os, psycopg
> c = psycopg.connect(os.getenv("DATABASE_URL"))
> cur = c.cursor()
> cur.execute("select current_user, current_database()")
> print(cur.fetchone()); c.close(); print("OK")
> '@
> $py | & 'C:\Python311\python.exe' -
>```
> -  Expect: ('smart', 'smartdb') and OK
> - OR use the below command
> ```shell
> docker exec -it db psql -U smart -d smartdb -c \
> "SELECT * FROM service_status WHERE os_platform='Windows' ORDER BY timestamp DESC LIMIT 20;"
>```