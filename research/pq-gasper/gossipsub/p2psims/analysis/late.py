# What PQ traffic arrives 8-16 s into a slot (after the deadline, before the next burst)? Per slot and class, means per
# online node-slot (pqdiag's rule: online from the slot start to the deadline):
#   first = needed PQ messages of the slot (own left out) first received after the deadline and by 16 s, from the rx
#           records; later = first received after 16 s (the records end at 20 s). These are the true late first
#           deliveries: per node they cannot exceed the messages missing at the deadline.
#   stale = copies older than max_msg_age_s (60 s) that gossipsub's 60 s duplicate cache no longer filters: counted in
#           topic_msg_recv_counts as new messages, then ignored by wbsim (stale_pq). Until Nov 11 13:3x this script
#           reported topic_msg_recv_counts as 'first', which included them, and took the tick before a boundary when
#           the boundary tick was logged ~1 ms late (window from 7.5 s); now ticks within 50 ms of a boundary count.
#   copies, kB, iwant, mcache-miss = tick counters (all copies, bytes, IWANT-requested messages, mcache misses).
# Window 4-8 s: first = needed messages held by the deadline. Also the PQ publish offsets per slot.
import glob, json, os, re, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, "repo/sim"); import analyze
run = "runs/" + sys.argv[1]
cfg = analyze.read_cfg(run); nodes, t0, S = cfg["nodes"], cfg["first_slot_s"], cfg["slots"]
link = [nd["link"] for nd in nodes]
off_iv = [nd.get("offline", []) for nd in nodes]
NEED_ALL = os.environ.get("PQ_NEED") == "all"  # every subscribed PQ subnet, ignoring a node's "need" (gen_config --backbone-subnets)
my_pq = [[t for t in nd["topics"] if t < 100] if NEED_ALL or "need" not in nd else nd["need"] for nd in nodes]
if any("need" in nd for nd in nodes):
    print(f"  completeness on {'every subscribed PQ subnet (PQ_NEED=all)' if NEED_ALL else 'needed PQ subnets (node field need)'}"
          f"; {sum('need' in nd for nd in nodes)} nodes have a need field")
sched = cfg["sched"]
pqs = {}
for s, msgs in enumerate(sched):
    if msgs:
        a = np.array([[m[0], m[1], m[2], m[4]] for m in msgs], dtype=np.int64)
        pqs[s] = dict(pub=a[:, 0], topic=a[:, 2], dl=a[:, 3], dlmax=int(a[:, 3].max()))
K = ["topic_msg_recv_counts_unfiltered", "topic_msg_recv_bytes", "topic_iwant_msgs", "memcache_misses", "stale_pq"]
RE = {k: re.compile(r'"%s":([0-9.]+)' % k) for k in ["t", "node"] + K}
CL = ("50x15", "50x25", "cloud")
acc = defaultdict(lambda: np.zeros(14))  # (slot, class) -> [n, held, first, later, w1 x5, w2 x5]
for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    ticks, rx, node = [], {}, None
    for line in open(f):
        if line.startswith('{"ev":"rx",'):
            e = json.loads(line); node = e["node"]
            if e["slot"] in pqs:
                rx[e["slot"]] = np.asarray(e["r"], dtype=np.int64)
        elif '"ev":"tick"' in line:
            row = []
            for k in ["t"] + K:
                m = RE[k].search(line)
                row.append(float(m.group(1)) if m else 0.0)
            ticks.append(row)
            if node is None:
                node = int(RE["node"].search(line).group(1))
    if node is None or not ticks:
        continue
    T = np.array(sorted(ticks))
    def at(t):
        return T[max(np.searchsorted(T[:, 0], t + 0.05) - 1, 0), 1:]
    i, c = node, link[node]
    for s, P in pqs.items():
        a = t0 + 12 * s
        if any(x < a + P["dlmax"] / 1e3 and y > a for x, y in off_iv[i]):
            continue
        v = acc[(s, c)]
        v[0] += 1
        r = rx.get(s)
        if r is not None:
            need = np.isin(P["topic"], my_pq[i]) & (P["pub"] != i)
            v[1] += int((need & (r >= 0) & (r <= P["dl"])).sum())
            v[2] += int((need & (r > P["dl"]) & (r <= 16000)).sum())
            v[3] += int((need & (r > 16000)).sum())
        v[4:9] += at(a + 8) - at(a + 4)
        v[9:14] += at(a + 16) - at(a + 8)
for s in range(S):
    offs = np.array([m[1] for m in sched[s]]) if s < len(sched) and sched[s] else np.zeros(1)
    out = []
    for c in CL:
        v = acc.get((s, c))
        if v is None or v[0] == 0:
            continue
        m = v / v[0]
        out.append(f"{c}: 4-8 s first {m[1]:.0f} copies {m[4]:.0f} iwant {m[6]:.0f} | 8-16 s first {m[2]:.2f} later {m[3]:.2f} "
                   f"stale {m[13]:.2f} copies {m[9]:.0f} kB {m[10]/1e3:.0f} iwant {m[11]:.0f} mcache-miss {m[12]:.0f}")
    print(f"slot {s}: pub offsets ms p50/p99/max {np.percentile(offs,50):.0f}/{np.percentile(offs,99):.0f}/{offs.max()}; " + " || ".join(out))
