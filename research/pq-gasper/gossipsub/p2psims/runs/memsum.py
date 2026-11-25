# Summed RSS and PSS (GiB, from /proc/<pid>/smaps_rollup) of this project's processes: shadow, wbsim and analysis
# python (repo/sim/ or .amp-out/ scripts). PSS divides shared pages (the wbsim binary, ~6.9 MiB per process) among
# the processes that map them, so its sum matches the drop in the machine's MemAvailable; summed RSS counts them once
# per process (+13.8 GiB at 2,048 hosts, measured Nov 07 19:39).
# Output: "RSS PSS" for the project, then "NAME RSS PSS" for each running shadow run (its process group).
import os

uid = os.getuid()
procs, names = [], {}
for p in os.listdir("/proc"):
    if not p.isdigit():
        continue
    try:
        if os.stat(f"/proc/{p}").st_uid != uid:
            continue
        comm = open(f"/proc/{p}/comm").read().strip()
        if comm not in ("shadow", "wbsim"):
            if not comm.startswith("python3"):
                continue
            args = open(f"/proc/{p}/cmdline").read()
            if "repo/sim/" not in args and ".amp-out/" not in args:
                continue
        rss = pss = 0
        for line in open(f"/proc/{p}/smaps_rollup"):
            if line.startswith("Rss:"):
                rss = int(line.split()[1])
            elif line.startswith("Pss:"):
                pss = int(line.split()[1])
        pg = os.getpgid(int(p))
        if comm == "shadow":
            names[pg] = os.path.basename(os.readlink(f"/proc/{p}/cwd"))
    except OSError:  # exited meanwhile
        continue
    procs.append((pg, rss, pss))
g = lambda kib: kib / 2 ** 20
print(f"{g(sum(x[1] for x in procs)):.1f} {g(sum(x[2] for x in procs)):.1f}")
for pg, name in names.items():
    print(f"{name} {g(sum(x[1] for x in procs if x[0] == pg)):.1f} {g(sum(x[2] for x in procs if x[0] == pg)):.1f}")
