# Attestation misses split by receiver type (all-64-subnet vs 2-subnet hosts) and link class, plus forward
# timeouts (dropped forwards) per node per slot from tick counters. Reads only rxbg/tick lines.
import json, sys, glob, os
from collections import defaultdict
sys.path.insert(0, "repo/sim"); import perturb
run = "runs/" + sys.argv[1]
cfg = json.load(open(f"{run}/run.json")); bg = json.load(open(f"{run}/bg.json"))
nodes, t0 = cfg["nodes"], cfg["first_slot_s"]
KATT = perturb.KINDS.index("att")
rx = defaultdict(dict); ticks = defaultdict(list)
for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    for line in open(f):
        if line.startswith('{"ev":"rxbg"'):
            e = json.loads(line); rx[e["slot"]][e["node"]] = {k for k, ms in e["r"]}
        elif '"ev":"tick"' in line:
            e = json.loads(line); ticks[e["node"]].append((e["t"], e["f_timeout"], e.get("f_queue_full", 0), e.get("f_forward", 0)))
natt = lambda nd: sum(1 for t in nd["topics"] if 200 <= t < 300)
typ = lambda nd: "all64" if natt(nd) == 64 else f"{natt(nd)}sub"
subs = defaultdict(list)
for i, nd in enumerate(nodes):
    for t in nd["topics"]:
        subs[t].append(i)
off = lambda i, s: any(x < t0 + 12 * (s + 1) and y > t0 + 12 * s for x, y in nodes[i].get("offline", []))
tot, miss = defaultdict(int), defaultdict(int)
for s, msgs in enumerate(bg):
    if s < 2: continue
    for k, m in enumerate(msgs):
        if m[4] != KATT or not m[5]: continue
        for i in subs[m[2]]:
            if i == m[0] or off(i, s): continue
            key = (typ(nodes[i]), nodes[i]["link"])
            tot[key] += 1
            if k not in rx[s].get(i, ()): miss[key] += 1
print("att misses by receiver type, link: missed / deliveries (%)")
for key in sorted(tot):
    print(f"  {key[0]:6s} {key[1]:6s} {miss[key]:7d} / {tot[key]:8d}  {100*miss[key]/tot[key]:.2f} %  nodes={sum(1 for nd in nodes if (typ(nd), nd['link'])==key)}")
for t in sorted({k[0] for k in tot}):
    a = sum(miss[k] for k in miss if k[0] == t); b = sum(tot[k] for k in tot if k[0] == t)
    print(f"  {t}: {100*a/b:.2f} % of {b}")
# forward timeouts (rust-libp2p drops a queued forward after its timeout) per node per slot, steady slots
S = cfg["slots"]; lo, hi = t0 + 24, t0 + 12 * S
per = defaultdict(list)
for i, tk in ticks.items():
    tk.sort(); a = [x for x in tk if x[0] <= lo]; b = [x for x in tk if x[0] <= hi]
    if a and b: per[nodes[i]["link"]].append(tuple((b[-1][j] - a[-1][j]) / ((hi - lo) / 12) for j in (3, 1, 2)))
import numpy as np
# f_forward counts forward messages gossipsub failed to send (SlowPeer events); f_timeout and f_queue_full split them
for c, v in sorted(per.items()):
    fw, to, qf = ([x[j] for x in v] for j in range(3))
    print(f"  failed forwards per node per slot, {c}: mean {np.mean(fw):.0f} (p50 {np.percentile(fw,50):.0f}, p90 {np.percentile(fw,90):.0f}, "
          f"max {max(fw):.0f}); timed out {np.mean(to):.0f}, queue full {np.mean(qf):.0f} (n={len(v)})")
