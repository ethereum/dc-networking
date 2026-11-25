# usage: python3 .amp-out/bgexcess.py RUN (> 1.03 in a slot = old messages accepted again: recirculation)
# First deliveries per slot window summed over hosts, per topic group (PQ and background), relative to the run's
# median slot: a jump means old messages were accepted again.
import glob, json, sys
from collections import defaultdict
import numpy as np
run = "runs/" + sys.argv[1]
cfg = json.load(open(f"{run}/run.json")); t0, S = cfg["first_slot_s"], cfg["slots"]
G = ["", "bg_att:", "bg_agg:", "bg_block:", "bg_col:", "bg_syncc:"]
T = defaultdict(list)
for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    for line in open(f):
        if '"ev":"tick"' in line:
            e = json.loads(line); T[e["node"]].append([e["t"]] + [e.get(g + "topic_msg_recv_counts", 0) for g in G])
A = {i: np.array(sorted(v)) for i, v in T.items()}
def at(i, t):
    a = A[i]; j = np.searchsorted(a[:, 0], t + 1e-6) - 1
    return a[max(j, 0), 1:]
tot = np.array([sum(at(i, t0 + 12 * s + 12) - at(i, t0 + 12 * s) for i in A) for s in range(S)])
med = np.median(tot[2:], axis=0)
for k, g in enumerate(G):
    print(f"{(g or 'pq:'):10s}", [round(float(x / med[k]), 3) if med[k] else None for x in tot[:, k]])
