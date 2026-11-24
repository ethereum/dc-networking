#!/usr/bin/env python3
"""PQ Gasper one-subnet study (Nov 17): one PQ subnet carrying 1,600 signatures per slot (2,404 B each, bundles of up
to 16 per publisher), which every node joins and needs. Per link class and slot: node-slots holding every signature of
the slot by 8.0 s, signatures and messages missing at 8 s and 9 s, completion times, signatures held over the slot,
late first deliveries (8-16 s), upload and download in 4-8 s and 4-5 s, dropped PQ forwards, PQ mesh makeup.
usage: python3 -I .amp-out/pq1600.py RUN [--slots A B] [--per-slot]
Rules (as pqdiag.py): a node-slot counts if the host is online from slot start to the deadline; a node's own signatures
are left out of the miss counts; the pass rule is >= 99 % of each class complete in every slot from slot 2, with late
first deliveries flat."""
import glob, json, os, re, sys
from collections import defaultdict
from multiprocessing import Pool
import numpy as np

sys.path.insert(0, "repo/sim")
import analyze  # noqa: E402

run = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
cfg = analyze.read_cfg(run)
nodes, t0, S, SL = cfg["nodes"], cfg["first_slot_s"], cfg["slots"], cfg["slot_s"]
sched = cfg["sched"]
N = len(nodes)
lo, hi = 2, S - 1
if "--slots" in sys.argv:
    j = sys.argv.index("--slots")
    lo, hi = int(sys.argv[j + 1]), int(sys.argv[j + 2])
PER = "--per-slot" in sys.argv
# non-forwarding leaves (--freeride-share) are their own classes, e.g. "50x25-leaf"
# SPLITCPU=1: home hosts with a slow CPU (verification x3) are their own classes, e.g. "50x25-slowcpu"
link = [nd["link"] + ("-leaf" if nd.get("freeride") else "")
        + ("-slowcpu" if os.environ.get("SPLITCPU") and nd.get("cpu") else "")
        # SPLIT=<node field> (access, nat, city): home classes split by that field, e.g. "50x15-access=dsl"
        + (f'-{os.environ["SPLIT"]}={nd.get(os.environ["SPLIT"])}' if os.environ.get("SPLIT") and nd["link"] != "cloud" else "")
        for nd in nodes]
CL = [c for c in ("50x15", "50x25", "cloud") if c in link] + sorted(set(link) - {"50x15", "50x25", "cloud"})
NAME = {"50x15": "50/15", "50x25": "50/25", "cloud": "1 Gbit"}
off_iv = [nd.get("offline", []) for nd in nodes]
my_pq = [[t for t in nd["topics"] if t < 100] for nd in nodes]


def cap(s):
    v, u = s.split()
    return float(v) * {"Kbit": 1e3, "Mbit": 1e6, "Gbit": 1e9}[u]


UP = np.array([cap(nd["up"]) for nd in nodes])
HOMEPUB = np.array([nd["link"] != "cloud" for nd in nodes])  # publisher on a home link (50/25; 50/15 hosts have no validators)
DOWN = np.array([cap(nd["down"]) for nd in nodes])
P = {}
for s, msgs in enumerate(sched):
    if msgs:
        a = np.array([[m[0], m[1], m[2], m[4], m[5]] for m in msgs], dtype=np.int64)
        P[s] = dict(pub=a[:, 0], off=a[:, 1], topic=a[:, 2], dl=a[:, 3], sigs=a[:, 4], dlmax=int(a[:, 3].max()))
KEYS = ["t", "tx", "rx", "topic_msg_sent_bytes", "topic_msg_recv_bytes", "forward_messages_dropped_per_topic",
        "timedout_messages_dropped_per_topic", "f_timeout", "f_queue_full", "topic_iwant_msgs",
        "topic_msg_recv_counts_unfiltered", "topic_msg_sent_counts"]
RE = {k: re.compile(r'[{,]"%s":([0-9.]+)' % k) for k in KEYS}
NODE_RE = re.compile(r'"node":(\d+)')
HOLD_AT = [5000, 6000, 7000, 8000, 9000, 10000, 12000]


def offline_between(i, a, b):
    return any(x < b and y > a for x, y in off_iv[i])


def one(f):
    """Per node file: rx vectors per slot, tick counters, PQ mesh at 3.95 s."""
    rx, ticks, mesh, node = {}, [], {}, None
    for line in open(f):
        if line.startswith('{"ev":"rx",'):
            e = json.loads(line)
            node = e["node"]
            rx[e["slot"]] = np.asarray(e["r"], dtype=np.int64)
        elif '"ev":"tick"' in line:
            row = []
            for k in KEYS:
                m = RE[k].search(line)
                row.append(float(m.group(1)) if m else 0.0)
            ticks.append(row)
            if node is None:
                node = int(NODE_RE.search(line).group(1))
        elif '"ev":"mesh"' in line:
            e = json.loads(line)
            node = e["node"]
            mesh[e["slot"]] = [int(x) for x in e["mesh"].get("1", [])]
    return node, rx, np.array(sorted(ticks)) if ticks else None, mesh


def per_node(args):
    node, rx, T, mesh = one(args)
    if node is None:
        return None
    i = node
    out = []
    for s, p in P.items():
        a = t0 + SL * s
        if offline_between(i, a, a + p["dlmax"] / 1e3):
            continue
        r = rx.get(s)
        d = dict(s=s)
        if r is not None and len(r) == len(p["pub"]):
            need = np.isin(p["topic"], my_pq[i]) & (p["pub"] != i)
            ok = (r >= 0) & (r <= p["dl"])
            ok1 = (r >= 0) & (r <= p["dl"] + 1000)
            d["need_m"], d["need_s"] = int(need.sum()), int(p["sigs"][need].sum())
            d["miss_m"], d["miss_s"] = int((need & ~ok).sum()), int(p["sigs"][need & ~ok].sum())
            d["miss_m1"], d["miss_s1"] = int((need & ~ok1).sum()), int(p["sigs"][need & ~ok1].sum())
            hp = need & HOMEPUB[p["pub"]]
            d["need_sh"], d["miss_sh"] = int(p["sigs"][hp].sum()), int(p["sigs"][hp & ~ok].sum())
            d["late"] = int((need & (r > p["dl"]) & (r <= 16000)).sum())
            d["late_s"] = int(p["sigs"][need & (r > p["dl"]) & (r <= 16000)].sum())
            d["never"] = int((need & (r < 0)).sum())
            rr = np.where(r < 0, 10 ** 9, r)
            d["done"] = int(rr[need].max()) if need.any() else 0  # ms after slot start when the last needed one arrived
            d["held"] = [int(p["sigs"][need & (rr <= h)].sum()) for h in HOLD_AT]
            lat = (r - p["off"])[need & (r >= 0)]
            d["lat"] = lat
        if T is not None:
            def at(t):
                j = np.searchsorted(T[:, 0], t + 0.05) - 1
                return T[j, 1:] if j >= 0 and abs(T[j, 0] - t) <= 0.05 else None
            off = cfg["vote_offset_s"]
            x4, x5, x8, x16 = at(a + off), at(a + off + 1.0), at(a + off + 4.0), at(a + 16.0)
            if x4 is not None and x8 is not None and (x8 >= x4).all():
                dd = x8 - x4
                d["up48"] = dd[0] * 8 / 4.0 / UP[i]
                d["down48"] = dd[1] * 8 / 4.0 / DOWN[i]
                d["pqdown48"] = dd[3] * 8 / 4.0 / DOWN[i]
                d["othdown48"] = (dd[1] - dd[3]) / 1e3  # kB received in 4-8 s besides PQ messages
                if dd[9] > 0:
                    d["pqcopyb"] = dd[3] / dd[9]  # PQ bytes per received copy (all copies, duplicates too)
                if x5 is not None and (x5 >= x4).all():
                    d["up45"] = (x5 - x4)[0] * 8 / 1.0 / UP[i]
                    d["down45"] = (x5 - x4)[1] * 8 / 1.0 / DOWN[i]
                if x16 is not None and (x16 >= x4).all():
                    e = x16 - x4
                    d["fq"], d["fto"] = e[4], e[5]  # PQ forwards dropped (queue full), timed out (1 s)
                    d["ftot_to"], d["ftot_qf"] = e[6], e[7]
                    d["iwant"] = e[8]
                    d["copies"] = e[9]
                    d["sentq"] = e[10]  # PQ messages queued for sending (publish + forward), incl. later dropped
        m = mesh.get(s)
        if m is not None:
            d["mdeg"] = len(m)
            d["mfast"] = sum(1 for j in m if nodes[j]["link"] == "cloud") / len(m) if m else np.nan
        out.append(d)
    return i, out


files = glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout")
with Pool(int(os.environ.get("POOL", "12"))) as pool:
    res = [x for x in pool.map(per_node, files, chunksize=8) if x]

rows = defaultdict(list)  # (slot, class) -> per-node dicts
for i, out in res:
    for d in out:
        rows[(d["s"], link[i])].append((i, d))
# slots with receive reports (a run stopped early has none for the slots after the stop)
done_slots = sorted({s for s, c in rows if any("need_s" in d for _, d in rows[(s, c)])})
slots = [s for s in done_slots if lo <= s <= hi]
name = os.path.basename(run.rstrip("/"))
print(f"== {name}: {N} hosts ({', '.join(f'{NAME.get(c, c)} {link.count(c)}' for c in CL)}), {S} slots, "
      f"analysed slots {slots[0]}-{slots[-1]}" + (f" (receive reports end at slot {done_slots[-1]})" if done_slots[-1] < S - 1 else ""))
sig = [int(sum(m[5] for m in sched[s])) for s in range(len(sched))]
print(f"   {cfg.get('msgs', max(sig)):,} signatures per subnet per slot ({cfg['msg_bytes']} B each, bundles of up to 16: "
      f"{np.mean([len(sched[s]) for s in range(len(sched))]):.1f} messages per slot); published per slot "
      f"min {min(sig)} max {max(sig)} (the rest lost to churn); every node needs every signature of the slot by 8.0 s")


def comp(s, c):
    v = [d for _, d in rows.get((s, c), []) if "need_s" in d]
    return (100 * sum(d["miss_m"] == 0 for d in v) / len(v), len(v), sum(d["miss_m"] > 0 for d in v)) if v else (None, 0, 0)


print("\n# Node-slots complete at 8.0 s (% of online node-slots), per slot:")
for c in CL:
    print(f"  {NAME.get(c, c):7s}", " ".join("  -  " if comp(s, c)[0] is None else f"{comp(s, c)[0]:5.1f}"
                                          for s in done_slots))
verdict = {}
for c in CL:
    v = [comp(s, c) for s in done_slots if lo <= s <= hi]
    v = [x for x in v if x[0] is not None]
    worst = min(v, key=lambda x: x[0]) if v else (None, 0, 0)
    verdict[c] = (all(x[0] >= 99 for x in v), worst)
print(f"  pass rule (>= 99 % in every slot from {lo}, slots {slots[0]}-{slots[-1]}): " +
      "; ".join(f"{NAME.get(c, c)} {'PASS' if verdict[c][0] else 'FAIL'} (worst {verdict[c][1][0]:.2f} %, "
                f"{verdict[c][1][2]} of {verdict[c][1][1]})" for c in CL if verdict[c][1][0] is not None))


def agg(c, key, ss=None):
    ss = ss or slots
    return [d.get(key) for s in ss for _, d in rows.get((s, c), []) if d.get(key) is not None]


print(f"\n# Per class, slots {slots[0]}-{slots[-1]} (means over online node-slots unless noted)")
for c in CL:
    v = [d for s in slots for _, d in rows.get((s, c), []) if "need_s" in d]
    if not v:
        continue
    ns_, nm = sum(d["need_s"] for d in v), sum(d["need_m"] for d in v)
    ms, mm = sum(d["miss_s"] for d in v), sum(d["miss_m"] for d in v)
    ms1, mm1 = sum(d["miss_s1"] for d in v), sum(d["miss_m1"] for d in v)
    inc = [d for d in v if d["miss_m"] > 0]
    held8 = np.array([d["held"][HOLD_AT.index(8000)] / d["need_s"] for d in v if d["need_s"]])
    held = np.array([[h / d["need_s"] for h in d["held"]] for d in v if d["need_s"]])
    done = np.array([d["done"] for d in v]) / 1e3
    lat = np.concatenate([d["lat"] for d in v if len(d.get("lat", []))]) / 1e3
    print(f"  {NAME.get(c, c)} ({link.count(c)} hosts): complete {100 * (1 - len(inc) / len(v)):.2f} % of {len(v)} "
          f"node-slots; signatures missing at 8 s {100 * ms / ns_:.3f} % ({ms / len(v):.1f} per node-slot of "
          f"{ns_ / len(v):.0f}), at 9 s {100 * ms1 / ns_:.3f} %; messages missing {100 * mm / nm:.3f} % / {100 * mm1 / nm:.3f} %")
    nsh, msh = sum(d.get("need_sh", 0) for d in v), sum(d.get("miss_sh", 0) for d in v)
    print(f"    signatures missing at 8 s by publisher link: from 1 Gbit publishers {100 * (ms - msh) / max(1, ns_ - nsh):.3f} % "
          f"({(ms - msh) / len(v):.1f} per node-slot of {(ns_ - nsh) / len(v):.0f}), from home publishers "
          f"{100 * msh / max(1, nsh):.3f} % ({msh / len(v):.1f} of {nsh / len(v):.0f})")
    print(f"    signatures held (% of needed, mean over node-slots) at {', '.join(f'{h / 1e3:g}' for h in HOLD_AT)} s: "
          + ", ".join(f"{100 * x:.1f}" for x in held.mean(axis=0)))
    if inc:
        hi8 = np.array([d["held"][HOLD_AT.index(8000)] / d["need_s"] for d in inc])
        print(f"    incomplete node-slots hold p10/p50/p90 {', '.join(f'{100 * np.percentile(hi8, q):.1f}' for q in (10, 50, 90))} "
              f"% of the signatures at 8 s; never delivered (by slot end + drain) in {sum(d['never'] > 0 for d in inc)}")
    fin = done[np.isfinite(done) & (done < 1e5)]
    print(f"    slot time when the last needed signature arrived p50/p90/p99 "
          f"{', '.join(f'{np.percentile(fin, q):.2f}' for q in (50, 90, 99))} s (node-slots that got all by "
          f"{(cfg['slot_s'] + cfg['drain_s']):g} s: {len(fin)} of {len(v)}); first-delivery latency from publish "
          f"p50/p99 {np.percentile(lat, 50):.2f} / {np.percentile(lat, 99):.2f} s")
    lt = [np.mean([d["late"] for _, d in rows.get((s, c), []) if "late" in d] or [0]) for s in slots]
    h = len(lt) // 2
    print(f"    late first deliveries (needed messages first received 8-16 s) per node-slot: mean {np.mean(lt):.2f}, "
          f"max slot {max(lt):.2f}; first half {np.mean(lt[:h]) if h else 0:.2f} vs second half {np.mean(lt[h:]):.2f}")
    up48, up45, dn48, dn45 = (np.array(agg(c, k)) for k in ("up48", "up45", "down48", "down45"))
    byn = defaultdict(list)
    for s in slots:
        for i, d in rows.get((s, c), []):
            if "up48" in d:
                byn[i].append(d["up48"])
    busiest = max((np.mean(x), i) for i, x in byn.items()) if byn else (np.nan, -1)
    if len(up48):
        print(f"    upload handed to TCP, % of the uplink (> 100 = socket buffers filling): 4-8 s mean {100 * up48.mean():.1f}, busiest node "
              f"{100 * busiest[0]:.1f} (n{busiest[1]}), node-slots >= 90 % {100 * (up48 >= 0.9).mean():.1f} %; "
              f"4-5 s mean {100 * up45.mean():.1f}, node-slots >= 90 % {100 * (up45 >= 0.9).mean():.1f} %")
        print(f"    download % of cap: 4-8 s mean {100 * dn48.mean():.1f}, 4-5 s mean {100 * dn45.mean():.1f}, "
              f"node-slots >= 90 % in 4-5 s {100 * (dn45 >= 0.9).mean():.1f} %")
        od, pb = np.array(agg(c, "othdown48")), np.array(agg(c, "pqcopyb"))
        if len(od):
            print(f"    received in 4-8 s besides PQ messages (control, background, framing): {od.mean():.0f} kB per "
                  f"node-slot; PQ bytes per received copy {pb.mean() if len(pb) else float('nan'):.0f}")
    fto, cp, iw, sq = (np.array(agg(c, k)) for k in ("fto", "copies", "iwant", "sentq"))
    if len(fto):
        print(f"    PQ sends queued per node-slot (4-16 s) {sq.mean():.0f}, of which dropped after 1 s in the queue {fto.mean():.0f} "
              f"({100 * fto.sum() / max(sq.sum(), 1):.0f} %); "
              f"PQ copies received {cp.mean():.0f} per node-slot ({cp.mean() / (nm / len(v)):.2f} per needed message), "
              f"IWANT-requested {iw.mean():.1f}")
    md, mf = np.array(agg(c, "mdeg")), np.array([x for x in agg(c, "mfast") if np.isfinite(x)])
    if len(md):
        print(f"    PQ mesh at 3.95 s: degree {md.mean():.2f}, 1 Gbit share {100 * mf.mean():.1f} %")
        a_c = [d for d in v if d.get("mfast") is not None and np.isfinite(d["mfast"])]
        if inc and a_c:
            print(f"    1 Gbit share of the PQ mesh, complete vs incomplete node-slots: "
                  f"{100 * np.mean([d['mfast'] for d in a_c if d['miss_m'] == 0] or [np.nan]):.1f} vs "
                  f"{100 * np.mean([d['mfast'] for d in a_c if d['miss_m'] > 0] or [np.nan]):.1f} %")
if PER:
    print("\n# Per slot: signatures missing at 8 s (%), late first deliveries per node, upload 4-8 s (% of cap), by class")
    for c in CL:
        sm, lf, up = [], [], []
        for s in done_slots:
            v = [d for _, d in rows.get((s, c), []) if "need_s" in d]
            sm.append(round(100 * sum(d["miss_s"] for d in v) / max(1, sum(d["need_s"] for d in v)), 3))
            lf.append(round(float(np.mean([d["late"] for d in v] or [0])), 2))
            u = [d["up48"] for _, d in rows.get((s, c), []) if "up48" in d]
            up.append(round(100 * float(np.mean(u)), 1) if u else None)
        print(f"  {NAME.get(c, c)} sig miss {sm}\n  {NAME.get(c, c)} late first {lf}\n  {NAME.get(c, c)} up 4-8 s {up}")
