# Stale copies (older than max_msg_age, 60 s: gossipsub's 60 s duplicate cache no longer filters them, wbsim ignores
# them) per 1 Gbit node, per slot and per 10-slot block, and whether they land on the hosts that miss PQ messages;
# usage: python3 -I .amp-out/stalehosts.py RUN [STEP_SLOT (default 33)]
# Per online node-slot (pqdiag's rule: online from the slot start to the last deadline): stale = tick-counter delta
# (stale_pq, stale_bg) over the slot (0-12 s); incomplete = a needed PQ message (own left out) not held by its deadline.
import glob, json, re, sys
import numpy as np
sys.path.insert(0, "repo/sim"); import analyze

run = "runs/" + sys.argv[1]
step = int(sys.argv[2]) if len(sys.argv) > 2 else 33
cfg = analyze.read_cfg(run)
nodes, t0, S = cfg["nodes"], cfg["first_slot_s"], cfg["slots"]
n = len(nodes)
link = np.array([nd["link"] for nd in nodes])
off_iv = [nd.get("offline", []) for nd in nodes]
my_pq = [[t for t in nd["topics"] if t < 100] for nd in nodes]
pqs = {}
for s, msgs in enumerate(cfg["sched"]):
    if msgs:
        a = np.array([[m[0], m[1], m[2], m[4]] for m in msgs], dtype=np.int64)
        pqs[s] = dict(pub=a[:, 0], topic=a[:, 2], dl=a[:, 3], dlmax=int(a[:, 3].max()))
KEYS = ("t", "stale_pq", "stale_bg")
RE = {k: re.compile(r'"%s":([0-9.]+)' % k) for k in KEYS + ("node",)}
stale = np.full((n, S, 2), np.nan)  # per node-slot: PQ, background
inc = np.full((n, S), np.nan)       # 1 incomplete, 0 complete, nan offline
for f in glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"):
    ticks, rx, node = [], {}, None
    for line in open(f):
        if line.startswith('{"ev":"rx",'):
            e = json.loads(line)
            node = e["node"]
            if e["slot"] in pqs:
                rx[e["slot"]] = np.asarray(e["r"], dtype=np.int64)
        elif '"ev":"tick"' in line:
            row = []
            for k in KEYS:
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
    i = node
    for s, P in pqs.items():
        a = t0 + 12 * s
        if any(x < a + P["dlmax"] / 1e3 and y > a for x, y in off_iv[i]):
            continue
        stale[i, s] = at(a + 12) - at(a)
        r = rx.get(s)
        if r is not None:
            need = np.isin(P["topic"], my_pq[i]) & (P["pub"] != i)
            inc[i, s] = float((need & ~((r >= 0) & (r <= P["dl"]))).any())

cl = np.flatnonzero(link == "cloud")
print(f"== {sys.argv[1]}: {n} hosts, {len(cl)} 1 Gbit; stale = copies older than 60 s, per online node-slot, whole slot")
print("per slot: 1 Gbit complete % (incomplete hosts) | stale PQ / background per 1 Gbit node | home stale PQ / bg per node")
home = np.flatnonzero(link != "cloud")
for s in range(2, S):
    c = inc[cl, s]
    print(f"  slot {s:2d}: {100 * (1 - np.nanmean(c)):.2f} ({int(np.nansum(c))}) | {np.nanmean(stale[cl, s, 0]):.2f} / "
          f"{np.nanmean(stale[cl, s, 1]):.1f} | {np.nanmean(stale[home, s, 0]):.2f} / {np.nanmean(stale[home, s, 1]):.1f}")
print("per 10-slot block: stale PQ / bg per 1 Gbit node per slot; incomplete 1 Gbit node-slots")
for a, b in [(2, 9), (10, 19), (20, 29), (30, 39), (40, S - 1)]:
    sl = slice(a, b + 1)
    print(f"  {a}-{b}: {np.nanmean(stale[cl, sl, 0]):.2f} / {np.nanmean(stale[cl, sl, 1]):.1f}; {int(np.nansum(inc[cl, sl]))}")
A, B = slice(step, S), slice(2, step)
incA, incB = np.nansum(inc[cl, A], axis=1), np.nansum(inc[cl, B], axis=1)
stA, stB = np.nansum(stale[cl, A, 0], axis=1), np.nansum(stale[cl, B, 0], axis=1)
bgA, bgB = np.nansum(stale[cl, A, 1], axis=1), np.nansum(stale[cl, B, 1], axis=1)
nA, nB = np.sum(~np.isnan(stale[cl, A, 0]), axis=1), np.sum(~np.isnan(stale[cl, B, 0]), axis=1)
miss = incA > 0
print(f"hosts incomplete at least once in slots {step}-{S - 1}: {miss.sum()} of {len(cl)} 1 Gbit hosts "
      f"({100 * miss.mean():.1f} %), holding {int(incA[miss].sum())} incomplete node-slots")
for lab, x, nn in (("PQ", (stA, stB), (nA, nB)), ("background", (bgA, bgB), (nA, nB))):
    xa, xb = x
    print(f"  stale {lab}: share on those hosts, slots {step}-{S - 1} {100 * xa[miss].sum() / max(xa.sum(), 1):.1f} %, "
          f"slots 2-{step - 1} {100 * xb[miss].sum() / max(xb.sum(), 1):.1f} %; per node per slot on them / on the others: "
          f"{xa[miss].sum() / max(nn[0][miss].sum(), 1):.2f} / {xa[~miss].sum() / max(nn[0][~miss].sum(), 1):.2f} "
          f"(slots 2-{step - 1}: {xb[miss].sum() / max(nn[1][miss].sum(), 1):.2f} / {xb[~miss].sum() / max(nn[1][~miss].sum(), 1):.2f})")


def ranks(x):
    o = np.argsort(x, kind="stable")
    r = np.empty(len(x))
    r[o] = np.arange(len(x))
    for v in np.unique(x):
        k = x == v
        r[k] = r[k].mean()
    return r


rho = np.corrcoef(ranks(stA), ranks(incA))[0, 1]
print(f"  Spearman, per 1 Gbit host, stale PQ vs incomplete node-slots in slots {step}-{S - 1}: {rho:.2f}; "
      f"background stale vs incomplete: {np.corrcoef(ranks(bgA), ranks(incA))[0, 1]:.2f}")
# node-slot level, slots step..S-1: incomplete rate with and without stale copies in the same or the previous slot
ss = []
for s in range(step, S):
    for j, i in enumerate(cl):
        if np.isnan(inc[i, s]) or np.isnan(stale[i, s, 0]):
            continue
        prev = stale[i, s - 1, 0] if not np.isnan(stale[i, s - 1, 0]) else 0
        ss.append((inc[i, s], stale[i, s, 0] + prev > 0, stale[i, s, 1] + (stale[i, s - 1, 1] if not np.isnan(stale[i, s - 1, 1]) else 0) > 0))
ss = np.array(ss)
for k, lab in ((1, "PQ"), (2, "background")):
    w = ss[:, k] > 0
    print(f"  node-slots {step}-{S - 1} with stale {lab} copies in the same or previous slot: {w.mean() * 100:.1f} %; incomplete "
          f"rate with / without: {100 * ss[w, 0].mean():.2f} / {100 * ss[~w, 0].mean():.2f} %; "
          f"share of incomplete node-slots that have them: {100 * ss[w, 0].sum() / max(ss[:, 0].sum(), 1):.0f} %")
top = np.argsort(-(incA + incB))[:10]
print(f"most often incomplete 1 Gbit hosts: host client city | incomplete 2-{step - 1} / {step}-{S - 1} | stale PQ per slot 2-{step - 1} / "
      f"{step}-{S - 1} | stale bg per slot")
for j in top:
    if incA[j] + incB[j] == 0:
        break
    nd = nodes[cl[j]]
    print(f"  {cl[j]:5d} {nd.get('client')} {nd.get('city')} | {int(incB[j])} / {int(incA[j])} | {stB[j] / max(nB[j], 1):.2f} / "
          f"{stA[j] / max(nA[j], 1):.2f} | {bgB[j] / max(nB[j], 1):.1f} / {bgA[j] / max(nA[j], 1):.1f}")
top = np.argsort(-stA)[:8]
print(f"1 Gbit hosts with the most stale PQ copies in slots {step}-{S - 1}: host client city | stale PQ per slot | incomplete 2-{step - 1} / {step}-{S - 1}")
for j in top:
    nd = nodes[cl[j]]
    print(f"  {cl[j]:5d} {nd.get('client')} {nd.get('city')} | {stA[j] / max(nA[j], 1):.2f} | {int(incB[j])} / {int(incA[j])}")
# A copy held up by a loss arrives one retransmission timeout later, so a stale copy (> 60 s) arrives 64 or 120 s, i.e.
# 5-10 slots, after the stall began. Lagged test: for each 1 Gbit node-slot s, does the host get stale PQ copies in
# slots s+5 .. s+11 (cut at the last slot)? Compared between incomplete and complete node-slots.
L0, L1 = 5, 11


def lagged(a, b, hosts):
    r = []
    for s in range(a, b + 1):
        if s + L0 > S - 1:
            continue
        for i in hosts:
            if np.isnan(inc[i, s]):
                continue
            r.append((inc[i, s] > 0, np.nansum(stale[i, s + L0:min(s + L1, S - 1) + 1, 0]) > 0))
    r = np.array(r, dtype=bool).reshape(-1, 2)
    m = r[:, 0]
    pct = lambda x: 100 * x.mean() if len(x) else float("nan")
    return int(m.sum()), int((~m).sum()), int(r[m, 1].sum()), pct(r[m, 1]), pct(r[~m, 1])


missers = cl[miss]
top1 = cl[np.argmax(incA)]
for lab, a, b, hosts in ((f"slots {step}-{S - 1 - L0}, all 1 Gbit hosts", step, S - 1, cl),
                         (f"slots {step}-{S - 1 - L0}, without host {top1}", step, S - 1, cl[cl != top1]),
                         (f"slots {step}-{S - 1 - L0}, the {len(missers)} hosts that miss in slots {step}-{S - 1}", step, S - 1, missers),
                         (f"same, without host {top1}", step, S - 1, missers[missers != top1]),
                         (f"slots 2-{step - 1}, all 1 Gbit hosts", 2, step - 1, cl),
                         (f"slots 2-{step - 1}, without host {top1}", 2, step - 1, cl[cl != top1])):
    ni, nc, k, pi, pc = lagged(a, b, hosts)
    print(f"  lagged ({lab}): incomplete node-slots {ni}, of them with stale PQ copies {L0}-{L1} slots later {k} ({pi:.0f} %); "
          f"complete node-slots {nc}: {pc:.1f} %")
print(f"per-slot stale PQ copies, slots 2-{S - 1}, of the hosts that miss in slots {step}-{S - 1} (x = incomplete, - = offline):")
for j in np.argsort(-incA, kind="stable"):
    if incA[j] == 0:
        break
    h = cl[j]
    nd = nodes[h]
    print(f"  {h} {nd.get('client')} {nd.get('city')}: " + " ".join(
        f"{s}:" + ("-" if np.isnan(inc[h, s]) else f"{stale[h, s, 0]:.0f}" + ("x" if inc[h, s] else "")) for s in range(2, S)))
