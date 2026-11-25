# Compare summed RSS, summed PSS (smaps_rollup) and the machine's MemAvailable drop for this project's processes.
# usage: python3 memcheck.py [IDLE_AVAIL_KIB]
import os, sys, time
def rollup(pid):
    d = {}
    try:
        for line in open(f"/proc/{pid}/smaps_rollup"):
            f = line.split()
            if len(f) >= 3 and f[0].endswith(":") and f[2] == "kB":
                d[f[0][:-1]] = int(f[1])
    except OSError:
        return None
    return d
uid = os.getuid()
t = time.time()
tot, n, per = {}, {}, {}
for p in os.listdir("/proc"):
    if not p.isdigit():
        continue
    try:
        if os.stat(f"/proc/{p}").st_uid != uid:
            continue
        comm = open(f"/proc/{p}/comm").read().strip()
        args = open(f"/proc/{p}/cmdline").read().replace("\0", " ")
    except OSError:
        continue
    if comm not in ("shadow", "wbsim") and not (comm.startswith("python3") and ("repo/sim/" in args or ".amp-out/" in args)):
        continue
    r = rollup(p)
    if r is None:
        continue
    k = comm if comm in ("shadow", "wbsim") else "python3"
    n[k] = n.get(k, 0) + 1
    for key, v in r.items():
        tot.setdefault(k, {}).setdefault(key, 0)
        tot[k][key] += v
dt = time.time() - t
mi = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
g = lambda kib: kib / 2**20
print(f"read {sum(n.values())} smaps_rollup in {dt:.1f} s")
allr = sum(v.get("Rss", 0) for v in tot.values()); allp = sum(v.get("Pss", 0) for v in tot.values())
for k, v in tot.items():
    print(f"  {k}: n={n[k]} Rss {g(v.get('Rss',0)):.2f} GiB, Pss {g(v.get('Pss',0)):.2f}, Shared_Clean {g(v.get('Shared_Clean',0)):.2f}, "
          f"Shared_Dirty {g(v.get('Shared_Dirty',0)):.2f}, Private_Dirty {g(v.get('Private_Dirty',0)):.2f}, Swap {g(v.get('Swap',0)):.2f}; "
          f"Rss-Pss per process {(v.get('Rss',0)-v.get('Pss',0))/n[k]/1024:.2f} MiB")
print(f"  total Rss {g(allr):.2f} GiB, total Pss {g(allp):.2f} GiB, difference {g(allr-allp):.2f} GiB")
print(f"  MemAvailable {g(mi['MemAvailable']):.2f} GiB, PageTables {g(mi['PageTables']):.2f}, Shmem {g(mi['Shmem']):.2f}, SUnreclaim {g(mi['SUnreclaim']):.2f}")
if len(sys.argv) > 1:
    idle = int(sys.argv[1])
    print(f"  MemAvailable drop vs idle {g(idle):.2f} GiB: {g(idle - mi['MemAvailable']):.2f} GiB")
