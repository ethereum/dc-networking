# Summary of one PQ realism run (usage: python3 .amp-out/pqsum.py RUN_NAME_OR_DIR).
# Sources: realism.json (realism_check.py: pq completion excluding offline node-slots, prop, scoring, peers, bg),
# summary2.json (analyze.py --levers: κ incl. background bytes, IDONTWANT, failed forwards, up/down use in the
# 4 s window), and the tick counters for per-slot PQ backlog: PQ bytes a node receives after the 4 s deadline.
import glob, json, os, sys
from collections import defaultdict
import numpy as np

d = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
r = json.load(open(f"{d}/realism.json"))
cfg = json.load(open(f"{d}/run.json"))
nodes, t0, S = cfg["nodes"], cfg["first_slot_s"], cfg["slots"]
lever = cfg.get("lever", "")
ps = lever.split("--peer-scale")[-1].split()[0] if "--peer-scale" in lever else "1.0"
print(f"== {os.path.basename(d.rstrip('/'))}: {len(nodes)} hosts, {S} slots, peer-scale {ps}")

pq = r["pq"]
print(" PQ complete per slot (% of online node-slots):", pq["complete_per_slot_pct"])
for c, v in pq["per_class"].items():
    print(f"  {c}: {v['complete_pct']} % of {v['node_slots']} node-slots; latency from publish p50/p99 {v['lat_p50_p99_s']} s")
print(f"  offline node-slots excluded {pq['node_slots_offline_excluded']}, PQ signatures lost to churn {pq['pq_lost_to_churn']}")

s2p = f"{d}/summary2.json"
if os.path.exists(s2p):
    s2 = json.load(open(s2p))
    p = s2["per_slot"]
    print(f" analyze.py: slots covered {s2['slots']}, latency p50/p90/p99/max {s2['lat_ms']} ms")
    for k in ("kappa", "copies", "idontwant", "fwd_dropped", "queue_full", "never", "rx_MiB", "tail_MiB"):
        print(f"  {k:12s}", [round(x[k], 2) if isinstance(x[k], float) else x[k] for x in p])
    for c, v in s2["classes"].items():
        print(f"  {c}: up {100*v['up_win']:.0f} % of cap in the 4 s window (max node {100*v['up_win_max']:.0f} %), "
              f"down {100*v['down_win']:.0f} % (max {100*v['down_win_max']:.0f} %), up over slot {100*v['up_use']:.0f} %")

pr = r.get("prop") or {}
for k in ("block", "col", "att", "agg"):
    if k in pr:
        v = pr[k]
        print(f" {k}: from slot start p10/50/90/95/99 {v['from_slot_start_s']}, missing {v['missing']}/{v['deliveries']}")
bg = r.get("bg") or {}
if isinstance(bg, dict):
    print(" copies per unique message (incl. pq):", bg.get("copies_per_unique_msg"))
    for c, v in bg.get("per_class", {}).items():
        print(f"  {c}: rx p50/p90 {v['rx_kB_s'][1]*8/1e3:.1f}/{v['rx_kB_s'][2]*8/1e3:.1f} Mbit/s, "
              f"tx p50/p90 {v['tx_kB_s'][1]*8/1e3:.1f}/{v['tx_kB_s'][2]*8/1e3:.1f} Mbit/s (slot average), pq {v.get('pq_recv_kB_per_slot')} kB/slot")
sc = r.get("scoring")
if isinstance(sc, dict):
    print(" mesh links per slot:", [x["mesh_links"] for x in sc["per_slot"]])
    print(" peers with negative score per slot:", [x["peers_with_negative_score"] for x in sc["per_slot"]], sc["penalties"])
pe = r.get("peers") or {}
print(" conns:", {k: v["conns"]["mean"] for k, v in pe.items() if "conns" in v})
print(" mesh pq/att by link:", {k: (v.get("mesh_pq", {}).get("mean"), v.get("mesh_att", {}).get("mean")) for k, v in pe.items() if k.startswith("link:")})

# per-slot PQ backlog and forward failures from the tick counters; mesh sizes per slot from the mesh events
ticks = defaultdict(list)
mesh = defaultdict(lambda: defaultdict(lambda: [0, 0, 0, 0]))  # slot -> link class -> nodes, links, PQ links, PQ topics
for f in glob.glob(f"{d}/shadow.data/hosts/*/wbsim.*.stdout"):
    for line in open(f):
        if '"ev":"tick"' in line:
            e = json.loads(line)
            ticks[e["node"]].append((e["t"], e.get("topic_msg_recv_bytes", 0), e.get("f_forward", 0), e.get("f_timeout", 0),
                                     e.get("f_queue_full", 0)))
        elif '"ev":"mesh"' in line:
            e = json.loads(line)
            m = mesh[e["slot"]][nodes[e["node"]]["link"]]
            m[0] += 1
            for t, v in e["mesh"].items():
                m[1] += len(v)
                if int(t) < 100:  # PQ topics; background topics are >= 100
                    m[2] += len(v)
                    m[3] += 1
sl = sorted(mesh)
print(" mesh links per node (all topics) by slot:",
      [round(sum(m[1] for m in mesh[s].values()) / max(sum(m[0] for m in mesh[s].values()), 1), 1) for s in sl])
for c in sorted({c for s in sl for c in mesh[s]}):
    print(f"  PQ mesh size per joined PQ topic, {c}:", [round(mesh[s][c][2] / max(mesh[s][c][3], 1), 2) for s in sl])
done = len(pq["complete_per_slot_pct"])
late = defaultdict(lambda: [[] for _ in range(done)])
fail = defaultdict(lambda: [[] for _ in range(done)])
for i, tk in ticks.items():
    tk.sort()
    tt = np.array([x[0] for x in tk])
    at = lambda t, j: tk[max(0, min(len(tk) - 1, np.searchsorted(tt, t - 1e-6)))][j]
    c = nodes[i]["link"]
    for s in range(done):
        a = t0 + 12 * s
        if tt[-1] < a + 16 - 1e-6:
            continue
        # PQ is published 4.0-4.5 s into the slot with an 8 s deadline: bytes from 8 s to the next burst (16 s)
        late[c][s].append((at(a + 16, 1) - at(a + 8, 1)) / 1e3)
        fail[c][s].append((at(a + 12, 2) - at(a, 2), at(a + 12, 3) - at(a, 3), at(a + 12, 4) - at(a, 4)))
print(" PQ kB received after the deadline (8 s) until the next burst (16 s), per node, mean per slot (backlog signal):")
for c in sorted(late):
    print(f"  {c}:", [round(float(np.mean(x)), 1) if x else None for x in late[c]])
# SlowPeer counters (libp2p-gossipsub FailedMessages): f_forward = forward messages that failed for any reason;
# f_timeout = messages (forward or publish) dropped after their queue timeout; f_queue_full = messages refused by a
# full queue, including IHAVE/IWANT/IDONTWANT, so the last two can add up to more than the first
print(" failed sends per node per slot, mean (forward msgs failed / any msg timed out / any msg refused, queue full):")
for c in sorted(fail):
    print(f"  {c}:", [tuple(round(float(np.mean([y[j] for y in x])), 1) for j in range(3)) if x else None for x in fail[c]])
