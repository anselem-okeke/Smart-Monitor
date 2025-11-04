### Smart-Monitor VirtualBox Network & PostgreSQL Connectivity Setup

This guide documents how to configure **Windows Server (Smart-Monitor Orchestrator)** and **Ubuntu Backend (PostgreSQL)** 
virtual machines to communicate reliably over a **VirtualBox Host-Only Network**.

It covers NIC setup, static IP assignment, route configuration, and firewall adjustments to achieve a successful 
TCP connection (`TcpTestSucceeded : True`) from Windows → Linux on port `5432`.

---

### System Overview

| Component | Role | OS | IP Address | Network Adapter |
|------------|------|----|-------------|-----------------|
| **winserver2025** | Smart-Monitor Orchestrator | Windows Server 2025 | `192.168.56.50` | Host-Only (Ethernet 2) |
| **BackendServer** | PostgreSQL Database | Ubuntu 20.04 | `192.168.56.11` | Host-Only (enp0s8) |

Both VMs use:
- **Adapter 1** → NAT (for Internet access)  
- **Adapter 2** → Host-Only Adapter (`vboxnet0` → 192.168.56.0/24 subnet)

---

setting window persistence env
```shell
[Environment]::SetEnvironmentVariable(
  "SMARTMON_APPROVED_JSON",
  "C:\ProgramData\SmartMonitor\approved_services.json",
  "Machine"
)
  
Get-ChildItem Env:
```

#### 1. VirtualBox Network Configuration

   - Windows VM (`winserver2025`)
   - Settings → Network
   - Adapter 1: Attached to NAT
   - Adapter 2: Attached to Host-Only Adapter
   - Name: VirtualBox Host-Only Ethernet Adapter (same as backend VM)
   - Both machines **must use the same Host-Only network name** (e.g., `vboxnet0`).
   - If mismatched (`#2`, `#3`, `#4`), they will be isolated even if IPs look similar.

#### 2. Verify Linux Network (PostgreSQL Host)

```shell
ip -4 addr show | grep 192.168
# → inet 192.168.56.11/24 scope global enp0s8
```
- Ensure the interface enp0s8 has an IP in 192.168.56.0/24

#### 3. Configure Windows Static IP & Routing

> - See which adapter has (or will have) the 192.168.56.0/24 route
> ```shell
> Get-NetRoute -DestinationPrefix '192.168.56.0/24' -AddressFamily IPv4 |
>  Format-Table InterfaceAlias,IfIndex,NextHop,RouteMetric
>```
> - Ask Windows which adapter it would use to reach a target on that subnet `(Example: VM at 192.168.56.11)`
> ```shell
> Test-NetConnection 192.168.56.11 -InformationLevel Detailed |
>  Select-Object InterfaceAlias, SourceAddress, RemoteAddress
>```
> - List adapters with clear descriptions (helps spot VirtualBox/Hyper-V)
> ```shell
> Get-NetAdapter | Format-Table Name, IfIndex, Status, InterfaceDescription
> # Often shows things like "VirtualBox Host-Only Ethernet Adapter"
>```
> - See IPv4s bound per adapter
> ```shell
> Get-NetIPAddress -AddressFamily IPv4 |
>  Format-Table IPAddress, PrefixLength, InterfaceAlias, InterfaceIndex, PrefixOrigin, AddressState
>```
> - `Nice to have` Make it unambiguous going forward 
> - Once you identify the right one, rename it to a stable alias you’ll use in scripts:
> ```shell
> Rename-NetAdapter -Name 'Ethernet 2' -NewName 'HostOnly-56'
> # Then the scripts can safely use:
> $nic = 'HostOnly-56'
>```
> In earlier output, Ethernet 2 had IfIndex 10 and is Connected. If the route/`Test-NetConnection`
> for `192.168.56.0/24` points to that alias, then yes `Ethernet 2` is the right adapter.
> The commands above remove the guesswork.

- Run all commands in elevated PowerShell:
```shell
# Choose the correct adapter name (check with Get-NetAdapter)
$nic = 'Ethernet 2'

# Remove old IPs
Get-NetIPAddress -InterfaceAlias $nic -AddressFamily IPv4 -ErrorAction SilentlyContinue |
  Remove-NetIPAddress -Confirm:$false

# Assign static IP in same subnet
New-NetIPAddress -InterfaceAlias $nic -IPAddress 192.168.56.50 -PrefixLength 24

# Lower metric to prefer this NIC for 192.168.56.x
Set-NetIPInterface -InterfaceAlias $nic -InterfaceMetric 1

# Restart adapter
Restart-NetAdapter -Name $nic -Confirm:$false

```
Confirm:
```shell
Get-NetIPAddress -InterfaceAlias $nic -AddressFamily IPv4
Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric
```
Example:
```yaml
IPAddress  : 192.168.56.50
AddressState : Preferred
InterfaceMetric : 1
```
Windows automatically creates a connected route:
```shell
Get-NetRoute -DestinationPrefix "192.168.56.0/24"
```
Expected:
```yaml
DestinationPrefix : 192.168.56.0/24
NextHop           : 0.0.0.0
InterfaceAlias    : Ethernet 2
```

#### 4. Verify Network Layer
Check connectivity and routing:
```shell
ping 192.168.56.11
Test-NetConnection 192.168.56.11 -Port 5432 -InformationLevel Detailed
```
Expected correct source:
```yaml
InterfaceAlias : Ethernet 2
SourceAddress  : 192.168.56.50
```
If InterfaceAlias shows Ethernet (NAT, 10.0.2.15) → Windows is using wrong NIC.
Adjust with:
```yaml
Set-NetIPInterface -InterfaceAlias "Ethernet" -InterfaceMetric 50
```

#### 5. Configure PostgreSQL on Backend Server
#### 5.1 Allow external connections

Edit `/etc/postgresql/12/main/postgresql.conf`:
```yaml
listen_addresses = '*'
```
#### 5.2 Update authentication rules

Edit `/etc/postgresql/12/main/pg_hba.conf`:
```yaml
# Allow access from host-only network
host    all     all     192.168.56.0/24     md5
```
Restart PostgreSQL:
```shell
sudo systemctl restart postgresql
```
Verify it’s listening:
```shell
sudo ss -ltnp | grep 5432
# → LISTEN 0 244 0.0.0.0:5432
```
Test locally:
```shell
psql -h 192.168.56.11 -U smart -d smartdb
```

#### 6. Firewall Configuration (Linux)
#### 6.1 Check status
```shell
sudo ufw status verbose
sudo systemctl status firewalld
```
#### 6.2 (Temporary test)
```shell
sudo ufw disable
# or
sudo systemctl stop firewalld
```
Retest from Windows:
```shell
Test-NetConnection 192.168.56.11 -Port 5432
```

- If success → re-enable firewall with a permanent rule.

#### 6.3 Permanent allow rules
Using UFW
```shell
sudo ufw allow in on enp0s8 from 192.168.56.0/24 to any port 5432 proto tcp
sudo ufw enable
sudo ufw status numbered
```
Using firewalld
```shell
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.56.0/24" port protocol="tcp" port="5432" accept'
sudo firewall-cmd --reload
```
Re-test connectivity:
```shell
Test-NetConnection 192.168.56.11 -Port 5432
```
Expected output:
```yaml
TcpTestSucceeded : True
```
Temporal firewall rule
```shell
sudo iptables -I INPUT  -i enp0s8 -p tcp --dport 5432 -j ACCEPT
sudo iptables -I OUTPUT -o enp0s8 -p tcp --sport 5432 -j ACCEPT
```

Parmanent firewall rule
- Option 1 — with `ufw`
```shell
sudo ufw allow in on enp0s8 from 192.168.56.0/24 to any port 5432 proto tcp
sudo ufw enable
```
Parmanent firewall rule
- Option 2 — with `firewalld`
```shell
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" \
  source address="192.168.56.0/24" interface name="enp0s8" \
  port protocol="tcp" port="5432" accept'
sudo firewall-cmd --reload
```
Parmanent firewall rule
- Option 3 — with `raw iptables persistence (manual)`
```shell
sudo iptables-save | sudo tee /etc/iptables/rules.v4
sudo iptables-restore < /etc/iptables/rules.v4
```
---
#### TROUBLESHOOTING
##### 1. Network
pg_hba.conf allows 192.168.56.0/24, firewall open, Postgres listening on 0.0.0.0:5432).
The problem now is 100% on the Windows routing side, Windows VM is still trying to reach 192.168.56.11
via the wrong interface (Ethernet, 10.0.2.15) instead of host-only adapter Ethernet 2 (192.168.56.50).

---

Root Cause Summary
```yaml
InterfaceAlias : Ethernet
SourceAddress  : 10.0.2.15
```
means:

- Windows sent the packet through the NAT adapter (`Ethernet`), not `Ethernet 2`.
- That adapter doesn’t have a route to 192.168.56.0/24, so the connection never reaches backend VM.

- The reason is that Windows prefers the default gateway route on Ethernet (NAT) for everything, because it’s the only interface with a gateway (0.0.0.0/0).
- Even though a connected route for 192.168.56.0/24 exists, the NAT interface’s metric or binding order is still winning.

Step-by-Step Fix, Confirm both NICs are up
```shell
Get-NetAdapter | Format-Table Name,IfIndex,Status,InterfaceDescription
```
- Ensure Ethernet and Ethernet 2 are both Up.
Ensure Ethernet 2 really has 192.168.56.50
```shell
Get-NetIPAddress -InterfaceAlias "Ethernet 2" -AddressFamily IPv4
```
You should see:
```yaml
IPAddress : 192.168.56.50
PrefixLength : 24
AddressState : Preferred
```

Lower the metric for Ethernet 2 dramatically, Set the metric very low so Windows prefers it for that subnet:
```shell
Set-NetIPInterface -InterfaceAlias "Ethernet 2" -InterfaceMetric 1
```
Then recheck:
```shell
Get-NetIPInterface -AddressFamily IPv4 | Sort-Object InterfaceMetric | Format-Table ifIndex,InterfaceAlias,InterfaceMetric
```
You should see:
```yaml
Ethernet 2   1
Ethernet     (higher number)
```
Flush and re-add the correct route explicitly, Even though one exists, we’ll force it cleanly:
```shell
Remove-NetRoute -DestinationPrefix "192.168.56.0/24" -Confirm:$false
New-NetRoute -DestinationPrefix "192.168.56.0/24" -InterfaceAlias "Ethernet 2" -NextHop 0.0.0.0
```
Then verify:
```shell
Get-NetRoute -DestinationPrefix "192.168.56.0/24"
```
Test again and confirm correct source IP
```shell
Test-NetConnection 192.168.56.11 -Port 5432 -InformationLevel Detailed
```
This time, it must show:
```yaml
InterfaceAlias : Ethernet 2
SourceAddress  : 192.168.56.50
TcpTestSucceeded : True
```

If it still uses Ethernet (10.0.2.15), Force binding order manually:
```shell
Set-NetIPInterface -InterfaceAlias "Ethernet" -InterfaceMetric 50
# This makes the NAT adapter less preferred for any route that can be served by another interface.
```
Re-run:
```shell
Test-NetConnection 192.168.56.11 -Port 5432
```
Optional: Verify routing table visually
- Run:
```shell
route print
```
should now see a section like:
```yaml
Network Destination  Netmask       Gateway     Interface      Metric
192.168.56.0         255.255.255.0  On-link    192.168.56.50       1
192.168.56.50        255.255.255.255 On-link   192.168.56.50       1
192.168.56.255       255.255.255.255 On-link   192.168.56.50       1
```
---
##### 2. Firewall
network path is now correct — Windows is using Ethernet 2 (192.168.56.50) to reach 192.168.56.11, and ping works.
So the last blocker is almost certainly firewalling on the Linux VM (or a rule ordering issue). 
Below is a fast, no-guesswork checklist. Run the Linux commands on BackendServer and the Windows ones on VM.

---
1) Prove whether packets reach Postgres (Linux), In one terminal on the Linux VM:
```shell
sudo tcpdump -i enp0s8 -nn tcp port 5432
```
Then from Windows run:
```shell
Test-NetConnection 192.168.56.11 -Port 5432
```
- If you see SYNs in tcpdump but no SYN/ACK going back → firewall on Linux is dropping replies.

- If you see nothing → something still blocks before Postgres (very likely firewall rules bound to interface/zones).

2) Temporarily disable Linux firewalls and retest (Just to confirm the hypothesis; re-enable later.)
```shell
# If UFW is present
sudo ufw status verbose
sudo ufw disable

# If firewalld is present
sudo systemctl status firewalld
sudo systemctl stop firewalld
```
Retest from Windows:
```shell
Test-NetConnection 192.168.56.11 -Port 5432
```

- Succeeds now ➜ firewall config was the issue. Continue to step 3 to add the right allow rules and re-enable.

- Still fails ➜ jump to step 4.

3) Add the correct allow rule(s) and re-enable
UFW (Ubuntu)
```shell
# Allow Postgres from the host-only network on the host-only interface
sudo ufw allow in on enp0s8 from 192.168.56.0/24 to any port 5432 proto tcp

sudo ufw enable
sudo ufw status numbered
```
firewalld (if you use it instead of UFW)
```shell
# Put enp0s8 into the trusted (or internal) zone
sudo firewall-cmd --zone=internal --add-interface=enp0s8 --permanent
# Or bind the rule directly to the interface
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" \
  source address="192.168.56.0/24" \
  interface name="enp0s8" \
  port protocol="tcp" port="5432" accept'
sudo firewall-cmd --reload
sudo firewall-cmd --list-all
```
Retest from Windows:
```shell
Test-NetConnection 192.168.56.11 -Port 5432
```
4) (If it still fails) Quick rule inspection on Linux
```shell
# UFW summary
sudo ufw status verbose

# firewalld zones / interface mapping
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --get-default-zone
sudo firewall-cmd --zone=$(sudo firewall-cmd --get-default-zone) --list-all

# nftables / iptables (depending on your distro)
sudo nft list ruleset | sed -n '1,200p'
sudo iptables -S
sudo iptables -L -n -v
```

Look for DROP/REJECT in INPUT or a default policy of DROP that isn’t overridden for enp0s8/port 5432.

As a quick force-allow (for testing) with legacy iptables:
```shell
sudo iptables -I INPUT 1 -i enp0s8 -p tcp --dport 5432 -s 192.168.56.0/24 -j ACCEPT
```
(If nftables is active, prefer the firewalld/ufw methods above.)

5) Sanity checks you already pass

- Postgres listens on 0.0.0.0:5432 

- pg_hba.conf contains lines for 192.168.56.0/24 (ensure not commented and above any generic reject)

- Windows now shows:
```yaml
InterfaceAlias : Ethernet 2
SourceAddress  : 192.168.56.50
```
6) Optional Windows outbound firewall check (rare)
```shell
Get-NetFirewallProfile | ft Name,Enabled
Get-NetFirewallRule -Direction Outbound -Action Block -Enabled True | measure
```
Outbound is typically allowed by default; this is just to be thorough.

Expected end state

Once the firewall rule is correct, you’ll see:
````shell
Test-NetConnection 192.168.56.11 -Port 5432

TcpTestSucceeded : True
````
