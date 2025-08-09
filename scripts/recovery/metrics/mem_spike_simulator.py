#!/usr/bin/env python3
import argparse, math, multiprocessing as mp, os, time
import psutil

PAGE = 4096

def how_to_run_it():
    """
      Windows: python .\mem_spike_simulator.py --label my_memory_simulation --tag my_memory_simulation --workers 4 --total-mb 2048 --hold-seconds 120
      Linux: python3 ./mem_spike_simulator.py --label my_memory_simulation --tag my_memory_simulation --workers 4 --total-mb 2048 --hold-seconds 120
    :return:
    """
    pass

def set_title(label: str):
    try:
        import setproctitle
        setproctitle.setproctitle(label)
    except Exception:
        pass  # fine on Windows

def _mb(n): return int(n * 1024 * 1024)

def touch(block: bytearray):
    # Touch one byte per page to force commit (esp. Windows)
    for i in range(0, len(block), PAGE):
        block[i] = 1

def hog_worker(label: str, target_mb: int, chunk_mb: int, ramp_ms: int, hold_seconds: int, tag: str):
    """
    Ramp to ~target_mb in chunk_mb steps (with ramp_ms delay between chunks),
    then HOLD memory for hold_seconds, then EXIT (memory self-releases).
    """
    set_title(label)
    allocated = 0
    blocks = []
    sleep_per_chunk = (ramp_ms / 1000.0) if ramp_ms > 0 else 0.0

    while allocated < target_mb:
        size = min(chunk_mb, target_mb - allocated)
        try:
            b = bytearray(_mb(size))
            touch(b)
            blocks.append(b)
            allocated += size
        except MemoryError:
            break
        if sleep_per_chunk:
            time.sleep(sleep_per_chunk)

    print(f"[SIM] {label} PID={os.getpid()} allocated≈{allocated} MB tag={tag}", flush=True)

    end = time.time() + max(0, hold_seconds)
    while time.time() < end:
        time.sleep(0.5)
    # Process exits -> memory freed

def main():
    ap = argparse.ArgumentParser(description="Targeted memory spike that auto-releases after a hold window")
    ap.add_argument("--label", default="my_memory_simulation", help="Process label (Linux title)")
    ap.add_argument("--tag", default="my_memory_simulation", help="Unique token in cmdline (helps on Windows)")
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() // 2))
    ap.add_argument("--total-mb", type=int, default=2048, help="Total MB across all workers")
    ap.add_argument("--chunk-mb", type=int, default=64, help="Per-step allocation size (MB)")
    ap.add_argument("--ramp-ms", type=int, default=100, help="Delay between chunks (ms)")
    ap.add_argument("--hold-seconds", type=int, default=120, help="How long to hold before auto-release")
    ap.add_argument("--print-interval", type=float, default=2.0, help="Seconds between live prints")
    args, unknown = ap.parse_known_args()  # keep tag visible in cmdline

    per_worker = max(1, args.total_mb // args.workers)
    print(f"[SIM] Workers={args.workers}  per-worker≈{per_worker} MB  hold={args.hold_seconds}s", flush=True)

    mp.set_start_method("spawn", force=True)
    procs = []
    for i in range(args.workers):
        lbl = args.label if i == 0 else f"{args.label}-{i}"
        p = mp.Process(target=hog_worker,
                       args=(lbl, per_worker, args.chunk_mb, args.ramp_ms, args.hold_seconds, args.tag))
        p.start()
        procs.append(p)

    # Live telemetry until all workers exit (or you Ctrl+C)
    try:
        while any(p.is_alive() for p in procs):
            vm = psutil.virtual_memory(); sm = psutil.swap_memory()
            print(f"[LIVE] Mem={vm.percent:.1f}%  UsedMB={(vm.used/1024/1024):.0f}  Swap={sm.percent:.1f}%", flush=True)
            time.sleep(args.print_interval)
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            p.join(timeout=5)
        print("[SIM] Memory spike finished (workers exited; memory should be back down).", flush=True)

if __name__ == "__main__":
    main()

