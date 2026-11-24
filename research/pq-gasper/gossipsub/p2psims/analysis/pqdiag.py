# Per-class miss analysis and per-slot mesh/score diagnostics for one run (PQ or no-PQ).
# usage: python3 .amp-out/pqdiag.py RUN [--slots A B]   (default: slots 2 .. last; the pass rule starts at slot 2)
#
# Item 1 (PQ runs): per class (link class), on online node-slots (same exclusion as realism_check.sec_pq: a host
#   offline at any time between slot start and the deadline is left out):
#   - node-slot completeness per slot (all needed PQ messages by the 8 s deadline) -> the pass rule;
#   - PQ message miss rate: (node, message) pairs missing at the deadline / pairs needed (own messages left out),
#     also at deadline + 1 s;
#   - what the incomplete node-slots are (first matching reason): host rejoined <= 12 s before the slot start,
#     rejoined 12-60 s before, a whole subscribed PQ subnet missing, >= 1 message never delivered (not by 20 s),
#     near miss (all missing messages held by deadline + 1 s), late (all held, some > 1 s late);
#     plus repeat hosts (incomplete in >= 2 of the analysed slots) and messages most subscribers missed.
# BLS baseline (runs with --bg): attestation (tracked) miss rate per class and subscription type, at 8 s after
#   the slot start (aggregation deadline) and never (not by slot end + drain), same exclusions as attmiss.py.
# Item 2: per slot (mesh snapshot at 3.95 s, just before the PQ burst): mesh links, PQ mesh degree per class,
#   negative-score peers by observer class and by scored-peer class, score bands, scoring penalty counters,
#   BadScore mesh churn and failed sends per topic group, and negatives vs the observer's own failed sends.
import glob, json, os, sys
from collections import defaultdict
import numpy as np

sys.path.insert(0, "repo/sim")
import analyze, perturb

run = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
cfg = analyze.read_cfg(run)
nodes, t0, S = cfg["nodes"], cfg["first_slot_s"], cfg["slots"]
sched = cfg.get("sched") or []
has_pq = any(sched)
bg = json.load(open(f"{run}/bg.json")) if os.path.exists(f"{run}/bg.json") else []
lo, hi = 2, S - 1
PER = "--per-slot" in sys.argv  # also print per-slot PQ and BLS miss % by class and negatives by observer client
if "--slots" in sys.argv:
    j = sys.argv.index("--slots")
    lo, hi = int(sys.argv[j + 1]), int(sys.argv[j + 2])
lever = cfg.get("lever", "")
ps = lever.split("--peer-scale")[-1].split()[0] if "--peer-scale" in lever else "1.0"
binary = next((b for b in ("cf", "stale", "fixed") if f"bin/{b}/" in lever), "old")
N = len(nodes)
link = [nd["link"] for nd in nodes]
classes = sorted(set(link))
print(f"== {os.path.basename(run.rstrip('/'))}: {N} hosts, {S} slots, peer-scale {ps}, binary {binary}; "
      f"analysed slots {lo}-{hi}")

off_iv = [nd.get("offline", []) for nd in nodes]
def offline_between(i, a, b):
    return any(x < b and y > a for x, y in off_iv[i])
def rejoin_age(i, a):  # seconds since the host last came back online before time a (None if never offline)
    ys = [y for x, y in off_iv[i] if y <= a]
    return a - max(ys) if ys else None

# ---------- PQ schedule per slot ----------
pqs = []
for s, msgs in enumerate(sched):
    if not msgs:
        pqs.append(None)
        continue
    a = np.array([[m[0], m[1], m[2], m[4]] for m in msgs], dtype=np.int64)
    G = float(os.environ.get("PQ_JOIN_GRACE", "0"))  # optional: publisher joined < G s before publishing = lost to churn
    for k in range(len(a)) if G > 0 else ():
        tp = t0 + 12 * s + a[k, 1] / 1e3
        if any(tp - G < y <= tp for x, y in off_iv[int(a[k, 0])]):
            print(f"  PQ_JOIN_GRACE {G:g} s: slot {s} msg {k} (publisher {a[k, 0]} joined < {G:g} s before publishing) not needed")
            a[k, 2] = -1
    pqs.append(dict(pub=a[:, 0], off=a[:, 1], topic=a[:, 2], dl=a[:, 3], dlmax=int(a[:, 3].max())))
pq_topics = sorted({t for nd in nodes for t in nd["topics"] if t < 100})
NEED_ALL = os.environ.get("PQ_NEED") == "all"  # every subscribed PQ subnet, ignoring a node's "need" (gen_config --backbone-subnets)
my_pq = [[t for t in nd["topics"] if t < 100] if NEED_ALL or "need" not in nd else nd["need"] for nd in nodes]
if any("need" in nd for nd in nodes):
    print(f"  completeness on {'every subscribed PQ subnet (PQ_NEED=all)' if NEED_ALL else 'needed PQ subnets (node field need)'}"
          f"; {sum('need' in nd for nd in nodes)} nodes have a need field")

ns = {}          # (slot, node) -> dict
pair = defaultdict(lambda: [0, 0, 0])  # (slot, class) -> [needed pairs excl. own, missed at dl, missed at dl+1s]
msg_miss = {}    # slot -> array: subscribers missing each message at the deadline
msg_subs = {}    # slot -> array: online subscribers (excl. publisher) of each message
no_report = 0

def do_rx(e):
    global no_report
    s, i = e["slot"], e["node"]
    if s >= len(pqs) or pqs[s] is None:
        return
    P = pqs[s]
    a = t0 + 12 * s
    if offline_between(i, a, a + P["dlmax"] / 1e3):
        ns[(s, i)] = dict(off=True)
        return
    r = np.asarray(e["r"], dtype=np.int64)
    need = np.isin(P["topic"], my_pq[i])
    ok = (r >= 0) & (r <= P["dl"])
    miss = need & ~ok
    complete = not miss.any()
    other = need & (P["pub"] != i)
    m1 = other & ~ok
    m2 = other & ~((r >= 0) & (r <= P["dl"] + 1000))
    c = link[i]
    pc = pair[(s, c)]
    pc[0] += int(other.sum()); pc[1] += int(m1.sum()); pc[2] += int(m2.sum())
    if s not in msg_miss:
        msg_miss[s] = np.zeros(len(r), dtype=np.int64)
        msg_subs[s] = np.zeros(len(r), dtype=np.int64)
    msg_miss[s] += m1
    msg_subs[s] += other
    d = dict(off=False, complete=complete, nmiss=int(miss.sum()))
    if not complete:
        idx = np.nonzero(miss)[0]
        rr = r[idx]
        d["never"] = bool((rr < 0).any())
        d["near"] = bool(((rr >= 0) & (rr <= P["dl"][idx] + 1000)).all())
        whole = []
        for t in my_pq[i]:
            on_t = need & (P["topic"] == t)
            if on_t.any() and not (on_t & ok).any():
                whole.append(t)
        d["whole"] = whole
        d["miss_idx"] = idx
    ns[(s, i)] = d

# ---------- BLS attestations (tracked background messages) ----------
KATT = perturb.KINDS.index("att") if bg else None
rxbg = defaultdict(dict)  # slot -> node -> {k: ms}

# ---------- ticks and mesh snapshots ----------
GROUPS = ["", "bg_block", "bg_agg", "bg_att", "bg_col", "bg_syncc"]
PEN = ["GraftBackoff", "BrokenPromise", "MessageDeficit", "IPColocation"]
def tick_row(e):
    row = [e["t"], e.get("f_forward", 0), e.get("f_timeout", 0), e.get("f_queue_full", 0)]
    row += [e.get(f"scoring_penalties:{p}", 0) for p in PEN]
    for g in GROUPS:
        pre = f"{g}:" if g else ""
        row += [e.get(f"{pre}mesh_peer_churn_events:BadScore", 0), e.get(f"{pre}forward_messages_dropped_per_topic", 0),
                e.get(f"{pre}timedout_messages_dropped_per_topic", 0)]
    return row
COL = {"t": 0, "f_forward": 1, "f_timeout": 2, "f_queue_full": 3}
for k, p in enumerate(PEN):
    COL[p] = 4 + k
for k, g in enumerate(GROUPS):
    COL[f"bad:{g or 'pq'}"] = 8 + 3 * k
    COL[f"qfull:{g or 'pq'}"] = 9 + 3 * k
    COL[f"tout:{g or 'pq'}"] = 10 + 3 * k
ticks = defaultdict(list)
mesh = {}  # (slot, node) -> (conns, mesh dict, score, neg)

for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    for line in open(f):
        if line.startswith('{"ev":"rx",'):
            if has_pq:
                do_rx(json.loads(line))
        elif line.startswith('{"ev":"rxbg"'):
            if bg:
                e = json.loads(line)
                rxbg[e["slot"]][e["node"]] = {k: ms for k, ms in e["r"]}
        elif '"ev":"tick"' in line:
            e = json.loads(line)
            ticks[e["node"]].append(tick_row(e))
        elif '"ev":"mesh"' in line:
            e = json.loads(line)
            mesh[(e["slot"], e["node"])] = (e["conns"], e["mesh"], e.get("score"), e.get("neg") or [])

T = {}
for i, tk in ticks.items():
    tk.sort()
    T[i] = np.array(tk, dtype=np.float64)
def at(i, t, col):  # counter value at time t (last tick <= t)
    a = T.get(i)
    if a is None:
        return 0.0
    j = np.searchsorted(a[:, 0], t + 1e-6) - 1
    return float(a[j, col]) if j >= 0 else 0.0
def delta(i, t1, t2, col):
    return at(i, t2, col) - at(i, t1, col)

cls_n = {c: sum(1 for x in link if x == c) for c in classes}
pct = lambda a, b: round(100 * a / b, 2) if b else None
slots = [s for s in range(lo, hi + 1)]

# ================= Item 1 =================
if has_pq:
    print("\n# Item 1: PQ misses at the 8 s deadline (online node-slots)")
    done_slots = sorted({s for (s, i) in ns})
    print(" node-slot completeness per slot and class (%), all slots:")
    for c in classes:
        row = []
        for s in done_slots:
            v = [d for (ss, i), d in ns.items() if ss == s and link[i] == c and not d["off"]]
            row.append(pct(sum(d["complete"] for d in v), len(v)))
        print(f"  {c:6s}", row)
    allc = []
    for s in done_slots:
        v = [d for (ss, i), d in ns.items() if ss == s and not d["off"]]
        allc.append(pct(sum(d["complete"] for d in v), len(v)))
    print("  all   ", allc)
    passed = all(all((pct(sum(d["complete"] for (ss, i), d in ns.items() if ss == s and link[i] == c and not d["off"]),
                          sum(1 for (ss, i), d in ns.items() if ss == s and link[i] == c and not d["off"])) or 0) >= 99
                     for s in done_slots if s >= 2) for c in classes)
    print(f"  pass rule (every class >= 99 % in every slot from slot 2): {'PASS' if passed else 'FAIL'}")
    worst = {c: min((pct(sum(d['complete'] for (ss, i), d in ns.items() if ss == s and link[i] == c and not d['off']),
                         sum(1 for (ss, i), d in ns.items() if ss == s and link[i] == c and not d['off'])) or 100, s)
                    for s in done_slots if s >= 2) for c in classes}
    print("  worst slot per class (%, slot):", worst)
    print(f"\n slots {lo}-{hi}: per class  node-slots | complete % | PQ msg miss % at 8 s | at 9 s | needed pairs")
    tot = [0, 0, 0, 0, 0]
    for c in classes:
        v = [d for (s, i), d in ns.items() if lo <= s <= hi and link[i] == c and not d["off"]]
        p = [sum(pair[(s, c)][k] for s in slots) for k in range(3)]
        tot = [tot[0] + len(v), tot[1] + sum(d["complete"] for d in v), tot[2] + p[0], tot[3] + p[1], tot[4] + p[2]]
        print(f"  {c:6s} {len(v):7d} | {pct(sum(d['complete'] for d in v), len(v))} | "
              f"{100 * p[1] / max(p[0], 1):.4f} | {100 * p[2] / max(p[0], 1):.4f} | {p[0]}")
    print(f"  all    {tot[0]:7d} | {pct(tot[1], tot[0])} | {100 * tot[3] / max(tot[2], 1):.4f} | "
          f"{100 * tot[4] / max(tot[2], 1):.4f} | {tot[2]}")
    offx = sum(1 for (s, i), d in ns.items() if lo <= s <= hi and d["off"])
    print(f"  offline node-slots left out: {offx}")

    # classification of incomplete node-slots
    inc = {(s, i): d for (s, i), d in ns.items() if lo <= s <= hi and not d["off"] and not d["complete"]}
    per_host = defaultdict(int)
    for (s, i) in inc:
        per_host[i] += 1
    reasons = ["rejoined<=12s", "rejoined12-60s", "whole_subnet", "never", "near_miss(<=1s)", "late(>1s)"]
    cnt = defaultdict(lambda: defaultdict(int))
    miss_by = defaultdict(lambda: defaultdict(int))
    for (s, i), d in inc.items():
        age = rejoin_age(i, t0 + 12 * s)
        if age is not None and age <= 12:
            r_ = reasons[0]
        elif age is not None and age <= 60:
            r_ = reasons[1]
        elif d["whole"]:
            r_ = reasons[2]
        elif d["never"]:
            r_ = reasons[3]
        elif d["near"]:
            r_ = reasons[4]
        else:
            r_ = reasons[5]
        cnt[link[i]][r_] += 1
        miss_by[link[i]][r_] += d["nmiss"]
    print(f"\n incomplete node-slots, slots {lo}-{hi}, by first matching reason: count (missing msgs)")
    for c in classes:
        n = sum(cnt[c].values())
        print(f"  {c:6s} {n:6d}: " + ", ".join(f"{r_} {cnt[c][r_]} ({miss_by[c][r_]})" for r_ in reasons if cnt[c][r_]))
    for c in classes:
        hs = [i for i in per_host if link[i] == c]
        if not hs:
            continue
        n = sum(per_host[i] for i in hs)
        rep = sum(per_host[i] for i in hs if per_host[i] >= 2)
        top = sorted((per_host[i] for i in hs), reverse=True)
        k10 = max(1, len(top) // 10)
        print(f"  {c:6s} repeat hosts: {len(hs)} of {cls_n[c]} hosts incomplete at least once; node-slots on hosts incomplete "
              f">= 2 times {pct(rep, n)} %; top 10 % of these hosts hold {pct(sum(top[:k10]), n)} %; max per host {top[0]} "
              f"of {hi - lo + 1} slots")
    # persistence: share of a slot's incomplete hosts that were also incomplete in the previous slot
    pers = []
    for s in slots[1:]:
        a = {i for (ss, i) in inc if ss == s}
        b = {i for (ss, i) in inc if ss == s - 1}
        pers.append(pct(len(a & b), len(a)))
    print("  share of a slot's incomplete hosts also incomplete in the previous slot (%):", pers)
    # whole subnet: which topics, and the host's mesh on that topic in the snapshot of that slot
    ws = [(s, i, t) for (s, i), d in inc.items() for t in d["whole"]]
    if ws:
        mz = [len(mesh.get((s, i), (None, {}, None, None))[1].get(str(t), [])) for s, i, t in ws]
        print(f"  whole-subnet misses: {len(ws)} (node-slot, topic); mesh size on that topic at 3.95 s: "
              f"0 in {sum(1 for x in mz if x == 0)}, 1-5 in {sum(1 for x in mz if 0 < x < 6)}, >=6 in {sum(1 for x in mz if x >= 6)}")
    # the most often incomplete hosts: attributes, and why their meshes on the missed subnets are small
    subs_pq = defaultdict(set)
    for i in range(N):
        for t in my_pq[i]:
            subs_pq[t].add(i)
    top = sorted(per_host, key=lambda i: -per_host[i])[:12]
    if top:
        print("  most often incomplete hosts: incomplete slots | link client peer_target nat city access | conns | "
              "negative peers | PQ topics with an empty mesh at 3.95 s | on those topics: connected subscribers, "
              "of them negative (means over the host's incomplete slots)")
    for i in top:
        nd = nodes[i]
        ss = [s for (s, j) in inc if j == i]
        cn, ng, z, zs, zn = [], [], [], [], []
        for s in ss:
            m = mesh.get((s, i))
            if not m:
                continue
            conns, mm, sc_, neg = m
            cn.append(len(conns)); ng.append((sc_ or [0, 0, 0, 0])[3])
            negset = {j for j, x in neg}
            empty = [int(t) for t, v in mm.items() if int(t) < 100 and not v]
            z.append(len(empty))
            for t in empty:
                cs = [j for j in conns if j in subs_pq[t]]
                zs.append(len(cs)); zn.append(sum(1 for j in cs if j in negset))
        mean = lambda v: round(float(np.mean(v)), 1) if v else None
        print(f"   host {i}: {per_host[i]} | {nd['link']} {nd.get('client')} {nd.get('peer_target')} nat={nd.get('nat')} "
              f"{nd.get('city')} {nd.get('access')} | {mean(cn)} | {mean(ng)} | {mean(z)} | {mean(zs)}, {mean(zn)}")
    # messages most subscribers missed (publisher-side failures)
    bad_msgs, bad_pairs, all_pairs, zero = 0, 0, 0, 0
    for s in slots:
        if s not in msg_miss:
            continue
        m, n = msg_miss[s], msg_subs[s]
        sel = (n > 0) & (m > 0.5 * n)
        bad_msgs += int(sel.sum()); bad_pairs += int(m[sel].sum()); all_pairs += int(m.sum())
        zero += int(((n > 0) & (m == n)).sum())
        if os.environ.get("PQ_ZERO"):  # debug: the messages that reached no subscriber, and their publisher
            for k in np.nonzero((n > 0) & (m == n))[0]:
                p = pqs[s]; i = int(p["pub"][k]); t = t0 + 12 * s + p["off"][k] / 1000
                print(f"  reached none: slot {s} msg {k} of {len(m)}/{len(p['pub'])}, publisher {i} ({link[i]}, "
                      f"{nodes[i].get('client')}, {nodes[i].get('city')}) at {t:.3f} s, topic {p['topic'][k]}; "
                      f"publisher offline near: {[(x, y) for x, y in off_iv[i] if y > t - 30 and x < t + 30]}")
    nmsg = sum(len(msg_miss[s]) for s in slots if s in msg_miss)
    print(f"  messages missed by > 50 % of their online subscribers: {bad_msgs} of {nmsg} ({zero} reached none); "
          f"they account for {pct(bad_pairs, all_pairs)} % of missed (node, message) pairs")

if PER:
    print(f"\n per slot {lo}-{hi}: PQ msg miss % at 8 s by class")
    for c in classes:
        print(f"  {c:6s}", [round(100 * pair[(s, c)][1] / pair[(s, c)][0], 4) if pair[(s, c)][0] else None for s in slots])

# ================= BLS attestation baseline =================
if bg:
    natt = lambda nd: sum(1 for t in nd["topics"] if 200 <= t < 300)
    typ = lambda nd: "all64" if natt(nd) == 64 else f"{natt(nd)}sub"
    subs = defaultdict(list)
    for i, nd in enumerate(nodes):
        for t in nd["topics"]:
            subs[t].append(i)
    tot, m8, mnev = defaultdict(int), defaultdict(int), defaultdict(int)
    tots, m8s = defaultdict(int), defaultdict(int)  # (slot, class) -> deliveries, missing at 8 s (--per-slot)
    for s, msgs in enumerate(bg):
        if not (lo <= s <= hi):
            continue
        a = t0 + 12 * s
        for k, m in enumerate(msgs):
            if m[4] != KATT or not m[5]:
                continue
            for i in subs[m[2]]:
                if i == m[0] or offline_between(i, a, a + 12):
                    continue
                key = (link[i], typ(nodes[i]))
                tot[key] += 1; tots[(s, link[i])] += 1
                ms = rxbg[s].get(i, {}).get(k)
                if ms is None:
                    mnev[key] += 1; m8[key] += 1; m8s[(s, link[i])] += 1
                elif ms > 8000:
                    m8[key] += 1; m8s[(s, link[i])] += 1
    print(f"\n# BLS attestation miss rate (tracked attestations, slots {lo}-{hi}): missing at 8 s / never, % of deliveries")
    for c in classes:
        b = sum(v for k, v in tot.items() if k[0] == c)
        if b:
            parts = [f"{k[1]} {100 * m8[k] / tot[k]:.3f} / {100 * mnev[k] / tot[k]:.3f} (n={tot[k]})" for k in sorted(tot) if k[0] == c]
            print(f"  {c:6s} {100 * sum(v for k, v in m8.items() if k[0] == c) / b:.3f} / "
                  f"{100 * sum(v for k, v in mnev.items() if k[0] == c) / b:.3f} % of {b};  " + "; ".join(parts))
    if PER:
        print("  per slot, missing at 8 s (% of deliveries) by class:")
        for c in classes:
            print(f"   {c:6s}", [round(100 * m8s[(s, c)] / tots[(s, c)], 3) if tots[(s, c)] else None for s in range(lo, hi + 1)])

# ================= Item 2 =================
print("\n# Item 2: per slot (mesh snapshot at 3.95 s into the slot)")
msl = sorted({s for (s, i) in mesh})
rows = defaultdict(list)
neg_by_obs = defaultdict(list)
neg_by_peer = defaultdict(list)
neg_by_cli = defaultdict(list)
bands = []
corr = defaultdict(lambda: [0, 0])  # bin of observer's failed sends in the previous 12 s -> [observers, negatives]
BINS = [(0, 0), (1, 99), (100, 999), (1000, 4999), (5000, 10 ** 9)]
for s in msl:
    es = {i: v for (ss, i), v in mesh.items() if ss == s}
    tl = sum(len(x) for v in es.values() for x in v[1].values())
    rows["mesh links"].append(tl)
    rows["links/node"].append(round(tl / max(len(es), 1), 1))
    rows["conns/node"].append(round(sum(len(v[0]) for v in es.values()) / max(len(es), 1), 1))
    for c in classes:
        deg = [len(x) for i, v in es.items() if link[i] == c for t, x in v[1].items() if int(t) < 100]
        rows[f"PQ mesh {c}"].append(round(float(np.mean(deg)), 2) if deg else None)
        rows[f"PQ mesh<6 {c} %"].append(pct(sum(1 for x in deg if x < 6), len(deg)))
        rows[f"PQ mesh=0 {c} %"].append(pct(sum(1 for x in deg if x == 0), len(deg)))
    negs = [(i, j, sc) for i, v in es.items() for j, sc in v[3] if j is not None]
    rows["neg peers"].append(sum((v[2] or [0, 0, 0, 0])[3] for v in es.values()))
    for c in classes:
        obs = [i for i in es if link[i] == c]
        neg_by_obs[c].append(round(sum((es[i][2] or [0, 0, 0, 0])[3] for i in obs) / max(len(obs), 1), 1))
        conn_c = sum(1 for v in es.values() for j in v[0] if link[j] == c)
        neg_by_peer[c].append(pct(sum(1 for i, j, sc in negs if link[j] == c), conn_c))
    for cl in sorted({nd["client"] for nd in nodes}):
        obs = [i for i in es if nodes[i]["client"] == cl]
        neg_by_cli[cl].append(round(sum((es[i][2] or [0, 0, 0, 0])[3] for i in obs) / max(len(obs), 1), 1))
    sc = np.array([x[2] for x in negs]) if negs else np.zeros(0)
    bands.append([int(((sc < 0) & (sc >= -1)).sum()), int(((sc < -1) & (sc >= -10)).sum()),
                  int(((sc < -10) & (sc >= -100)).sum()), int(((sc < -100) & (sc >= -1000)).sum()), int((sc < -1000).sum())])
    a = t0 + 12 * s + 3.95
    for i, v in es.items():
        fs = delta(i, a - 12, a, COL["f_timeout"]) + delta(i, a - 12, a, COL["f_queue_full"])
        for b, (x, y) in enumerate(BINS):
            if x <= fs <= y:
                corr[b][0] += 1; corr[b][1] += (v[2] or [0, 0, 0, 0])[3]
                break
for k, v in rows.items():
    print(f"  {k:18s}", v)
print("  negative-score peers per observer, by observer class:")
for c in classes:
    print(f"   {c:6s}", neg_by_obs[c])
if PER:
    print("  negative-score peers per observer, by observer client:")
    for cl in sorted(neg_by_cli):
        print(f"   {cl:10s}", neg_by_cli[cl])
print("  % of connections to peers of a class that are negative, by scored-peer class:")
for c in classes:
    print(f"   {c:6s}", neg_by_peer[c])
print("  negative scores by band per slot [(-1,0), [-10,-1), [-100,-10), [-1000,-100), < -1000]:")
print("  ", bands)
print("  negatives per observer vs the observer's own failed sends (timeouts + queue full) in the 12 s before the snapshot:")
for b, (x, y) in enumerate(BINS):
    if corr[b][0]:
        print(f"   {x}-{y if y < 10 ** 9 else 'inf'} failed: {corr[b][0]} observer-slots, mean negatives {corr[b][1] / corr[b][0]:.1f}")

# per slot counter deltas summed over nodes (slot window [start, start + 12 s))
print("  per slot, summed over hosts (counter deltas over the slot):")
for key in ["GraftBackoff", "BrokenPromise", "MessageDeficit", "IPColocation"]:
    print(f"   penalty {key:15s}", [round(sum(delta(i, t0 + 12 * s, t0 + 12 * s + 12, COL[key]) for i in T)) for s in msl])
for g in GROUPS:
    gg = g or "pq"
    print(f"   {gg:9s} BadScore churn", [round(sum(delta(i, t0 + 12 * s, t0 + 12 * s + 12, COL[f'bad:{gg}']) for i in T)) for s in msl])
# libp2p-gossipsub counts per topic only the messages dropped after their queue timeout (forward 1 s, publish 5 s):
# forward_messages_dropped_per_topic = forwards, timedout_messages_dropped_per_topic = forwards + publishes.
# Messages refused by a full queue (f_queue_full) are not split by topic.
print("   messages dropped after the queue timeout, thousands, summed over hosts (forwards / publishes):")
for g in GROUPS:
    gg = g or "pq"
    q = [round(sum(delta(i, t0 + 12 * s, t0 + 12 * s + 12, COL[f'qfull:{gg}']) for i in T) / 1e3, 1) for s in msl]
    t_ = [round(sum(delta(i, t0 + 12 * s, t0 + 12 * s + 12, COL[f'tout:{gg}']) for i in T) / 1e3, 1) for s in msl]
    if any(q) or any(t_):
        print(f"   {gg:9s}", [(a, round(b - a, 1)) for a, b in zip(q, t_)])
for c in classes:
    hs = [i for i in T if link[i] == c]
    print(f"   failed sends per host ({c}): timed out / queue full",
          [(round(np.mean([delta(i, t0 + 12 * s, t0 + 12 * s + 12, COL['f_timeout']) for i in hs])),
            round(np.mean([delta(i, t0 + 12 * s, t0 + 12 * s + 12, COL['f_queue_full']) for i in hs]))) for s in msl])
