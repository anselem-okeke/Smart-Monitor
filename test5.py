import time

import psutil


def top_cpu_processes(limit=10):
    procs = []
    for p in psutil.process_iter(['pid','name','cpu_percent']):
        try:
            procs.append(p.info)
        except psutil.Error:
            pass
    procs.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
    return procs[:limit]
# print(top_cpu_processes())

for p in top_cpu_processes():
    name = (p["name"] or "").lower()
    try:
        proc = psutil.Process(pid=p['pid'])
        user = proc.username().lower()
        uptime = time.time() - proc.create_time()
        print(uptime)
    except psutil.Error:
        pass
uptime = int(time.time() - psutil.boot_time())
print(uptime)

