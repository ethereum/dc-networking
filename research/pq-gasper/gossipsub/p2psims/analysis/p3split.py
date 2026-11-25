#!/usr/bin/env python3
"""P3 around activation (slot 15): MessageDeficit penalties per slot by observer client and topic group (per-topic
counter only in cf2 runs), and, for chosen hosts, mesh prunes, own deficit penalties, PQ mesh in/out degree and how
many views score them negative, per slot.
usage: p3split.py RUN HOST[,HOST...] [FIRST LAST]"""
import glob, json, os, re, sys
from collections import defaultdict
from multiprocessing import Pool

run = sys.argv[1]
H = [int(x) for x in sys.argv[2].split(",")]
CTRL = [int(x) for x in os.environ.get("CTRL", "").split(",") if x]  # optional control group: per-host means
HALL = set(H) | set(CTRL)
lo, hi = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (2, 19)
cfg = json.load(open(os.path.join(run, "run.json")))
T0 = cfg.get("first_slot_s", 30)
assert cfg.get("slot_s", 12) == 12
client = {n["id"]: n.get("client", "?") for n in cfg["nodes"]}
PQ = {str(t) for t in range(1, 17)}
KEYS = ["scoring_penalties:MessageDeficit", "mesh_peer_churn_events:Prune", "mesh_peer_churn_events:BadScore",
        "mesh_peer_counts", "message_deficit_per_topic", "bg_att:message_deficit_per_topic",
        "bg_block:message_deficit_per_topic", "bg_agg:message_deficit_per_topic"]
TRE = re.compile(r'"t":([0-9.]+)')


def host(d):
    last = {}  # slot -> raw tick line (last tick in the slot)
    neg, indeg, own = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(int)), {}
    node = None
    for fn in glob.glob(os.path.join(d, "wbsim.*.stdout")):
        for line in open(fn):
            if '"ev":"tick"' in line:
                m = TRE.search(line)
                if m:
                    last[int((float(m.group(1)) - T0) // 12)] = line
            elif '"ev":"mesh"' in line:
                e = json.loads(line)
                s, node = e["slot"], e["node"]
                rust = client[node] in ("lighthouse", "other")
                for p, sc in e.get("neg") or []:
                    if p in HALL:
                        neg[p][s].append((sc, client[node]))
                for t, ids in e["mesh"].items():
                    if t in PQ:
                        for p in ids:
                            if p in HALL:
                                indeg[p][s] += 1
                if node in HALL:
                    own[s] = sum(len(v) for t, v in e["mesh"].items() if t in PQ)
    snap = {}
    for k, line in last.items():
        t = json.loads(line)
        node = t.get("node", node)
        snap[k] = [t.get(x, 0) for x in KEYS]
    return node, snap, {p: dict(v) for p, v in neg.items()}, {p: dict(v) for p, v in indeg.items()}, own


dirs = sorted(glob.glob(os.path.join(run, "shadow.data/hosts/*")))
with Pool(8) as pool:
    res = pool.map(host, dirs, chunksize=16)
snaps = {}
negs, indeg, own = defaultdict(lambda: defaultdict(list)), defaultdict(lambda: defaultdict(int)), {}
for node, snap, ng, ind, ow in res:
    if node is None:
        continue
    snaps[node] = snap
    for p, v in ng.items():
        for s, l in v.items():
            negs[p][s] += l
    for p, v in ind.items():
        for s, c in v.items():
            indeg[p][s] += c
    if node in HALL:
        own[node] = ow


def delta(i, s, k):  # counter change over slot s (last tick of slot s minus last tick of slot s - 1)
    a, b = snaps[i].get(s - 1), snaps[i].get(s)
    return (b[k] - a[k]) if a and b else 0


slots = list(range(lo, hi + 1))
print(f"{run}: slots {lo}-{hi}")
print("MessageDeficit penalties per slot by observer client (sum over hosts; hosts):")
for c in sorted(set(client.values())):
    hs = [i for i in snaps if client[i] == c]
    print(f"  {c:10s} ({len(hs):4d})", [sum(delta(i, s, 0) for i in hs) for s in slots])
print("MessageDeficit per topic group (cf2 binary only): PQ / att / block / agg")
for j, g in [(4, "pq"), (5, "att"), (6, "block"), (7, "agg")]:
    print(f"  {g:6s}", [sum(delta(i, s, j) for i in snaps) for s in slots])
print("MessageDeficit from slot 15 by observer client and topic group (cf2 binary only), sum / per host:")
for c in sorted(set(client.values())):
    hs = [i for i in snaps if client[i] == c]
    row = [(g, sum(delta(i, s, j) for i in hs for s in slots if s >= 15)) for j, g in
           [(4, "pq"), (5, "att"), (6, "block"), (7, "agg")]]
    print(f"  {c:10s} ({len(hs):4d})", ", ".join(f"{g} {v} ({v / max(1, len(hs)):.2f})" for g, v in row))
print("MessageDeficit per slot by observer client and topic group (cf2 binary only): pq / att / block / agg")
for c in sorted(set(client.values())):
    hs = [i for i in snaps if client[i] == c]
    for j, g in [(4, "pq"), (5, "att"), (6, "block"), (7, "agg")]:
        print(f"  {c:10s} {g:5s}", [sum(delta(i, s, j) for i in hs) for s in slots])
top = sorted(snaps, key=lambda i: -sum(delta(i, s, 0) for s in slots if s >= 15))[:10]
print("observers with the most MessageDeficit penalties from slot 15:",
      [(i, client[i], sum(delta(i, s, 0) for s in slots if s >= 15)) for i in top])
SPLIT = int(os.environ.get("SPLIT", "0"))  # optional: means over slots [lo, SPLIT) and [SPLIT, hi] instead of lists
CL = sorted(set(client.values()))
med = lambda xs: round(sorted(xs)[len(xs) // 2], 1) if xs else None


def rows(h):
    ng = negs[h]
    r = {"PQ Prune received": [delta(h, s, 1) for s in slots],
         "PQ BadScore removed": [delta(h, s, 2) for s in slots],
         "own MessageDeficit": [delta(h, s, 0) for s in slots],
         "own PQ mesh links": [own.get(h, {}).get(s) for s in slots],
         "in others' PQ mesh": [indeg[h].get(s, 0) for s in slots],
         "views negative": [len(ng.get(s, [])) for s in slots]}
    for c in CL:
        r[f"  of them {c}"] = [sum(1 for _, o in ng.get(s, []) if o == c) for s in slots]
    r["median neg score"] = [med([x for x, _ in ng.get(s, [])]) for s in slots]
    r["median neg, non-Rust"] = [med([x for x, o in ng.get(s, []) if o not in ("lighthouse", "other")]) for s in slots]
    r["median neg, T/L/N"] = [med([x for x, o in ng.get(s, []) if o in ("teku", "lodestar", "nimbus")]) for s in slots]
    return r


def show(k, v):
    if not SPLIT:
        print(f"  {k:22s}", v)
        return
    f = lambda xs: round(sum(xs) / len(xs), 2) if xs else None
    a = [x for s, x in zip(slots, v) if s < SPLIT and x is not None]
    b = [x for s, x in zip(slots, v) if s >= SPLIT and x is not None]
    print(f"  {k:22s} mean slots {lo}-{SPLIT - 1}: {f(a)} | {SPLIT}-{hi}: {f(b)}")


for h in H:
    print(f"\nhost {h} ({client[h]}):")
    for k, v in rows(h).items():
        show(k, v)
if CTRL:
    R = [rows(h) for h in CTRL]
    print(f"\ncontrol group: {len(CTRL)} hosts, per-host means per slot")
    for k in R[0]:
        col = [[r[k][j] for r in R if r[k][j] is not None] for j in range(len(slots))]
        show(k, [round(sum(x) / len(x), 2) if x else None for x in col])
