#!/usr/bin/env python3
"""cf2 validation: per observer client, the logged scoring view (score_cfg), P3 deficit penalties per topic
group, IWANT promises and broken promises, and the most negative peer score seen in mesh events.
usage: cf2check.py RUN [FROM_SLOT]"""
import glob, json, os, sys
from collections import defaultdict

run = sys.argv[1]
from_slot = int(sys.argv[2]) if len(sys.argv) > 2 else 0
cfg = json.load(open(os.path.join(run, "run.json")))
client = {n["id"]: n.get("client", "?") for n in cfg["nodes"]}
views = defaultdict(set)
tot = defaultdict(lambda: defaultdict(float))
worst = defaultdict(list)
nodes = defaultdict(int)
for d in glob.glob(os.path.join(run, "shadow.data/hosts/*")):
    last, first_cfg = None, None
    for fn in glob.glob(os.path.join(d, "wbsim.*.stdout")):
        for line in open(fn):
            if '"ev":"tick"' in line:
                last = line
            elif '"ev":"score_cfg"' in line and first_cfg is None:
                first_cfg = json.loads(line)
            elif '"ev":"mesh"' in line:
                e = json.loads(line)
                if e.get("slot", -1) >= from_slot and e.get("score"):
                    worst[client[e["node"]]].append(e["score"][0])
    if first_cfg is None:
        continue
    c = client[first_cfg["node"]]
    nodes[c] += 1
    r = lambda v: None if v is None else tuple(round(x, 3) for x in v)
    views[c].add((first_cfg["slow_peer_weight"], first_cfg["iwant_promise_mode"], r(first_cfg["p3_pq"]),
                  r(first_cfg["p3_att"]), r(first_cfg["p3_block"])))
    if last:
        t = json.loads(last)
        for k, v in t.items():
            if isinstance(v, (int, float)) and ("deficit" in k or "promise" in k or "iwant" in k or "Deficit" in k
                                                 or "BrokenPromise" in k):
                tot[c][k] += v
print(f"run {run}, mesh events from slot {from_slot}")
for c in sorted(nodes):
    print(f"\n== {c}: {nodes[c]} hosts")
    for v in sorted(views[c], key=str):
        print(f"  view: slow_peer_w={v[0]} iwant_mode={v[1]}  P3 [weight, threshold, full-deficit cost]: "
              f"pq={v[2]} att={v[3]} block={v[4]}")
    for k in sorted(tot[c]):
        print(f"  {k} = {tot[c][k]:.0f}")
    t = tot[c]
    if t.get("iwant_rpcs"):
        print(f"  promises/IWANT = {t.get('iwant_promises', 0) / t['iwant_rpcs']:.3f}, "
              f"broken/IWANT = {t.get('broken_promises', 0) / t['iwant_rpcs']:.4f}")
    w = sorted(worst[c])
    if w:
        print(f"  most negative peer score per mesh event: min {w[0]:.1f}, p10 {w[len(w) // 10]:.1f}, "
              f"median {w[len(w) // 2]:.1f} ({len(w)} events)")
