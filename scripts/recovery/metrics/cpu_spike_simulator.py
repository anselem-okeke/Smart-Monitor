import multiprocessing
import platform
import shutil
import subprocess
import time

import psutil
import setproctitle

CPU_LOAD_TIME = 120
NUM_CORES = multiprocessing.cpu_count()

def cpu_hog(name="my_leaky_simulation"):
    setproctitle.setproctitle(name)
    x = 0
    while True:
        x = x ** 2 + x + 2  # Keep CPU busy

def run_cpu_stress(proc_name="my_leaky_simulation"):
    print(f"[INFO] Lauching {NUM_CORES} CPU hog processes for {CPU_LOAD_TIME} seconds...")
    procs = []
    for _ in range(NUM_CORES):
        p = multiprocessing.Process(target=cpu_hog, args=(proc_name,))
        p.start()
        procs.append(p)

    # Monitor live CPU and top process during load
    start = time.time()
    while time.time() - start < CPU_LOAD_TIME:
        cpu = psutil.cpu_percent(interval=1)
        print(f"[LIVE CPU] {cpu}%")
        top = sorted(
            [p.info for p in psutil.process_iter(['pid', 'name', 'cpu_percent'])],
            key=lambda x: x['cpu_percent'],
            reverse=True
        )[:5]
        print("[TOP PROCESSES]")
        for p in top:
            print(p)
        time.sleep(2)

    print(f"[INFO] Terminating stress processes for {NUM_CORES}...")
    for p in procs:
        p.terminate()
        p.join()
    print("[INFO] CPU stress simulation complete...")


def stress_linux():
    if shutil.which("stress") is None:
        print("[INFO] Installing stress tool...")
        subprocess.call(["sudo", "apt", "install", "-y", "stress"])
    subprocess.call(["stress", "--cpu", str(NUM_CORES), "--timeout", str(CPU_LOAD_TIME)])

if __name__ == '__main__':
    os_type = platform.system()

    if os_type == "Windows":
        run_cpu_stress()
    elif os_type == "Linux":
        # Check if stress is installed or fallback to Python stressor
        try:
            if shutil.which("stress"):
                stress_linux()
            else:
                run_cpu_stress()
        except ImportError:
            run_cpu_stress()
    else:
        print(f"Unsupported OS: {os_type}")