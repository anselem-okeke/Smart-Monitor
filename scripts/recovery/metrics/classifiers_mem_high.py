def is_memory_high(rows, warn_th, swap_th, consecutive):
    """
    rows = list[(timestamp, mem%, swap%)] newest first
    Trigger if at least `consecutive` samples have:
      • memory_usage >= warn_th  AND
      • swap_usage    >=  swap_th
    """
    if len(rows) < consecutive:
        return False

    count = 0

    for _, mem, swap in rows[:consecutive]:
        if mem is None or swap is None:
            continue
        if mem >= warn_th and swap >= swap_th:
            count += 1

    return count >= consecutive


    # chk = [(m, s) for _, m, s in rows[:consecutive] if m is not None]
    # return len(chk) == consecutive and all(m >= warn_th and s > swap_th for m, s in chk)
