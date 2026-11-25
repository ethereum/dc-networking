#!/usr/bin/env python3
"""Hosts that start failing late: per slot, PQ messages missing at 8 s, connected peers, peers dropped / added since the
previous slot's snapshot (and how many of the dropped were offline in between), PQ mesh degree (mean per PQ topic) and
its 1 Gbit share, failed sends (timed out / queue full) and tx / rx MB per slot; the same as means over a control group
(cloud hosts in the given cities, excluding HOSTS and EXCLUDE).
usage: farhosts.py RUN HOSTS CITIES [EXCLUDE]"""
import json, os, re, sys
from multiprocessing import Pool

run = sys.argv[1]
H = [int(x) for x in sys.argv[2].split(",")]
cities = set(sys.argv[3].split(","))
excl = {int(x) for x in sys.argv[4].split(",")} if len(sys.argv) > 4 else set()
cfg = json.load(open(os.path.join(run, "run.json")))
nodes = cfg["nodes"]
T0 = cfg["first_slot_s"]
sched = json.load(open(os.path.join(run, "sched.json")))
link = [n["link"] for n in nodes]
off = [n.get("offline", []) for n in nodes]
PQ = [str(t) for t in range(1, 17)]
TRE = re.compile(r'"t":([0-9.]+)')
ctrl = [n["id"] for n in nodes if n["link"] == "cloud" and n["city"] in cities and n["id"] not in H and n["id"] not in excl]
S = len(sched)


def host(i):
    fn = os.path.join(run, "shadow.data/hosts", f"n{i:04d}", "wbsim.1000.stdout")
    last, mesh, miss = {}, {}, {}
    for line in open(fn):
        if '"ev":"tick"' in line:
            m = TRE.search(line)
            if m:
                last[int((float(m.group(1)) - T0) // 12)] = line
        elif '"ev":"mesh"' in line:
            e = json.loads(line)
            mesh[e["slot"]] = e
        elif '"ev":"rx"' in line:
            e = json.loads(line)
            s = e["slot"]
            if s < S and e.get("on", True):
                miss[s] = sum(1 for (p, *_), r in zip(sched[s], e["r"]) if p != i and (r < 0 or r > 8000))
    tick = {k: json.loads(v) for k, v in last.items()}
    row = {}
    for s in range(2, S):
        e, ep = mesh.get(s), mesh.get(s - 1)
        r = {"miss": miss.get(s)}
        if e:
            c = set(e["conns"])
            r["conns"] = len(c)
            pq = [p for t in PQ for p in e["mesh"].get(t, [])]
            r["deg"] = len(pq) / max(1, sum(1 for t in PQ if t in e["mesh"]))
            r["fast"] = sum(link[p] == "cloud" for p in pq) / max(1, len(pq))
            if ep:
                cp = set(ep["conns"])
                a, b = T0 + 12 * (s - 1), T0 + 12 * s
                gone = cp - c
                r["drop"], r["add"] = len(gone), len(c - cp)
                r["drop_off"] = sum(any(x < b and y > a for x, y in off[p]) for p in gone)
        t, tp = tick.get(s), tick.get(s - 1)
        if t and tp:
            for k in ("f_timeout", "f_queue_full"):
                r[k] = t.get(k, 0) - tp.get(k, 0)
            r["txMB"] = (t.get("tx", 0) - tp.get("tx", 0)) / 1e6
            r["rxMB"] = (t.get("rx", 0) - tp.get("rx", 0)) / 1e6
        row[s] = r
    return i, row


with Pool(8) as pool:
    res = dict(pool.map(host, H + ctrl, chunksize=4))
slots = list(range(2, S))
KEYS = ["miss", "conns", "drop", "drop_off", "add", "deg", "fast", "f_timeout", "f_queue_full", "txMB", "rxMB"]
fmt = lambda v: "-" if v is None else (f"{v:.2f}" if isinstance(v, float) and abs(v) < 10 else f"{v:.0f}")
early, late = [s for s in slots if s <= 14], [s for s in slots if s >= 16]


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


print(f"{run}: slots {slots[0]}-{slots[-1]}; control = {len(ctrl)} cloud hosts in {sorted(cities)}")
for i in H:
    n = nodes[i]
    print(f"\nhost {i} ({n['client']}, {n['city']}, target {n['peer_target']}):")
    for k in KEYS:
        v = [res[i][s].get(k) for s in slots]
        print(f"  {k:12s} {' '.join(fmt(x) for x in v)}   | 2-14 {fmt(mean(v[:len(early)]))} -> 16-19 {fmt(mean(v[-len(late):]))}")
print("\ncontrol means per slot:")
for k in KEYS:
    v = [mean([res[c][s].get(k) for c in ctrl]) for s in slots]
    print(f"  {k:12s} {' '.join(fmt(x) for x in v)}   | 2-14 {fmt(mean(v[:len(early)]))} -> 16-19 {fmt(mean(v[-len(late):]))}")
