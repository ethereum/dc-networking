#!/usr/bin/env python3
"""rtt3 checks from the tcpd lines of a run on the rtt3 build (LNXBUF_LOG=1): post-RTO cwnd against in-flight + 1
("tcpd rto3"), and per recovery ("tcpd recovered": first RTO until every packet outstanding at its RTOs is acked)
resends of that data and duration, by path type and Eifel verdict.
usage: rtt3diag.py RUNDIR [CONFIGDIR]"""
import collections, gzip, json, os, statistics, sys

run = sys.argv[1]
cfg = sys.argv[2] if len(sys.argv) > 2 else run
nodes = json.load(open(f"{cfg}/run.json"))["nodes"]
hostcls = {f"n{n['id']:04d}": n["cls"] for n in nodes}
ipcls = {n["ip"]: n["cls"] for n in nodes}
G = lambda a, b: ("1G" if a == "cloud" else "home") + "->" + ("1G" if b == "cloud" else "home")
GROUPS = ["1G->1G", "1G->home", "home->1G", "home->home"]
path = next(f"{run}/{n}" for n in ("shadow-tcpd.log.gz", "shadow.log", "shadow.log.gz") if os.path.exists(f"{run}/{n}"))
opener = gzip.open if path.endswith(".gz") else open


def peercls(ip):
    return ipcls.get(".".join(str((ip >> k) & 255) for k in (0, 8, 16, 24)), "?")


cur = {}
rto = collections.Counter()  # (path, cwnd == inflight + 1) ; also inflight distribution
infl = collections.Counter()
cw = collections.Counter()
newwatch = collections.Counter()
rec = collections.defaultdict(list)  # (path, verdict) -> [(dur ms, resends, timeouts, episodes, outstanding, ssthresh)]
for line in opener(path, "rt", errors="replace"):
    k = line.find("] tcpd ")
    if k < 0:
        continue
    tok = line[k + 7:].split()
    kind, ptr = tok[0], tok[1]
    i = line.find("] [n")
    host = line[i + 3:i + 8]
    d = dict(zip(tok[2::2], tok[3::2]))
    if kind == "snap":
        cur[(host, ptr)] = G(hostcls.get(host, "?"), peercls(int(d["peer"])))
        continue
    g = cur.get((host, ptr), "?")
    if kind == "rto3":
        f, c = int(d["inflight"]), int(d["cwnd"])
        rto[(g, c == f + 1)] += 1
        infl[min(f, 3)] += 1
        cw[min(c, 11)] += 1
        newwatch[g] += int(d["newwatch"])
    elif kind == "recovered":
        rec[(g, int(d["spurious"]))].append((int(d["dur"]) / 1000, int(d["resends"]), int(d["timeouts"]),
                                             int(d["episodes"]), int(d["outstanding"]), int(d["ssthresh"])))

n = sum(rto.values())
ok = sum(v for (g, m), v in rto.items() if m)
print(f"RTOs {n}: cwnd == in-flight + 1 in {ok} ({100 * ok / max(n, 1):.2f} %); in-flight at the RTO (3 = 3+): "
      f"{sorted(infl.items())}; cwnd after (11 = 11+): {sorted(cw.items())}")
q = lambda v, p: sorted(v)[min(len(v) - 1, int(p * len(v)))] if v else float("nan")
V = {1: "spurious", 0: "genuine", -1: "no Eifel check"}
print("\nrecoveries: count | resends of the RTO's data per recovery mean / p50 / p90 / max | RTOs per recovery mean | "
      "share with 1 episode | duration ms p50 / p90 / p99 | recoveries started but not finished")
for g in GROUPS + ["all"]:
    for v in (1, 0, -1):
        rows = [r for (gg, vv), rs in rec.items() if vv == v and (g == "all" or gg == g) for r in rs]
        if not rows:
            continue
        rs = [r[1] for r in rows]
        du = [r[0] for r in rows]
        print(f"{g:10s} {V[v]:15s} {len(rows):6d} | {statistics.mean(rs):5.2f} / {q(rs, .5)} / {q(rs, .9)} / {max(rs)} | "
              f"{statistics.mean(r[2] for r in rows):4.2f} | {100 * sum(r[3] == 1 for r in rows) / len(rows):5.1f} % | "
              f"{q(du, .5):7.0f} / {q(du, .9):7.0f} / {q(du, .99):7.0f}")
    if g != "all":
        fin = sum(len(rs) for (gg, vv), rs in rec.items() if gg == g)
        print(f"{g:10s} unfinished {newwatch[g] - fin}")
gen = [r for (gg, vv), rs in rec.items() if vv == 0 for r in rs]
for lab, sel in (("genuine, 1 RTO", lambda r: r[2] == 1), ("genuine, 2+ RTOs", lambda r: r[2] >= 2)):
    du = [r[0] for r in gen if sel(r)]
    ss = [r[5] for r in gen if sel(r)]
    if du:
        print(f"{lab:18s} {len(du):6d} recoveries, duration ms p50 / p90 / p99 {q(du, .5):.0f} / {q(du, .9):.0f} / "
              f"{q(du, .99):.0f}; ssthresh at the end p10 / p50 {q(ss, .1)} / {q(ss, .5)}")
