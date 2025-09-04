import time

import psutil


# def top_cpu_processes(limit=10):
#     procs = []
#     for p in psutil.process_iter(['pid','name','cpu_percent']):
#         try:
#             procs.append(p.info)
#         except psutil.Error:
#             pass
#     procs.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
#     return procs[:limit]
# # print(top_cpu_processes())
#
# for p in top_cpu_processes():
#     name = (p["name"] or "").lower()
#     try:
#         proc = psutil.Process(pid=p['pid'])
#         user = proc.username().lower()
#         uptime = time.time() - proc.create_time()
#         print(uptime)
#     except psutil.Error:
#         pass
# uptime = int(time.time() - psutil.boot_time())
#
# swap = psutil.swap_memory().percent
# print(swap)


def whitelisted_rss():
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'memory_info']):
        try:
            procs.append(p.info)
        except psutil.Error:
            pass
    procs.sort(key=lambda x: x['memory_info'].rss if x['memory_info'] else 0, reverse=True)

    return procs

# procs_name = []
# for p in whitelisted_rss():
#     print(f"{p['name']}={p['memory_info']}")
#     procs_name.append(p['memory_info'])
# print(procs_name)

def top_mem_processes(limit=10, verbose=False, min_rss_mb=0):
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'username', 'memory_info', 'cmdline', 'create_time']):
        try:
            info = p.info
            rss = info['memory_info'].rss if info['memory_info'] else 0
            if rss <= 0:
                continue

            rec = {
                'pid': info['pid'],
                'name': info['name'],
                'rss_mb': rss / (1024 * 1024),
                'username': (info.get('username') or '').lower(),
                'create_time': info.get('create_time')
            }
            if verbose:
                cmd = info.get('cmdline')
                rec['cmdline'] = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)

            if rec['rss_mb'] >= min_rss_mb:
                procs.append(rec)
        except psutil.Error:
            continue

    procs.sort(key=lambda x: x['rss_mb'], reverse=True)
    return procs[:limit]
print(top_mem_processes())







