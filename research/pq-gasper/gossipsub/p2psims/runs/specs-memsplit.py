#!/usr/bin/env python3
"""PQ Gasper subnet specs study (Nov 23): every 120 s, for each running Shadow run (its process group), the PSS of the
shadow process and of its wbsim node processes (sum, count, mean and max per process), from /proc/<pid>/smaps_rollup,
appended to runs/specs-memsplit.txt: what the node processes need, separately from Shadow's own memory.
Start: nohup setsid taskset -c 48-95 nice -n 19 python3 runs/specs-memsplit.py > /dev/null 2>&1 < /dev/null &"""
import os
import time

OUT = "/home/yann/p2p-ministry-gossip2000/runs/specs-memsplit.txt"
uid = os.getuid()


def pss_kib(p):
    for line in open(f"/proc/{p}/smaps_rollup"):
        if line.startswith("Pss:"):
            return int(line.split()[1])
    return 0


while True:
    sh, wb = {}, {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            if os.stat(f"/proc/{p}").st_uid != uid:
                continue
            comm = open(f"/proc/{p}/comm").read().strip()
            if comm not in ("shadow", "wbsim"):
                continue
            pg, k = os.getpgid(int(p)), pss_kib(p)
            if comm == "shadow":
                sh[pg] = (os.path.basename(os.readlink(f"/proc/{p}/cwd")), k)
            else:
                wb.setdefault(pg, []).append(k)
        except OSError:  # exited meanwhile
            continue
    with open(OUT, "a") as f:
        for pg, (name, k) in sh.items():
            w = wb.get(pg, [])
            if w:
                f.write(f"{time.strftime('%H:%M:%S')} {name} shadow={k / 2 ** 20:.1f}GiB wbsim={sum(w) / 2 ** 20:.1f}GiB "
                        f"n={len(w)} mean={sum(w) / len(w) / 1024:.1f}MiB max={max(w) / 1024:.1f}MiB\n")
    time.sleep(120)
