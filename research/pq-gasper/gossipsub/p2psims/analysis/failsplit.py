# Chronic incomplete hosts, and failed sends that cost slow-peer score split by kind, for one PQ run.
# usage: python3 .amp-out/failsplit.py RUN
# Chronic: a host incomplete (PQ, 8 s deadline, online) in at least half of the analysed slots (2 .. last).
# Failed sends (cumulative tick counters; rust-libp2p 0.49.5 adds +1 slow-peer penalty to the peer for each):
#   publish timeout  P_to = sum over topics of timedout_ minus forward_messages_dropped_per_topic (own publish dropped
#                    after 5 s; both gossipsub metrics, updated at the drop)
#   forward timeout  F_to = f_timeout - P_to (dropped after the 1 s queue timeout)
# (f_* come from SlowPeer events, reported at heartbeats, so only P_to mixes the two sources)
#   forward qfull    F_qf = f_forward - F_to (refused: non-priority queue at its 2,500 cap)
#   publish qfull    P_qf = f_publish - P_to (refused: per-peer publish counter at its 2,500 cap)
#   control qfull    C_qf = f_queue_full - F_qf - P_qf (IHAVE / IWANT / IDONTWANT refused, non-priority queue full)
import glob, json, os, sys
from collections import defaultdict
import numpy as np

sys.path.insert(0, "repo/sim")
import analyze

run = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
cfg = analyze.read_cfg(run)
nodes, t0, S = cfg["nodes"], cfg["first_slot_s"], cfg["slots"]
sched = cfg["sched"]
NEED_ALL = os.environ.get("PQ_NEED") == "all"  # every subscribed PQ subnet, ignoring a node's "need" (gen_config --backbone-subnets)
my = [[t for t in nd["topics"] if t < 100] if NEED_ALL or "need" not in nd else nd["need"] for nd in nodes]
P = [None if not m else (np.array([x[2] for x in m]), np.array([x[4] for x in m]), max(x[4] for x in m)) for m in sched]
inc = defaultdict(int); seen = defaultdict(int)
T = defaultdict(list)
GR = ["", "bg_block:", "bg_agg:", "bg_att:", "bg_col:", "bg_syncc:"]
for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    for line in open(f):
        if line.startswith('{"ev":"rx",'):
            e = json.loads(line); s, i = e["slot"], e["node"]
            if s < 2 or s >= len(P) or P[s] is None:
                continue
            a = t0 + 12 * s
            if any(x < a + P[s][2] / 1e3 and y > a for x, y in nodes[i].get("offline", [])):
                continue
            r = np.asarray(e["r"]); need = np.isin(P[s][0], my[i])
            seen[i] += 1
            inc[i] += bool((need & ~((r >= 0) & (r <= P[s][1]))).any())
        elif '"ev":"tick"' in line:
            e = json.loads(line)
            pto = sum(e.get(g + "timedout_messages_dropped_per_topic", 0) - e.get(g + "forward_messages_dropped_per_topic", 0) for g in GR)
            T[e["node"]].append((e["t"], e.get("f_forward", 0), e.get("f_publish", 0), e.get("f_queue_full", 0),
                                 e.get("f_timeout", 0), pto, e.get("conns", 0)))
ana = S - 2
print(f"== {os.path.basename(run.rstrip('/'))}: {len(nodes)} hosts, {S} slots, analysed slots 2-{S - 1}")
chronic = sorted((i for i in inc if inc[i] * 2 >= seen[i] and nodes[i]["link"] == "cloud"), key=lambda i: -inc[i])
rep = [i for i in inc if inc[i] >= 2 and nodes[i]["link"] == "cloud"]
cnt = lambda hs: dict(sorted(defaultdict(int, {c: sum(1 for i in hs if nodes[i]["client"] == c) for c in {nodes[i]["client"] for i in hs}}).items()))
allc = cnt([i for i in range(len(nodes)) if nodes[i]["link"] == "cloud"])
print(f" cloud hosts by client: {allc}")
print(f" chronic cloud hosts (incomplete in >= half of {ana} slots): {len(chronic)} {cnt(chronic)}")
for i in chronic:
    nd = nodes[i]
    print(f"   host {i}: {inc[i]}/{seen[i]} slots, {nd['client']} target {nd['peer_target']}, {nd['city']}")
print(f" cloud hosts incomplete in >= 2 slots: {len(rep)} {cnt(rep)}; incomplete at least once: "
      f"{cnt([i for i in inc if inc[i] and nodes[i]['link'] == 'cloud'])}")

# failed sends per kind, per slot window [start, start + 12 s), summed over hosts
A = {i: np.array(sorted(v)) for i, v in T.items()}
def at(i, t):
    a = A[i]; j = np.searchsorted(a[:, 0], t + 1e-6) - 1
    return a[max(j, 0), 1:]
def kinds(d):  # d = delta of (f_forward, f_publish, f_queue_full, f_timeout, P_to, conns)
    pto = d[4]; fto = d[3] - pto; fqf = d[0] - fto; pqf = d[1] - pto; cqf = d[2] - fqf - pqf
    return np.array([fto, fqf, cqf, pto, pqf])
K = ["fwd timeout", "fwd qfull", "ctrl qfull", "pub timeout", "pub qfull"]
rust = lambda i: nodes[i]["client"] in ("lighthouse", "other")
tot = defaultdict(lambda: np.zeros(5)); per = []
for s in range(S):
    a = t0 + 12 * s; row = np.zeros(5); pq_conn = []
    for i in A:
        k = kinds(at(i, a + 12) - at(i, a))
        row += k
        tot[(nodes[i]["link"], "rust" if rust(i) else "non-rust")] += k
        c = at(i, a + 12)[5]
        if c:
            pq_conn.append(k[4] / c)
    per.append((row, np.mean(pq_conn), sum(1 for x in pq_conn if x > 0)))
allk = sum(tot.values())
print(" failed sends that cost score, whole run, share by kind (%):",
      {k: round(100 * v / allk.sum(), 1) for k, v in zip(K, allk)}, f"total {allk.sum():.0f}")
for key in sorted(tot):
    v = tot[key]
    print(f"   {key[0]:6s} {key[1]:8s} hosts={sum(1 for i in A if (nodes[i]['link'], 'rust' if rust(i) else 'non-rust') == key)}: "
          + ", ".join(f"{k} {100 * x / max(v.sum(), 1):.1f} %" for k, x in zip(K, v)) + f" (total {v.sum():.0f})")
print(" per slot, summed over hosts (thousands): fwd timeout / fwd qfull / ctrl qfull / pub timeout / pub qfull;"
      " own-publish refusals per connection (mean over hosts); hosts with any")
for s, (row, pc, n) in enumerate(per):
    print(f"   slot {s:2d}: " + " / ".join(f"{x / 1e3:.1f}" for x in row) + f"; {pc:.3f}; {n}")
