### Runbook: Fix Orchestrator Kind Kubernetes API Connectivity (Docker Compose) 

**Purpose**

When Smart-Monitor Orchestrator runs in Docker Compose and must monitor a Kubernetes cluster, it may report K8s API
down even though the cluster is up. This runbook fixes the connection by ensuring:

 - The container loads the correct kubeconfig

 - The kubeconfig server: uses a TLS-valid SAN address

 - The container can route to that address

---

**Symptoms**

- Dashboard alert: K8s API appears unreachable ... version=unknown

- Python client error includes:

  - Invalid kube-config file. No configuration found. 
  - Service host/port is not set. 
  - SSLCertVerificationError ... Hostname mismatch ... host.docker.internal 
  - or timeouts

### Step 1 — Confirm Kind API is exposed on the host
```shell
docker inspect smart-monitor-control-plane --format '{{json .NetworkSettings.Ports}}'
```
You should see something like:

- 6443/tcp -> HostPort 6443 (stable)
- or a random hostport (less stable).

### Step 2 — Confirm the API server certificate SANs
```shell
apip=$(docker port smart-monitor-control-plane 6443/tcp | awk -F: '{print $2}')
echo | openssl s_client -connect 127.0.0.1:$apip -servername 127.0.0.1 2>/dev/null \
  | openssl x509 -noout -text | sed -n '/Subject Alternative Name/,+2p'
```

Look for an IP like:

- IP Address:172.18.0.4 or similar range 172. ... 
- and/or DNS:localhost, DNS:kubernetes.default.svc... 
- If the plan is to use `host.docker.internal`, confirm it exists in SANs (usually it does not).
- One way to include it `recommended` is to create the cluster adding `host.docker.internal` in `cerSAN`
```yaml
# Updated kind-config.yaml with explicit node definitions
#kind delete cluster --name smart-monitor
#kind create cluster --name smart-monitor --config kind-config.yaml

kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  apiServerAddress: "0.0.0.0"
  apiServerPort: 6443
kubeadmConfigPatches:
- |
  kind: ClusterConfiguration
  apiServer:
    certSANs:
      - "host.docker.internal"
      - "172.17.0.1"
      - "127.0.0.1"
# --- section to define nodes ---
nodes:
- role: control-plane
  extraPortMappings:
    - containerPort: 30001
      hostPort: 30001
- role: worker
- role: worker
```
### Step 3 — Choose connection strategy
Use the control-plane container IP from SAN. Get the control-plane IP
```shell
docker inspect smart-monitor-control-plane --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```
Example output `172.18.0.4`

### Step 4 — Update kubeconfig server to SAN-valid IP
keep a dedicated “container kubeconfig” copy. Create a separate file so host kubectl still works unchanged:
```shell
cp /home/vagrant/.kube/config /home/vagrant/.kube/config.docker
sed -i 's#https://127.0.0.1:36873#https://host.docker.internal:6443#g' /home/vagrant/.kube/config.docker
```
Depending on the path of config on host, Then mount that file into the container:
```yaml
volumes:
  - /home/vagrant/.kube/config.docker:/app/config/kube/config:ro
environment:
  KUBECONFIG: /app/config/kube/config
```
or

Assuming orchestrator uses a dedicated kubeconfig file on host: `/home/vagrant/.kube/config.docker` run:
```shell
KUBECONFIG=/home/vagrant/.kube/config.docker \
kubectl config set-cluster kind-smart-monitor --server=https://172.18.0.4:6443
```
verify change

```shell
grep -n "server:" /home/vagrant/.kube/config.docker | head -n 30
```
### Step 5 — Mount kubeconfig into the orchestrator container

In docker-compose.yml ensure the file is mounted:
````shell
volumes:
  - /home/vagrant/.kube/config.docker:/app/config/kube/config:ro
````

### Step 6 — Force container to use the mounted kubeconfig (critical)

In docker-compose.yml do not rely on interpolation if it’s being overridden. Hard-set:
```yaml
environment:
  KUBECONFIG: /app/config/kube/config
```
Recreate container
```shell
docker compose up -d --force-recreate orchestrator_lab
```
Confirm inside container:
```yaml
docker exec -it sm-orchestrator-lab sh -lc '
echo "KUBECONFIG=$KUBECONFIG";
ls -l /app/config/kube/config;
grep -n "server:" /app/config/kube/config | head -n 20
'
```
Expected: `KUBECONFIG=/app/config/kube/config` or `server: https://172.18.0.4:6443`

### Step 7 — Ensure routing works (network)

The orchestrator container must be able to route to 172.18.0.4.

Find the kind docker network name:

```shell
docker inspect smart-monitor-control-plane \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'
```
Connect Orchestrator contianer to that network, use the actual network name as printed
```shell
docker network connect kind sm-orchestrator-lab
```
### Step 8 — Validate with Python client (real success test)
```shell
docker exec -it sm-orchestrator-lab sh -lc '
python3 - <<PY
from kubernetes import config, client
config.load_kube_config(config_file="/app/config/kube/config", context="kind-smart-monitor")
print("OK version:", client.VersionApi().get_code().git_version)
PY
'
```
if it prints a version `v1.34.0` API connectivity + TLS are correct

### Step 9 — Validate from Smart-Monitor UI/API

Check cluster health endpoint:
```shell
curl 'http://127.0.0.1:5003/api/k8s/clusters?since_minutes=240'
```
You want:

- api_reachable: true

- k8s_version: vX.Y.Z

**Troubleshooting quick map**

1) Service host/port is not set

   - Expected if not inside K8s. Ensure fallback to kubeconfig works.

2) Invalid kube-config file. No configuration found

   - KUBECONFIG points to wrong path or empty file.

   - Fix: set KUBECONFIG=/app/config/kube/config and recreate container.

3) Hostname mismatch … host.docker.internal

   - TLS SAN mismatch.

   - Fix: use SAN-valid IP (Option B) like 172.18.0.4.

4) Timeout / connection refused to 172.18.0.4:6443

   - Container not on the kind network.

   - Fix: docker network connect kind sm-orchestrator-lab

### Notes (Production)

The orchestrator runs inside the cluster, it talks to the API server using in-cluster auth, not local kubeconfig/context.
How it talks to the API server (in-cluster)

Inside a Pod, Kubernetes automatically provides:

- API endpoint via env vars: `KUBERNETES_SERVICE_HOST` + `KUBERNETES_SERVICE_PORT`
- ServiceAccount token mounted at: `/var/run/secrets/kubernetes.io/serviceaccount/token`
- Cluster CA cert at: `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt`
- Namespace at: `/var/run/secrets/kubernetes.io/serviceaccount/namespace`
- The Python client’s `config.load_incluster_config()` reads those and makes HTTPS calls to: `https://kubernetes.default.svc` 
(the API service in-cluster)

---

### REVISED
1) Find what host port kind exposes for the API (6443/tcp)
```shell
docker port smart-monitor-control-plane 6443/tcp
```
**expected**

0.0.0.0:6443 ✅ (stable, ideal), OR

127.0.0.1:38071 (random host port)

Capture the port:
```shell
apip=$(docker port smart-monitor-control-plane 6443/tcp | awk -F: '{print $2}')
echo "$apip"
```
2) Check certificate SANs for what you want to connect to
```shell
echo | openssl s_client -connect 127.0.0.1:$apip -servername 127.0.0.1 2>/dev/null \
  | openssl x509 -noout -text | sed -n '/Subject Alternative Name/,+2p'
```
looking for:

DNS:host.docker.internal, or

at least IP Address:127.0.0.1 / IP Address:172.17.0.1 etc.

If host.docker.internal is not in SANs, then connecting to it will often fail TLS verification.

3) Update the container kubeconfig to use host endpoint

Important: keep the same port $apip (don’t force 6443 unless that’s actually the host port).
```shell
cp /home/vagrant/.kube/config /home/vagrant/.kube/config.docker

# safer than sed: update by cluster name
KUBECONFIG=/home/vagrant/.kube/config.docker \
kubectl config set-cluster kind-smart-monitor --server="https://host.docker.internal:$apip"
```
verify:
```shell
grep -n "server:" /home/vagrant/.kube/config.docker | head -n 30
```
4) Ensure compose mounts this kubeconfig and uses it

You already have:

extra_hosts: host.docker.internal:host-gateway

volume mount to /app/config/kube/config

KUBECONFIG=/app/config/kube/config

Recreate:
```shell
docker compose up -d --force-recreate orchestrator_lab
```
5) Hard verification in container (real test)
```shell
docker exec -it sm-orchestrator-lab sh -lc '
python3 - <<PY
from kubernetes import config, client
config.load_kube_config(config_file="/app/config/kube/config", context="kind-smart-monitor")
print("OK version:", client.VersionApi().get_code().git_version)
PY
'
```

**works even without SAN changes): Use control-plane container IP + attach networks**

Get control-plane container IP
```shell
docker inspect smart-monitor-control-plane --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
```
Example: 172.18.0.2

Put that IP into the docker kubeconfig
```shell
cp /home/vagrant/.kube/config /home/vagrant/.kube/config.docker
KUBECONFIG=/home/vagrant/.kube/config.docker \
kubectl config set-cluster kind-smart-monitor --server="https://172.18.0.2:6443"
```
verify:
```shell
grep -n "server:" /home/vagrant/.kube/config.docker | head -n 30
```

Ensure orchestrator can route to that IP (critical)

Find the kind network name:
```shell
docker inspect smart-monitor-control-plane \
  --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}'
```

Attach orchestrator to that network (use the printed network name, commonly kind):
```shell
docker network connect kind sm-orchestrator-lab
```
Validate from inside container
```shell
docker exec -it sm-orchestrator-lab sh -lc '
curl -sk https://172.18.0.4:6443/healthz && echo
'
```

## Make Kind API port stable on the host (no random port)

```yaml
# Updated kind-config.yaml with explicit node definitions
#kind delete cluster --name smart-monitor
#kind create cluster --name smart-monitor --config kind-config.yaml

kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  apiServerAddress: "0.0.0.0"
  apiServerPort: 6443
kubeadmConfigPatches:
- |
  kind: ClusterConfiguration
  apiServer:
    certSANs:
      - "host.docker.internal"
      - "172.17.0.1"
      - "127.0.0.1"
# --- section to define nodes ---
nodes:
- role: control-plane
  extraPortMappings:
    - containerPort: 30001
      hostPort: 30001
- role: worker
- role: worker
```

Then recreate:
```shell
kind delete cluster --name smart-monitor
kind create cluster --name smart-monitor --config kind-config.yaml
```

Why this matters

- apiServerPort: 6443 removes the “random hostport” problem.

- certSANs makes the API certificate valid when clients connect using those names/IPs.

**Ensure containers can resolve host.docker.internal (Linux needs this)**

In docker-compose.yml for the orchestrator service add:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Why this matters

- On Linux, host.docker.internal is not guaranteed unless you map it.

- host-gateway resolves to the host’s gateway IP from the container’s POV (commonly `172.17.0.1`).

**Use a dedicated kubeconfig for containers (server points to host.docker.internal)**

Create a container kubeconfig:
```shell
cp ~/.kube/config ~/.kube/config.docker
kubectl --kubeconfig ~/.kube/config.docker config set-cluster kind-smart-monitor \
  --server=https://host.docker.internal:6443
```
Host config:
```shell
kubectl --kubeconfig ~/.kube/config.docker config set-cluster kind-smart-monitor \
  --server=https://127.0.0.1:6443
```
Mount it into orchestrator and hard-set KUBECONFIG:
```yaml
volumes:
  - ~/.kube/config.docker:/app/config/kube/config:ro
environment:
  KUBECONFIG: /app/config/kube/config
```
Why hard-set matters
- It prevents the “wrong path → kubeconfig missing → in-cluster fallback → Service host/port is not set” chain.

**Validate from inside orchestrator (real test)**
````shell
docker exec -it sm-orchestrator-lab sh -lc '
python3 - <<PY
from kubernetes import config, client
config.load_kube_config(config_file="/app/config/kube/config", context="kind-smart-monitor")
print("OK version:", client.VersionApi().get_code().git_version)
PY
'
````