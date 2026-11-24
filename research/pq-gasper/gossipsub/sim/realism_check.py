#!/usr/bin/env python3
"""Validation and calibration report for runs made with the sim/perturb.py flags.

    python3 sim/realism_check.py runs/<run> [--json out.json]

Sections (each only when the run has the data):
  rtt       libp2p ping RTTs per host pair vs the configured path (min and median), by continent pair
  loss      data packets sent vs received between pcap-captured hosts, and TCP retransmissions
  churn     offline/online transitions, connection churn, mesh churn and (re)graft events, recovery after restart
  bg        background bytes per node by class, total rx/tx per node (kB/s), by link class
  scoring   peer scores in mesh logs, scoring penalties, misbehaving hosts in meshes over time
  prop      block / column / attestation / aggregate arrival percentiles (from slot start and from publish)
  peers     connections and mesh sizes per node, by client
  pq        PQ completion at the deadline per class (node·slots offline in the window excluded)
"""

import glob
import json
import os
import struct
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perturb  # noqa: E402
from analyze import read_cfg  # noqa: E402

NEED_ALL = os.environ.get("PQ_NEED") == "all"  # every subscribed PQ subnet, ignoring a node's "need" (gen_config --backbone-subnets)

KINDS = perturb.KINDS
ACC = {name: (ow, jit, loss) for name, _, ow, jit, loss in perturb.ACCESS}


def q(xs, ps=(10, 50, 90, 95, 99)):
    xs = np.asarray(xs, dtype=float)
    return [round(float(v), 3) for v in np.percentile(xs, ps)] if xs.size else [None] * len(ps)


def load(run):
    cfg = read_cfg(run)
    ev = defaultdict(list)
    for f in glob.glob(os.path.join(run, "shadow.data/hosts/*/wbsim.*.stdout")):
        for line in open(f):
            if not line.startswith("{"):
                continue
            e = json.loads(line)
            ev[e["ev"]].append(e)
    bg = json.load(open(os.path.join(run, "bg.json"))) if os.path.exists(os.path.join(run, "bg.json")) else None
    return cfg, ev, bg


def one_way_ms(cfg, a, b):
    """Configured one-way latency and mean jitter (ms) between hosts a and b."""
    na, nb = cfg["nodes"][a], cfg["nodes"][b]
    ca, cb = na.get("city"), nb.get("city")
    if ca is None:
        return None
    acc_a, acc_b = na.get("access"), nb.get("access")
    lat = jit = 0.0
    for x in (acc_a, acc_b):
        if x:
            lat += ACC[x][0]
            jit += ACC[x][1]
    if ca != cb:
        lat += perturb.rtt(ca, cb) / 2
        jit += perturb.BACKBONE_JITTER_MS
    elif (acc_a is None and acc_b is None) or (acc_a == acc_b):
        lat += perturb.INTRA_CITY_RTT / 2
    return lat, jit


def sec_rtt(cfg, ev):
    pings = ev.get("ping", [])
    if not pings:
        return None
    by_pair = defaultdict(list)
    for e in pings:
        if e["peer"] is not None and e["t"] >= cfg["first_slot_s"] - 25:
            by_pair[(e["node"], e["peer"])].append(e["rtt_ms"])
    ratio_min, ratio_med, cont = [], [], defaultdict(lambda: [[], [], []])
    meas_all, exp_all = [], []
    for (a, b), xs in by_pair.items():
        ow = one_way_ms(cfg, a, b)
        if ow is None:
            continue
        base = 2 * ow[0]
        mean = base + 2 * ow[1]
        ratio_min.append(min(xs) / base)
        ratio_med.append(float(np.median(xs)) / mean)
        k = tuple(sorted((perturb.CONTINENT[cfg["nodes"][a]["city"]], perturb.CONTINENT[cfg["nodes"][b]["city"]])))
        cont[k][0].append(float(np.median(xs)))
        cont[k][1].append(mean)
        cont[k][2].append(min(xs))
        meas_all += xs
        exp_all.append(mean)
    return dict(pairs=len(by_pair), pings=len(pings),
                min_over_configured_base=q(ratio_min, (1, 50, 99)),
                median_over_configured_mean=q(ratio_med, (10, 50, 90)),
                rtt_all_measured_ms=q(meas_all), rtt_pairs_configured_mean_ms=q(exp_all),
                by_continent={f"{k[0]}-{k[1]}": dict(pairs=len(v[0]), measured_median_ms=round(float(np.median(v[0])), 1),
                                                    configured_mean_ms=round(float(np.median(v[1])), 1),
                                                    measured_min_ms=round(float(np.median(v[2])), 1))
                              for k, v in sorted(cont.items())})


def pcap_packets(path):
    with open(path, "rb") as f:
        gh = f.read(24)
        nano = struct.unpack("<I", gh[:4])[0] == 0xA1B23C4D
        off = 14 if struct.unpack("<I", gh[20:24])[0] == 1 else 0
        while True:
            h = f.read(16)
            if len(h) < 16:
                return
            sec, frac, incl, orig = struct.unpack("<IIII", h)
            d = f.read(incl)
            ip = d[off:]
            if len(ip) < 40 or ip[9] != 6:
                continue
            ihl = (ip[0] & 15) * 4
            tot = struct.unpack(">H", ip[2:4])[0]
            tcp = ip[ihl:]
            thl = (tcp[12] >> 4) * 4
            pay = tot - ihl - thl
            sport, dport, seq = struct.unpack(">HHI", tcp[:8])
            yield sec + frac / (1e9 if nano else 1e6), ip[12:16], ip[16:20], sport, dport, seq, pay


def sec_loss(run, cfg):
    caps = sorted(glob.glob(os.path.join(run, "shadow.data/hosts/*/eth0.pcap")))
    if len(caps) < 2:
        return None
    ipn = {bytes(int(x) for x in nd["ip"].split(".")): nd["id"] for nd in cfg["nodes"]}
    names = {int(p.split("/")[-2][1:]): p for p in caps}
    sent, recv, retx = defaultdict(int), defaultdict(int), 0
    data_sent = 0
    for i, p in names.items():
        seen = set()
        for t, s, d, sp, dp, seq, pay in pcap_packets(p):
            if pay <= 0:
                continue
            a, b = ipn.get(s), ipn.get(d)
            key = (a, b, sp, dp, seq, pay)
            if a == i:
                data_sent += 1
                if key in seen:
                    retx += 1
                seen.add(key)
                if b in names:
                    sent[key] += 1
            elif b == i and a in names:
                recv[key] += 1
    tot = sum(sent.values())
    got = sum(min(c, recv.get(k, 0)) for k, c in sent.items())
    pairs = defaultdict(lambda: [0, 0])
    for k, c in sent.items():
        pairs[(k[0], k[1])][0] += c
        pairs[(k[0], k[1])][1] += min(c, recv.get(k, 0))
    exp = []
    for (a, b), (c, g) in pairs.items():
        la = ACC.get(cfg["nodes"][a].get("access"), (0, 0, 0))[2]
        lb = ACC.get(cfg["nodes"][b].get("access"), (0, 0, 0))[2]
        ca, cb = cfg["nodes"][a].get("city"), cfg["nodes"][b].get("city")
        lc = 0 if ca == cb else perturb.LOSS_INTER if perturb.CONTINENT[ca] != perturb.CONTINENT[cb] else perturb.LOSS_INTRA
        same_node = ca == cb and cfg["nodes"][a].get("access") == cfg["nodes"][b].get("access") and la
        p = 1 - (1 - la) ** 2 if same_node else 1 - (1 - la) * (1 - lc) * (1 - lb)
        exp.append((p, c))
    lev = (cfg.get("lever") or "").split()
    scale = cfg.get("loss_scale", float(lev[lev.index("--loss-scale") + 1]) if "--loss-scale" in lev else 1.0)
    return dict(captured_hosts=len(names), data_packets_between_captured=tot,
                measured_loss=round(1 - got / tot, 6) if tot else None,
                configured_loss_weighted=round(sum(p * c for p, c in exp) / max(1, sum(c for _, c in exp)) * scale, 6),
                retransmissions=retx, data_packets_sent=data_sent,
                retransmit_rate=round(retx / data_sent, 6) if data_sent else None)


def ticks_by_node(ev):
    tk = defaultdict(list)
    for e in ev.get("tick", []):
        tk[e["node"]].append(e)
    return tk


def delta(tk, node, key, a, b):
    xs = tk[node]
    va = next((e.get(key, 0) for e in xs if e["t"] >= a - 1e-6), None)
    vb = next((e.get(key, 0) for e in xs if e["t"] >= b - 1e-6), xs[-1].get(key, 0) if xs else 0)
    return 0 if va is None else vb - va


def sec_churn(cfg, ev, tk):
    n = len(cfg["nodes"])
    end = cfg["first_slot_s"] + cfg["slots"] * cfg["slot_s"]
    last = {i: tk[i][-1] for i in tk if tk[i]}
    tot = lambda k: sum(e.get(k, 0) for e in last.values())
    churn = defaultdict(int)
    incl = defaultdict(int)
    for e in last.values():
        for k, v in e.items():
            if k.startswith("mesh_peer_churn_events:") or (k.startswith("bg_") and ":mesh_peer_churn_events:" in k):
                churn[k.split(":")[-1]] += v
            if k.startswith("mesh_peer_inclusion_events:") or (k.startswith("bg_") and ":mesh_peer_inclusion_events:" in k):
                incl[k.split(":")[-1]] += v
    sched_off = [(i, x, y) for i, nd in enumerate(cfg["nodes"]) for x, y in nd.get("offline", [])]
    # recovery: for each restart (x, y) inside the run, mesh size in the first mesh log after y vs before x
    mesh = defaultdict(dict)
    for e in ev.get("mesh", []):
        mesh[e["node"]][e["slot"]] = sum(len(v) for v in e["mesh"].values())
    t0 = cfg["first_slot_s"]
    rec = []
    for i, x, y in sched_off:
        if y < end and x > t0:
            before = [v for s, v in mesh[i].items() if t0 + s * 12 + 3.95 < x]
            after = sorted((s, v) for s, v in mesh[i].items() if t0 + s * 12 + 3.95 > y)
            if before and after:
                rec.append(dict(node=i, down_s=round(y - x, 1), mesh_before=before[-1], mesh_first_after=after[0][1],
                                first_after_s=round(t0 + after[0][0] * 12 + 3.95 - y, 1)))
    return dict(scheduled_offline_intervals=len(sched_off),
                leaves=sum(1 for _, x, y in sched_off if y > 1e8), joins=sum(1 for _, x, y in sched_off if x == 0.0),
                restarts=sum(1 for _, x, y in sched_off if 0 < x and y < 1e8),
                offline_events=len(ev.get("offline", [])), online_events=len(ev.get("online", [])),
                conn_churned=tot("pm_churned"), pm_dials=tot("pm_dials"), pm_prunes=tot("pm_prunes"),
                refused_inbound=tot("pm_refused"), score_disconnects=tot("pm_score_dc"),
                mesh_churn_by_reason=dict(churn), mesh_inclusion_by_reason=dict(incl),
                recovery=rec[:20], recovery_n=len(rec))


def node_class(nd):
    return nd["link"]


def sec_bg(cfg, ev, tk):
    t0s = [cfg["first_slot_s"] + s * cfg["slot_s"] for s in range(cfg["slots"])]
    steady = t0s[2:] or t0s
    out = {}
    classes = sorted({node_class(nd) for nd in cfg["nodes"]})
    keys = sorted({k for e in ev.get("tick", [])[:5000] for k in e if k.endswith(":topic_msg_recv_bytes")})
    for c in classes:
        ids = [nd["id"] for nd in cfg["nodes"] if node_class(nd) == c and tk[nd["id"]]]
        r = dict(nodes=len(ids))
        for k in keys + ["topic_msg_recv_bytes"]:
            v = [np.mean([delta(tk, i, k, t, t + 12) for t in steady]) / 1e3 for i in ids]
            r[f"{k.split(':')[0] if ':' in k else 'pq'}_recv_kB_per_slot"] = round(float(np.mean(v)), 1)
        rx = [np.mean([delta(tk, i, "rx", t, t + 12) for t in steady]) / 12 / 1e3 for i in ids]
        tx = [np.mean([delta(tk, i, "tx", t, t + 12) for t in steady]) / 12 / 1e3 for i in ids]
        r["rx_kB_s"] = q(rx, (10, 50, 90))
        r["tx_kB_s"] = q(tx, (10, 50, 90))
        r["rx_Mbit_s_mean"] = round(float(np.mean(rx)) * 8 / 1e3, 2)
        out[c] = r
    # duplicates per unique message by class
    dup = {}
    for k in [x.replace(":topic_msg_recv_bytes", "") for x in keys] + [""]:
        pre = f"{k}:" if k else ""
        u = sum(delta(tk, i, pre + "topic_msg_recv_counts", steady[0], steady[-1] + 12) for i in tk)
        a = sum(delta(tk, i, pre + "topic_msg_recv_counts_unfiltered", steady[0], steady[-1] + 12) for i in tk)
        if u:
            dup[k or "pq"] = round(a / u, 2)
    return dict(per_class=out, copies_per_unique_msg=dup)


def sec_scoring(cfg, ev, tk):
    if not cfg.get("scoring"):
        return None
    sc = [e["score"] for e in ev.get("mesh", []) if e.get("score")]
    last = {i: tk[i][-1] for i in tk if tk[i]}
    pen = defaultdict(int)
    for e in last.values():
        for k, v in e.items():
            if "scoring_penalties" in k:
                pen[k.split(":")[-1]] += v
    bad = {nd["id"] for nd in cfg["nodes"] if nd.get("bad")}
    free = {nd["id"] for nd in cfg["nodes"] if nd.get("freeride")}
    per_slot = []
    for s in range(cfg["slots"]):
        es = [e for e in ev.get("mesh", []) if e["slot"] == s]
        tot = sum(len(v) for e in es for v in e["mesh"].values())
        inb = sum(1 for e in es for v in e["mesh"].values() for j in v if j in bad)
        inf = sum(1 for e in es for v in e["mesh"].values() for j in v if j in free)
        conb = sum(1 for e in es for j in e["conns"] if j in bad)
        neg = sum(e.get("score", [0, 0, 0, 0])[3] for e in es if e.get("score"))
        per_slot.append(dict(slot=s, mesh_links=tot, mesh_links_to_bad=inb, mesh_links_to_freeriders=inf,
                             conns_to_bad=conb, peers_with_negative_score=neg))
    return dict(mesh_logs_with_scores=len(sc), score_min=q([x[0] for x in sc], (1, 50)),
                score_mean=q([x[1] for x in sc], (10, 50, 90)), score_max=q([x[2] for x in sc], (50, 99)),
                penalties=dict(pen), bad_hosts=len(bad), freeriders=len(free), per_slot=per_slot)


def sec_prop(cfg, ev, bg):
    if not bg:
        return None
    t0 = cfg["first_slot_s"]
    nodes = cfg["nodes"]
    rx = defaultdict(dict)
    for e in ev.get("rxbg", []):
        rx[e["slot"]][e["node"]] = dict((k, ms) for k, ms in e["r"])
    offl = lambda i, s: any(x < t0 + 12 * (s + 1) and y > t0 + 12 * s for x, y in nodes[i].get("offline", []))
    subs = defaultdict(list)  # topic -> subscribers (a node's topics are fixed for the run)
    for i, nd in enumerate(nodes):
        for t in nd["topics"]:
            subs[t].append(i)
    off = {(i, s) for i, nd in enumerate(nodes) if nd.get("offline") for s in range(len(bg)) if offl(i, s)}
    res = {}
    for kind in ("block", "col", "att", "agg"):
        kid = KINDS.index(kind)
        from_start, from_pub, by_cont, miss = [], [], defaultdict(list), 0
        tot = 0
        for s, msgs in enumerate(bg):
            if s < 2:
                continue
            for k, m in enumerate(msgs):
                if m[4] != kid or not m[5]:
                    continue
                for i in subs[m[2]]:
                    nd = nodes[i]
                    if i == m[0] or (i, s) in off:
                        continue
                    tot += 1
                    ms = rx[s].get(i, {}).get(k)
                    if ms is None:
                        miss += 1
                        continue
                    from_start.append(ms / 1e3)
                    from_pub.append((ms - m[1]) / 1e3)
                    by_cont[perturb.CONTINENT.get(nd.get("city"), nd.get("region"))].append(ms / 1e3)
        if tot:
            res[kind] = dict(deliveries=tot, missing=miss, from_slot_start_s=q(from_start), from_publish_s=q(from_pub),
                             by_continent_from_start_p50_p90_p99={c: q(v, (50, 90, 99)) for c, v in sorted(by_cont.items())})
    if "att" in res:
        res["att"]["after_4s_mark_s"] = [None if x is None else round(x - 4.0, 3) for x in res["att"]["from_slot_start_s"]]
    return res


def sec_peers(cfg, ev):
    ms = [e for e in ev.get("mesh", []) if e["slot"] >= 2]
    if not ms:
        return None
    by = defaultdict(lambda: defaultdict(list))
    for e in ms:
        nd = cfg["nodes"][e["node"]]
        for grp in (nd.get("client", "all"), "link:" + nd["link"]):
            by[grp]["conns"].append(len(e["conns"]))
            for t, v in e["mesh"].items():
                t = int(t)
                cls = "pq" if t < 100 else "block" if t == 100 else "agg" if t == 101 else "syncc" if t == 102 \
                    else "att" if t < 300 else "col"
                by[grp][f"mesh_{cls}"].append(len(v))
    return {g: {k: dict(mean=round(float(np.mean(v)), 1), p10_p50_p90=q(v, (10, 50, 90))) for k, v in d.items()}
            for g, d in sorted(by.items())}


def sec_verify(cfg, tk):
    if not cfg.get("verify_us_kind"):
        return None
    out = {}
    for nd in cfg["nodes"]:
        last = tk[nd["id"]][-1] if tk[nd["id"]] else {}
        k = f"{nd['link']} cpu x{nd.get('cpu', 1)} workers {nd.get('workers', 1)}"
        o = out.setdefault(k, [0, 0, 0, 0])
        o[0] += 1
        o[1] += last.get("v_n", 0)
        o[2] += last.get("v_us", 0)
        o[3] = max(o[3], last.get("v_max_us", 0))
    return {k: dict(nodes=a, msgs_verified_per_node=round(b / a), mean_delay_ms=round(c / max(b, 1) / 1e3, 3),
                    max_delay_ms=round(d / 1e3, 1)) for k, (a, b, c, d) in sorted(out.items())}


def sec_pq(cfg, ev):
    sched = cfg.get("sched") or []
    if not any(sched):
        return None
    nodes = cfg["nodes"]
    t0 = cfg["first_slot_s"]
    rx = {}
    for e in ev.get("rx", []):
        rx[(e["slot"], e["node"])] = e["r"]
    out = defaultdict(lambda: [0, 0])
    lat = defaultdict(list)
    skipped = 0
    per_slot = []
    for s, msgs in enumerate(sched):
        ok_s = tot_s = 0
        for i, nd in enumerate(nodes):
            dl = t0 + 12 * s + max(m[4] for m in msgs) / 1e3 if msgs else 0
            if any(x < dl and y > t0 + 12 * s for x, y in nd.get("offline", [])):
                skipped += 1
                continue
            r = rx.get((s, i))
            if r is None:
                continue
            need = [k for k, m in enumerate(msgs) if m[2] in (nd["topics"] if NEED_ALL or "need" not in nd else nd["need"])]
            ok = all(0 <= r[k] <= msgs[k][4] for k in need)
            c = nd["link"]
            out[c][0] += ok
            out[c][1] += 1
            ok_s += ok
            tot_s += 1
            if s >= 2:
                lat[c] += [r[k] - msgs[k][1] for k in need if r[k] >= 0 and msgs[k][0] != i]
        per_slot.append(round(100 * ok_s / max(tot_s, 1), 1))
    return dict(complete_per_slot_pct=per_slot,
                per_class={c: dict(complete_pct=round(100 * a / b, 2), node_slots=b,
                                   lat_p50_p99_s=[round(x / 1e3, 2) for x in np.percentile(lat[c], [50, 99])] if lat[c] else None)
                           for c, (a, b) in sorted(out.items())},
                node_slots_offline_excluded=skipped, pq_lost_to_churn=cfg.get("pq_lost_to_churn", 0))


def main():
    run = sys.argv[1]
    cfg, ev, bg = load(run)
    tk = ticks_by_node(ev)
    res = dict(run=os.path.basename(run.rstrip("/")), hosts=len(cfg["nodes"]), slots=cfg["slots"], lever=cfg.get("lever"))
    for name, f in [("rtt", lambda: sec_rtt(cfg, ev)), ("loss", lambda: sec_loss(run, cfg)),
                    ("churn", lambda: sec_churn(cfg, ev, tk)), ("bg", lambda: sec_bg(cfg, ev, tk)),
                    ("scoring", lambda: sec_scoring(cfg, ev, tk)), ("prop", lambda: sec_prop(cfg, ev, bg)),
                    ("peers", lambda: sec_peers(cfg, ev)), ("verify", lambda: sec_verify(cfg, tk)), ("pq", lambda: sec_pq(cfg, ev))]:
        try:
            res[name] = f()
        except Exception as e:  # keep the other sections
            res[name] = f"error: {e!r}"
    out = os.environ.get("REALISM_OUT") or os.path.join(run, "realism.json")
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
