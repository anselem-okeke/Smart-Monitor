import platform

import psutil


def current_zombie_stats():
    """
    A zombie process = a process that has completed execution but still has an entry in the process table because
     its parent hasn’t reaped it yet

       Suppose you run a web server (nginx):
       nginx master spawns worker processes.
       A worker crashes or exits.
       If the master doesn’t call wait(), that worker stays as a zombie.

       Zombies = dead processes waiting for their parent to acknowledge their exit.
       Parents = the processes that created them but failed to reap them.
       Often caused by bugs, mismanagement of child processes, or occasionally expected short-lived behavior.

        The function Scan live processes and return:
        total_procs, zombie_count, zombie_ratio, zombies_by_parent_ppid, parent_name_map

        total = 200
        zombies = 5
        ratio = 0.025
        zombies_by_parent_ppid = {123: 3, 456: 2}
        parent_name_map = {
        1: "systemd",
        123: "nginx",
        456: "python3",
        789: "sshd",
     }

       Parent process nginx (PID 123) has 3 zombie children
       Parent process python3 (PID 456) has 2 zombie children

        total_procs → Total number of processes scanned.
        zombie_count → How many are zombies.
        zombie_ratio → Fraction of processes that are zombies (zombies / total).
        zombies_by_parent_ppid → Dictionary mapping parent PID → number of zombie children.
        parent_name_map → Mapping of PID → process name (to help identify parent processes later).
    :return:
    """
    if platform.system() == "Windows":
        return 0, 0, 0.0, {}, {}

    total = zombies = 0
    by_ppid = {}
    pname = {}

    for p in psutil.process_iter(['pid', 'ppid', 'name', 'status']):
        total +=1
        info = p.info
        pname[info['pid']] = (info.get('name') or "").lower()
        if info.get('status') == psutil.STATUS_ZOMBIE:
            zombies += 1
            pp = info.get('ppid')
            by_ppid[pp] = by_ppid.get(pp, 0) + 1
    ratio = (zombies / total) if total else 0.0
    return total, zombies, ratio, by_ppid, pname

def is_zombie_flood(total, zombies, ratio, cfg):
    """
    "min_total_procs": 100,           // ignore tiny systems / transient spikes
    "ratio_warn": 0.05,               // 5% of processes are zombies → warn
    "ratio_crit": 0.10,               // 10% → critical
    "abs_crit": 50,                   // or >= 50 zombies → critical
    "consecutive": 2,                 // need N consecutive detections

    Returns ('none'|'warning'|'critical')
    """
    if platform.system() == "Windows":
        return 'none'
    if total < cfg["min_total_procs"]:
        return 'none'
    if zombies >= cfg["abs_crit"] or ratio >= cfg["ratio_crit"]:
        return 'critical'
    if ratio >= cfg["ratio_warn"]:
        return 'warning'
    return 'none'