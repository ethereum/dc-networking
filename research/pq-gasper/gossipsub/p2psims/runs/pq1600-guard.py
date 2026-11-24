#!/usr/bin/env python3
"""Half-budget guard for the PQ Gasper one-subnet study (Nov 17). Every 60 s: CPU (cores, from /proc utime+stime
deltas) and RSS of every other human user's processes (uid 1000-65533, not ours). Another user is active after 10
consecutive checks above 4 cores or 16 GB. Then: queue paused (runs/STOP-night, runs/HALF-pq1600), our shadow and wbsim
processes limited to CPUs 72-95 (half of 48-95), and the running run stopped with runs/stop-run.sh NAME otheruser if
our summed PSS is above 117 GiB (half of the 235 GiB cap). After 10 consecutive quiet checks: CPUs 48-95 again, and
the files the guard created are removed, so the queue resumes (a stopped run reruns from scratch).
Start: nohup setsid taskset -c 48-95 nice -n 19 python3 runs/pq1600-guard.py > /dev/null 2>&1 < /dev/null &"""
import os
import subprocess
import time

BASE = "/home/yann/p2p-ministry-gossip2000"
ME = os.getuid()
LOG = f"{BASE}/runs/realistic.log"
HZ = os.sysconf("SC_CLK_TCK")


def log(msg):
    with open(LOG, "a") as f:
        f.write(time.strftime("%H:%M:%S") + " GUARD " + msg + "\n")


def others():
    """{pid: (uid, cpu ticks, rss kB)} of other human users' processes."""
    out = {}
    for p in os.listdir("/proc"):
        if not p.isdigit():
            continue
        try:
            uid = os.stat(f"/proc/{p}").st_uid
            if uid == ME or not 1000 <= uid < 65534:
                continue
            f = open(f"/proc/{p}/stat").read().rsplit(")", 1)[1].split()
            rss = int(f[21]) * os.sysconf("SC_PAGE_SIZE") // 1024
            out[int(p)] = (uid, int(f[11]) + int(f[12]), rss)
        except (OSError, IndexError, ValueError):
            continue
    return out


def ours():
    return [p for p in subprocess.run(["pgrep", "-u", str(ME), "-x", "shadow|wbsim"], capture_output=True,
                                      text=True).stdout.split()]


def affinity(cpus):
    for p in ours():
        subprocess.run(["taskset", "-a", "-p", "-c", cpus, p], capture_output=True)


def pss():
    out = subprocess.run(["python3", f"{BASE}/runs/memsum.py"], capture_output=True, text=True).stdout.splitlines()
    tot = float(out[0].split()[1]) if out else 0.0
    runs = [(float(l.split()[2]), l.split()[0]) for l in out[1:]]
    return tot, runs


busy, quiet, active, created = 0, 0, False, False
prev = others()
while True:
    time.sleep(60)
    cur = others()
    ticks = sum(t - prev[p][1] for p, (u, t, r) in cur.items() if p in prev and t >= prev[p][1])
    cores = ticks / HZ / 60.0
    rss_gb = sum(r for u, t, r in cur.values()) / 1e6
    prev = cur
    hot = cores > 4 or rss_gb > 16
    busy, quiet = (busy + 1, 0) if hot else (0, quiet + 1)
    if not active and busy >= 10:
        active = True
        log(f"another user active for 10 min ({cores:.1f} cores, {rss_gb:.1f} GB): half budget, CPUs 72-95, queue paused")
        created = not os.path.exists(f"{BASE}/runs/STOP-night")
        open(f"{BASE}/runs/STOP-night", "a").close()
        open(f"{BASE}/runs/HALF-pq1600", "a").close()
    if active:
        affinity("72-95")
        tot, runs = pss()
        if tot > 117 and runs:
            gib, name = max(runs)
            log(f"our PSS {tot:.1f} GiB > 117 GiB with another user active: stopping {name} ({gib:.1f} GiB)")
            subprocess.run(["bash", f"{BASE}/runs/stop-run.sh", name, "otheruser",
                            f"guard: another user active ({cores:.1f} cores, {rss_gb:.1f} GB), our PSS {tot:.1f} GiB"])
        if quiet >= 10:
            active = False
            affinity("48-95")
            os.remove(f"{BASE}/runs/HALF-pq1600")
            if created and os.path.exists(f"{BASE}/runs/STOP-night"):
                os.remove(f"{BASE}/runs/STOP-night")
            log("other users quiet for 10 min: CPUs 48-95, queue resumed" + ("" if created else " (STOP-night kept: not ours)"))
