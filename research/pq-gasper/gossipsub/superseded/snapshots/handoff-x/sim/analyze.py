#!/usr/bin/env python3
"""Summarise Shadow runs produced by gen_config.py.

    python3 sim/analyze.py runs/gossip runs/direct [...] > results/sim.md
    python3 sim/analyze.py runs/flood-* > flood.md   # flood runs (gen_config.py --mode flood)
"""

import glob
import json
import os
import statistics as st
import sys
from collections import defaultdict


def pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    return xs[min(len(xs) - 1, int(q * len(xs)))]


def wpct(pairs, q):
    """Percentile of (value, weight) pairs; a vote_rx event with n stands for n votes."""
    pairs = sorted(pairs)
    total = sum(w for _, w in pairs)
    if not total:
        return float("nan")
    target, acc = min(total - 1, int(q * total)), 0
    for v, w in pairs:
        acc += w
        if acc > target:
            return v
    return pairs[-1][0]


def load(run):
    cfg = json.load(open(os.path.join(run, "run.json")))
    events = []
    for f in glob.glob(os.path.join(run, "shadow.data/hosts/*/wbsim.*.stdout")):
        for line in open(f):
            if line.startswith("{"):
                events.append(json.loads(line))
    return cfg, events


def summarise(run):
    cfg, ev = load(run)
    nodes = {n["id"]: n for n in cfg["nodes"]}
    aggs = [n["id"] for n in cfg["nodes"] if n["role"] == "aggregator"]
    votes = sum(len(n["validators"]) for n in cfg["nodes"])
    tps = cfg["topics"] // cfg["subnets"]
    # votes an aggregator must collect: its topic (direct) or its whole subnet (gossip)
    need = cfg["votes_per_topic"] * (tps if cfg["mode"] == "gossip" else 1)
    # keep only slots every host finished (a run may be stopped early)
    done = [s for s in range(cfg["slots"])
            if sum(1 for e in ev if e["ev"] == "bytes" and e["phase"] == "proofs" and e["slot"] == s) == len(nodes)]
    ev = [e for e in ev if "slot" not in e or e["slot"] in done]
    slots = len(done)
    slot0 = cfg["first_slot_s"]
    vote_start = lambda s: slot0 + s * cfg["slot_s"] + cfg["vote_offset_s"]

    r = {"run": os.path.basename(run.rstrip("/")), "mode": cfg["mode"] + (" (cold connect)" if cfg["cold_connect"] else "")
         + (", proofs pulled" if cfg["mode"] == "gossip" and (cfg.get("proofs") == "pull" or not cfg.get("gossip_proofs", True)) else ""),
         "profile / seed": f"{cfg.get('profile', '?')} / {cfg['seed']}",
         "hosts": len(nodes), "subnets × votes per subnet": f"{cfg['subnets']} × {votes // cfg['subnets']:,}",
         "direct topics × recipients": f"{cfg['topics']} × {len(aggs) // cfg['topics']}" if cfg["mode"] == "direct" else "–",
         "slots analysed": slots}

    lat = [(e["lat"], e.get("n", 1)) for e in ev if e["ev"] == "vote_rx" and not e["late"]]
    r["vote latency p50/p90/p99/max (ms)"] = "/".join(f"{wpct(lat, q) * 1e3:.0f}" for q in (0.5, 0.9, 0.99, 1.0))
    by_link = defaultdict(list)
    for e in ev:
        if e["ev"] == "vote_rx" and not e["late"] and e["from"] in nodes:
            by_link[nodes[e["from"]]["link"]].append((e["lat"], e.get("n", 1)))
    r["vote latency p99 by voter link (ms)"] = ", ".join(
        f"{k} {wpct(v, 0.99) * 1e3:.0f}" for k, v in sorted(by_link.items()))

    # coverage at the aggregator deadline, and time until an aggregator held 100 % of votes
    close = [e for e in ev if e["ev"] == "agg_close"]
    cov = [e["count"] / need for e in close]
    r["votes held at deadline: min / mean"] = f"{min(cov):.1%} / {st.mean(cov):.2%}"
    full = []
    by = defaultdict(list)
    for e in ev:
        if e["ev"] == "vote_rx":
            by[(e["node"], e["slot"])].append((e["t"], e.get("n", 1)))
    for (n, s), ts in by.items():
        acc = 0
        for t, w in sorted(ts):
            acc += w
            if acc >= need:
                full.append(t - vote_start(s))
                break
    r["aggregators with 100 % (of agg·slots)"] = f"{len(full)}/{len(aggs) * slots}"
    if full:
        r["time to 100 % of votes after vote start: p50 / max (s)"] = f"{pct(full, 0.5):.2f} / {max(full):.2f}"

    # proofs at the proposer
    prop = [n["id"] for n in cfg["nodes"] if n["role"] == "proposer"][0]
    first = []
    for s in done:
        ps = [e for e in ev if e["ev"] == "proof_rx" and e["node"] == prop and e["slot"] == s]
        tx = [e["t"] for e in ev if e["ev"] == "proof_tx" and e["slot"] == s]
        if tx:
            ts = sorted(p["t"] - min(tx) for p in ps) or [float("nan")]
            first.append((ts[0], ts[-1], len(ps)))
    if first:
        r["proposer: proofs per slot (min–max)"] = f"{min(f[2] for f in first)}–{max(f[2] for f in first)}"
        r["proposer: 1st / last proof after 1st emitted (s)"] = (
            f"{st.mean(f[0] for f in first):.2f} / {st.mean(f[1] for f in first):.2f}")

    # proofs held by the end of the slot (the next proposer's deadline)
    proofs = cfg.get("proofs", "flood" if cfg.get("gossip_proofs", cfg["mode"] == "gossip") else "pull")
    r["proofs"] = proofs + (f" ({len(cfg['decoys'])} decoys)" if proofs == "decoy" else "")
    emitted = {s: sum(1 for e in ev if e["ev"] == "proof_tx" and e["slot"] == s) for s in done}
    held = defaultdict(set)
    for e in ev:
        if e["ev"] == "proof_rx" and e["slot"] in emitted and e["t"] < slot0 + (e["slot"] + 1) * cfg["slot_s"]:
            held[(e["node"], e["slot"])].add(e["agg"])
    r["proofs emitted per slot"] = f"{min(emitted.values(), default=0)}"
    if proofs != "pull" and emitted:
        share = lambda n, s: len(held[(n, s)]) / emitted[s] if emitted[s] else 1.0
        r["proposer: share of proofs held at slot end, min / mean"] = (
            f"{min(share(prop, s) for s in done):.0%} / {st.mean(share(prop, s) for s in done):.1%}")
    if proofs == "flood" and emitted:
        # the proposer could be any node: every node must get them
        by_cls = defaultdict(list)
        for n in nodes.values():
            if n["role"] != "aggregator":
                by_cls[n["link"]] += [share(n["id"], s) for s in done]
        r["any node: share of proofs held at slot end, min / mean, by link"] = ", ".join(
            f"{k} {min(v):.0%} / {st.mean(v):.1%}" for k, v in sorted(by_cls.items()))

    # bytes per role and link class, per phase, averaged over slots
    rows = defaultdict(lambda: defaultdict(list))
    for e in ev:
        if e["ev"] != "bytes":
            continue
        n = nodes[e["node"]]
        cls = n.get("cls") or (n["role"] if n["role"] != "voter" else f"voter-{n['link']}")
        rows[cls][(e["phase"], "rx")].append(e["rx"])
        rows[cls][(e["phase"], "tx")].append(e["tx"])
    r["_bytes"] = {cls: {k: st.mean(v) for k, v in d.items()} for cls, d in rows.items()}

    # network-wide vote-phase bytes and copies per vote (payload-normalised)
    vote_rx_total = sum(e["rx"] for e in ev if e["ev"] == "bytes" and e["phase"] == "votes") / slots
    r["network bytes received in vote phase / slot"] = f"{vote_rx_total / 2**20:,.1f} MiB"
    vb = cfg["vote_bytes"]
    if cfg["mode"] == "gossip":
        # every node needs every vote of the subnets it joined (all of them here)
        r["bytes received per needed vote byte (κ)"] = f"{vote_rx_total / (votes * vb * (len(nodes) - 1)):.2f}"
        drops = [e for e in ev if e["ev"] == "slow_peer"]
        r["gossip messages dropped from send queues, run total (forward / publish)"] = (
            f"{sum(e['forward'] for e in drops):,} / {sum(e['publish'] for e in drops):,}")
    else:
        # each vote is needed by the recipients of its topic
        r["bytes received per needed vote byte (κ)"] = f"{vote_rx_total / (votes * vb * len(aggs) / cfg['topics']):.2f}"
    # a cancelled duplicate dial (already connected or dialling) is harmless
    errs = [e for e in ev if e["ev"] in ("rr_fail", "conn_err", "dial_err", "publish_err")
            and "dial condition" not in e.get("err", "")]
    r["errors"] = str(len(errs))
    return r


MBIT = {"Mbit": 1e6, "Gbit": 1e9}


def cap_bps(x):
    v, u = x.split()
    return float(v) * MBIT[u]


def flood_load(run):
    """Per-node receipt times (ms after slot start, -1 never) and counter ticks."""
    import numpy as np
    cfg = json.load(open(os.path.join(run, "run.json")))
    n, slots, msgs = len(cfg["nodes"]), cfg["slots"], cfg["msgs"]
    rx = np.full((slots, n, msgs), -1, dtype=np.int64)
    reported = np.zeros((slots, n), dtype=bool)
    ticks = defaultdict(list)
    errs = []
    for f in glob.glob(os.path.join(run, "shadow.data/hosts/*/wbsim.*.stdout")):
        for line in open(f):
            if line.startswith('{"ev":"rx"'):
                e = json.loads(line)
                rx[e["slot"], e["node"]] = e["r"]
                reported[e["slot"], e["node"]] = True
            elif '"ev":"tick"' in line:
                e = json.loads(line)
                ticks[e["node"]].append(e)
            elif '"ev":"publish_err"' in line or '"ev":"conn_err"' in line:
                errs.append(json.loads(line))
    # a run stopped early: keep the slots every node reported
    done = int(np.argmin(np.append(reported.all(axis=1), False)))
    cfg["slots"] = done
    return cfg, rx[:done], ticks, errs


def flood_summary(run):
    """Everything the report needs from one flood run, cached in <run>/summary.json."""
    import numpy as np
    cache = os.path.join(run, "summary.json")
    log = os.path.join(run, "shadow.log")
    fresh = lambda: os.path.getmtime(cache) > max(os.path.getmtime(log), os.path.getmtime(__file__))
    if os.path.exists(cache) and fresh() and "Finished simulation" in open(log).read()[-4096:]:
        return json.load(open(cache))
    cfg, rx, ticks, errs = flood_load(run)
    n, slots, msgs, size = len(cfg["nodes"]), cfg["slots"], cfg["msgs"], cfg["msg_bytes"]
    t0s = [cfg["first_slot_s"] + s * cfg["slot_s"] for s in range(slots)]
    pub_start_ms = int(cfg["vote_offset_s"] * 1000)
    deadline_ms = pub_start_ms + 4000
    sched = np.array(cfg["sched"])  # slots x msgs x (publisher, offset ms)
    got_all = all(len(ticks[i]) > 0 for i in range(n))

    # counters as arrays: node x tick
    keys = ["rx", "tx", "topic_msg_recv_counts", "topic_msg_recv_counts_unfiltered", "topic_msg_sent_counts",
            "idontwant_msgs_ids", "topic_iwant_msgs", "f_forward", "f_publish", "f_queue_full", "f_timeout", "conns",
            "mesh_peer_counts"]
    T = min(len(ticks[i]) for i in range(n))
    tt = np.array([e["t"] for e in ticks[0]][:T])
    C = {k: np.array([[e.get(k, 0) for e in ticks[i][:T]] + [0] * (T - len(ticks[i])) for i in range(n)], dtype=np.float64)
         for k in keys}

    def delta(k, a, b):
        """Per-node change of counter k between times a and b (s)."""
        ia, ib = np.searchsorted(tt, a - 1e-6), np.searchsorted(tt, b - 1e-6)
        ib = min(ib, T - 1)
        return C[k][:, ib] - C[k][:, ia]

    links = [nd["link"] for nd in cfg["nodes"]]
    classes = sorted(set(links))
    up = np.array([cap_bps(nd["up"]) for nd in cfg["nodes"]])
    down = np.array([cap_bps(nd["down"]) for nd in cfg["nodes"]])

    per_slot = []
    lat_all = []
    for s in range(slots):
        r = rx[s]
        held = ((r >= 0) & (r <= deadline_ms)).sum(axis=1)
        held_end = ((r >= 0) & (r <= 12000)).sum(axis=1)
        held_ever = (r >= 0).sum(axis=1)
        own = sched[s, :, 0][None, :] == np.arange(n)[:, None]
        lat = np.where(r >= 0, r - sched[s, :, 1][None, :], np.iinfo(np.int64).max)[~own]
        lat_all.append(lat)
        q = np.percentile(lat, [50, 90, 99, 100], method="lower") if lat.size else [np.nan] * 4
        t0 = t0s[s]
        rxb = delta("rx", t0, t0 + 12)
        dl_rx = delta("rx", t0, t0 + cfg["vote_offset_s"] + 4)
        uniq = delta("topic_msg_recv_counts", t0, t0 + 12)
        unf = delta("topic_msg_recv_counts_unfiltered", t0, t0 + 12)
        complete_t = np.where(held_ever == msgs, r.max(axis=1) - pub_start_ms, -1)
        per_slot.append(dict(
            slot=s,
            complete_at_deadline=float((held == msgs).mean()),
            held_at_deadline_mean=float(held.mean() / msgs), held_at_deadline_min=float(held.min() / msgs),
            complete_at_slot_end=float((held_end == msgs).mean()), held_at_slot_end_mean=float(held_end.mean() / msgs),
            complete_ever=float((held_ever == msgs).mean()), never_delivered=int(msgs * n - held_ever.sum()),
            lat_ms=[None if x == np.iinfo(np.int64).max else int(x) for x in q],
            time_to_complete_p50_ms=(int(np.median(complete_t[complete_t >= 0])) if (complete_t >= 0).any() else None),
            kappa_slot=float(rxb.sum() / (n * msgs * size)),
            kappa_deadline=float(dl_rx.sum() / (n * msgs * size)),
            dup_per_msg=float((unf.sum() - uniq.sum()) / max(uniq.sum(), 1)),
            copies_per_msg=float(unf.sum() / max(uniq.sum(), 1)),
            idontwant_ids_per_node=float(delta("idontwant_msgs_ids", t0, t0 + 12).mean()),
            iwant_per_node=float(delta("topic_iwant_msgs", t0, t0 + 12).mean()),
            sent_msgs_per_node=float(delta("topic_msg_sent_counts", t0, t0 + 12).mean()),
            fwd_dropped=int(delta("f_forward", t0, t0 + 12).sum()),
            pub_dropped=int(delta("f_publish", t0, t0 + 12).sum()),
            timed_out=int(delta("f_timeout", t0, t0 + 12).sum()),
            queue_full=int(delta("f_queue_full", t0, t0 + 12).sum()),
            # traffic still flowing in the 4 s before the next slot publishes: backlog
            tail_rx_MiB_per_node=float(delta("rx", t0 + 8, t0 + 12).mean() / 2**20),
            rx_MiB_per_node=float(rxb.mean() / 2**20), tx_MiB_per_node=float(delta("tx", t0, t0 + 12).mean() / 2**20),
        ))
    lat = np.concatenate(lat_all)
    q = np.percentile(lat, [50, 90, 99, 99.9, 100], method="lower")

    # link use per class: whole slots (steady state = slots >= 2), the 4 s deadline window, and the
    # busiest single bin
    end = t0s[-1] + 12
    steady = [s for s in range(slots) if s >= 2] or list(range(slots))
    links_out = {}
    for cls in classes:
        m = np.array([l == cls for l in links])
        d = {"nodes": int(m.sum()), "up_cap_Mbps": float(up[m][0] / 1e6), "down_cap_Mbps": float(down[m][0] / 1e6)}
        for name, (a, b) in {"slot": (0, 12), "window": (cfg["vote_offset_s"], cfg["vote_offset_s"] + 4)}.items():
            txr = np.mean([delta("tx", t0s[s] + a, t0s[s] + b) for s in steady], axis=0)[m] * 8 / (b - a)
            rxr = np.mean([delta("rx", t0s[s] + a, t0s[s] + b) for s in steady], axis=0)[m] * 8 / (b - a)
            d[f"up_{name}_mean"] = float((txr / up[m]).mean())
            d[f"up_{name}_max"] = float((txr / up[m]).max())
            d[f"down_{name}_mean"] = float((rxr / down[m]).mean())
            d[f"down_{name}_max"] = float((rxr / down[m]).max())
        i0, i1 = np.searchsorted(tt, t0s[0]), np.searchsorted(tt, end)
        bins_tx = np.diff(C["tx"][m][:, i0:i1 + 1], axis=1) * 8 / cfg["bin_s"]
        bins_rx = np.diff(C["rx"][m][:, i0:i1 + 1], axis=1) * 8 / cfg["bin_s"]
        d["up_bin_max"] = float((bins_tx / up[m][:, None]).max())
        d["down_bin_max"] = float((bins_rx / down[m][:, None]).max())
        d["up_run_mean"] = float(((C["tx"][m][:, i1] - C["tx"][m][:, i0]) * 8 / (end - t0s[0]) / up[m]).mean())
        d["fwd_dropped_per_node_slot"] = float(delta("f_forward", t0s[0], end)[m].mean() / slots)
        d["complete_at_deadline"] = float(np.mean([(((rx[s][m] >= 0) & (rx[s][m] <= deadline_ms)).sum(axis=1) == msgs).mean()
                                                   for s in range(slots)]))
        # messages this class published: mean share of nodes holding them at the deadline
        held_by = [(((rx[s] >= 0) & (rx[s] <= deadline_ms)).mean(axis=0))[m[sched[s, :, 0]]] for s in range(slots)]
        held_by = np.concatenate(held_by)
        d["published"] = int(held_by.size)
        d["published_held_at_deadline"] = float(held_by.mean()) if held_by.size else None
        links_out[cls] = d

    drain_rx = delta("rx", end, end + cfg["drain_s"]) if tt[-1] >= end + cfg["drain_s"] - 1e-6 else np.full(n, np.nan)
    res = dict(run=os.path.basename(run.rstrip("/")), hosts=n, slots=slots, msgs=msgs, msg_bytes=size,
               links=cfg["links"], fast_share=cfg["fast_share"], seed=cfg["seed"], gossip_dial=cfg["gossip_dial"],
               publish_window=cfg["publish_window"], complete_data=got_all,
               conns_mean=float(C["conns"][:, np.searchsorted(tt, t0s[0])].mean()),
               mesh_mean=float(C["mesh_peer_counts"][:, np.searchsorted(tt, t0s[0])].mean()),
               lat_ms=[None if x == np.iinfo(np.int64).max else int(x) for x in q],
               drain_rx_MiB_per_node=float(drain_rx.mean() / 2**20),
               errors=len([e for e in errs if e["ev"] == "publish_err"]), conn_errors=len(errs) - len([e for e in errs if e["ev"] == "publish_err"]),
               per_slot=per_slot, links_use=links_out)
    json.dump(res, open(cache, "w"))
    return res


def cls_extra(xs, steady):
    """Per-class latency p50/p99 (s ≥ 2, None = some message never arrived), κ, drops per node·slot, tail, worst held."""
    import numpy as np
    lat = np.concatenate([xs[s]["lat"] for s in steady])
    q = [int(v) if v < 10 ** 9 else None for v in np.percentile(lat, [50, 99], method="lower")] if len(lat) else [None, None]
    return dict(lat_p50=q[0], lat_p99=q[1], kappa=float(np.mean([xs[s]["kappa"] for s in steady])),
                drop_node_slot=float(np.mean([xs[s]["drop"] for s in steady])),
                tail_first=xs[0]["tail"], tail_last=xs[-1]["tail"],
                held_min=float(min(xs[s]["held_min"] for s in steady)))


def lever_summary(run):
    """Flood runs with topics, per-message sizes and deadlines (gen_config.py lever flags).

    A host needs every message on a topic it joins. It completes a slot when it holds each needed message by that
    message's deadline. Relaxed requirements are computed from the same receipt times. Cached in summary2.json."""
    import numpy as np
    cache = os.path.join(run, "summary2.json")
    log = os.path.join(run, "shadow.log")
    if os.path.exists(cache) and os.path.getmtime(cache) > max(os.path.getmtime(log), os.path.getmtime(__file__)) \
            and "Finished simulation" in open(log).read()[-4096:]:
        return json.load(open(cache))
    cfg = json.load(open(os.path.join(run, "run.json")))
    nodes = cfg["nodes"]
    n, S = len(nodes), cfg["slots"]
    sched = [np.array([(e + [0, cfg["msg_bytes"], 8000, 1])[:6] if len(e) < 6 else e for e in m], dtype=np.int64)
             for m in cfg["sched"]]
    rx = [None] * S
    ticks = defaultdict(list)
    for f in glob.glob(os.path.join(run, "shadow.data/hosts/*/wbsim.*.stdout")):
        for line in open(f):
            if line.startswith('{"ev":"rx"'):
                e = json.loads(line)
                if rx[e["slot"]] is None:
                    rx[e["slot"]] = np.full((n, len(sched[e["slot"]])), -2, dtype=np.int64)
                rx[e["slot"]][e["node"]] = e["r"]
            elif '"ev":"tick"' in line:
                e = json.loads(line)
                ticks[e["node"]].append(e)
    done = 0
    while done < S and rx[done] is not None and (rx[done][:, 0] != -2).all():
        done += 1
    S = done
    T = min(len(ticks[i]) for i in range(n))
    tt = np.array([e["t"] for e in ticks[0]][:T])
    keys = ["rx", "tx", "topic_msg_recv_counts", "topic_msg_recv_counts_unfiltered", "idontwant_msgs_ids",
            "topic_iwant_msgs", "f_forward", "f_publish", "f_queue_full", "f_timeout"]
    C = {k: np.array([[e.get(k, 0) for e in ticks[i][:T]] for i in range(n)], dtype=np.float64) for k in keys}

    def delta(k, a, b):
        ia, ib = np.searchsorted(tt, a - 1e-6), min(np.searchsorted(tt, b - 1e-6), T - 1)
        return C[k][:, ib] - C[k][:, ia]

    links = np.array([nd["link"] for nd in nodes])
    classes = sorted(set(links))
    joins = [set(nd.get("topics") or [0]) for nd in nodes]
    up = np.array([cap_bps(nd["up"]) for nd in nodes])
    t0s = [cfg["first_slot_s"] + s_ * cfg["slot_s"] for s_ in range(S)]
    per_slot, lats = [], []
    cls_ok = {c: [] for c in classes}
    cls_x = {c: [] for c in classes}  # per slot: latencies, κ, drops, tail, worst held
    for s_ in range(S):
        m = sched[s_]
        r = rx[s_]
        need = np.array([[t in j for t in m[:, 2]] for j in joins])
        got = r >= 0
        lat = np.where(got, r - m[None, :, 1], 10 ** 9)
        own = m[None, :, 0] == np.arange(n)[:, None]
        sig = m[:, 5] > 0  # signature messages (aggregates have 0 signatures)

        def ok(limit, mask=need):
            return ((lat <= limit) | ~mask).all(axis=1)
        okd = ((got & (r <= m[None, :, 4])) | ~need).all(axis=1)
        rel = m[:, 4] - m[:, 1]  # each message's budget from its own publish time
        held = ((got & (r <= m[None, :, 4])) & need & sig[None, :]).sum(axis=1) / np.maximum((need & sig[None, :]).sum(axis=1), 1)
        sel = need & ~own
        lats.append(lat[sel])
        rb = delta("rx", t0s[s_], t0s[s_] + 12)
        useful = (need * m[None, :, 3]).sum()
        drop = delta("f_forward", t0s[s_], t0s[s_] + 12) + delta("f_queue_full", t0s[s_], t0s[s_] + 12)
        tail = delta("rx", t0s[s_] + 8, t0s[s_] + 12)
        for c in classes:
            cls_ok[c].append(float(okd[links == c].mean()))
            k = links == c
            cls_x[c].append(dict(lat=lat[sel & k[:, None]], kappa=float(rb[k].sum() / max((need[k] * m[None, :, 3]).sum(), 1)),
                                 drop=float(drop[k].mean()), tail=float(tail[k].mean() / 2 ** 20),
                                 held_min=float(held[k].min())))
        per_slot.append(dict(
            complete=float(okd.mean()),
            complete_plus4=float(ok(rel[None, :] + 4000).mean()),
            complete_plus8=float(ok(rel[None, :] + 8000).mean()),
            two_thirds=float((held >= 2 / 3).mean()),
            held_mean=float(held.mean()), held_min=float(held.min()),
            fast_complete=float(okd[links == "cloud"].mean()) if (links == "cloud").any() else None,
            kappa=float(rb.sum() / useful),
            rx_MiB=float(rb.mean() / 2 ** 20),
            tail_MiB=float(delta("rx", t0s[s_] + 8, t0s[s_] + 12).mean() / 2 ** 20),
            copies=float((delta("topic_msg_recv_counts_unfiltered", t0s[s_], t0s[s_] + 12).sum())
                         / max(delta("topic_msg_recv_counts", t0s[s_], t0s[s_] + 12).sum(), 1)),
            idontwant=float(delta("idontwant_msgs_ids", t0s[s_], t0s[s_] + 12).mean()),
            fwd_dropped=int(delta("f_forward", t0s[s_], t0s[s_] + 12).sum()),
            queue_full=int(delta("f_queue_full", t0s[s_], t0s[s_] + 12).sum()),
            pub_dropped=int(delta("f_publish", t0s[s_], t0s[s_] + 12).sum()),
            never=int((need & ~got).sum()),
        ))
    lat = np.concatenate(lats)
    q = [int(x) if x < 10 ** 9 else None for x in np.percentile(lat, [50, 90, 99, 100], method="lower")]
    steady = list(range(2, S)) or list(range(S))
    end = t0s[-1] + 12
    upuse = {c: float(np.mean([(delta("tx", t0s[s_], t0s[s_] + 12) * 8 / 12 / up)[links == c].mean() for s_ in steady]))
             for c in classes}
    off = cfg["vote_offset_s"]
    upwin = np.mean([delta("tx", t0s[s_] + off, t0s[s_] + off + 4) * 8 / 4 / up for s_ in steady], axis=0)
    down = np.array([cap_bps(nd["down"]) for nd in nodes])
    dnwin = np.mean([delta("rx", t0s[s_] + off, t0s[s_] + off + 4) * 8 / 4 / down for s_ in steady], axis=0)
    res = dict(run=os.path.basename(run.rstrip("/")), hosts=n, slots=S, lever=cfg.get("lever", ""),
               msgs=[len(x) for x in sched[:S]], lat_ms=q, per_slot=per_slot,
               classes={c: dict(nodes=int((links == c).sum()), complete=float(np.mean(cls_ok[c])), up_use=upuse[c],
                                 up_win=float(upwin[links == c].mean()), up_win_max=float(upwin[links == c].max()),
                                 down_win=float(dnwin[links == c].mean()), down_win_max=float(dnwin[links == c].max()),
                                 complete_steady=float(np.mean(cls_ok[c][2:] or cls_ok[c])), slots=cls_ok[c],
                                 **cls_extra(cls_x[c], steady))
                        for c in classes},
               drain_MiB=float(delta("rx", end, end + cfg["drain_s"]).mean() / 2 ** 20)
               if tt[-1] >= end + cfg["drain_s"] - 1e-6 else None)
    json.dump(res, open(cache, "w"))
    return res


def lever_report(runs):
    """One row per run: completion per slot at the deadline, relaxed requirements, latency, κ, drops, backlog."""
    pct = lambda x: "–" if x is None else f"{x * 100:.0f}"
    print("| run | slots | all needed by deadline, per slot (%) | ≥ 2/3 held at deadline (mean %) | mean held (%) | 1 Gbit / slow classes "
          "complete (%) | latency p50/p90/p99 (s) | κ | fwd dropped per slot | rx MiB/node first→last | "
          "after deadline MiB first→last | drain MiB |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        d = lever_summary(r)
        ps = d["per_slot"]
        mean = lambda k: sum(p[k] for p in ps) / len(ps)
        cls = ", ".join(f"{c} {pct(v['complete'])}" for c, v in d["classes"].items())
        L = "/".join("never" if x is None else f"{x / 1e3:.2f}" for x in d["lat_ms"][:3])
        print(f"| {d['run']} | {d['slots']} | {' '.join(pct(p['complete']) for p in ps)} | "
              f"{pct(mean('two_thirds'))} | {mean('held_mean') * 100:.1f} | {cls} | "
              f"{L} | {mean('kappa'):.2f} | {mean('fwd_dropped') / 1e3:,.0f}k | {ps[0]['rx_MiB']:.1f}→{ps[-1]['rx_MiB']:.1f} | "
              f"{ps[0]['tail_MiB']:.2f}→{ps[-1]['tail_MiB']:.2f} | "
              + ("–" if d["drain_MiB"] is None else f"{d['drain_MiB']:.2f}") + " |")


def fmt_lat(q):
    return "/".join("never" if x is None else f"{x / 1e3:.2f}" for x in q)


def flood_report(runs):
    res = [flood_summary(r) for r in runs]
    print("| run | msgs × B | links (+1 Gbit share) | seed | dial | slots | nodes with all msgs at 4 s, per slot | "
          "mean held at 4 s (first→last slot) | latency p50/p90/p99/p99.9/max (s) | κ | never delivered |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in res:
        ps = r["per_slot"]
        cov = " ".join(f"{p['complete_at_deadline'] * 100:.0f}" for p in ps)
        print(f"| {r['run']} | {r['msgs']} × {r['msg_bytes']} | {r['links']} (+{r['fast_share'] * 100:.0f} %) | {r['seed']} | "
              f"{r['gossip_dial']} | {r['slots']} | {cov} | {ps[0]['held_at_deadline_mean'] * 100:.1f} → "
              f"{ps[-1]['held_at_deadline_mean'] * 100:.1f} % | {fmt_lat(r['lat_ms'])} | "
              f"{st.mean(p['kappa_slot'] for p in ps):.2f} | {sum(p['never_delivered'] for p in ps):,} |")
    for r in res:
        print(f"\n**{r['run']}** per slot ({r['hosts']} hosts, {r['conns_mean']:.0f} connections and "
              f"{r['mesh_mean']:.1f} mesh peers per node at slot 0)\n")
        print("| slot | nodes with all at 4 s | held at 4 s mean / min | all by 12 s | latency p50/p90/p99/max (s) | "
              "κ (slot / by 4 s) | copies per msg | IDONTWANT ids rx per node | fwd dropped / all timeouts / all queue-full drops | "
              "MiB rx/tx per node | MiB rx in last 4 s |")
        print("|---|---|---|---|---|---|---|---|---|---|---|")
        for p in r["per_slot"]:
            print(f"| {p['slot']} | {p['complete_at_deadline'] * 100:.1f} % | {p['held_at_deadline_mean'] * 100:.2f} / "
                  f"{p['held_at_deadline_min'] * 100:.1f} % | {p['complete_at_slot_end'] * 100:.1f} % | {fmt_lat(p['lat_ms'])} | "
                  f"{p['kappa_slot']:.2f} / {p['kappa_deadline']:.2f} | {p['copies_per_msg']:.2f} | "
                  f"{p['idontwant_ids_per_node']:,.0f} | {p['fwd_dropped']:,} / {p['timed_out']:,} / {p['queue_full']:,} | "
                  f"{p['rx_MiB_per_node']:.1f} / {p['tx_MiB_per_node']:.1f} | {p['tail_rx_MiB_per_node']:.2f} |")
        print(f"\nDrain ({r['run']}, after the last slot): {r['drain_rx_MiB_per_node']:.2f} MiB rx per node. "
              f"Publish errors {r['errors']}, connection errors {r['conn_errors']}.\n")
        print("\nLink use is libp2p bytes ÷ link cap, per node, averaged over slots 2 onwards. Sent bytes are counted "
              "when written to TCP, so they can run ahead of the wire by the socket send buffer; "
              "`pcap_rate.py` gives on-wire rates.\n")
        print("| link class | nodes | cap down/up (Mbit/s) | up, slot mean / max node | up, 4 s window mean / max node | "
              "down, slot mean / max node | down, 4 s window mean / max node | fwd dropped per node·slot | "
              "nodes·slots with all at 4 s | msgs it published: count, mean share of nodes holding them at 4 s |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for cls, d in r["links_use"].items():
            f = lambda k: f"{d[k] * 100:.0f} %"
            print(f"| {cls} | {d['nodes']} | {d['down_cap_Mbps']:.0f}/{d['up_cap_Mbps']:.0f} | {f('up_slot_mean')} / {f('up_slot_max')} | "
                  f"{f('up_window_mean')} / {f('up_window_max')} | {f('down_slot_mean')} / {f('down_slot_max')} | "
                  f"{f('down_window_mean')} / {f('down_window_max')} | "
                  f"{d['fwd_dropped_per_node_slot']:,.0f} | {d['complete_at_deadline'] * 100:.1f} % | "
                  f"{d['published']:,}, " + ("–" if d['published_held_at_deadline'] is None else
                                             f"{d['published_held_at_deadline'] * 100:.1f} %") + " |")


def mesh_summary(run):
    """Observed peering and gossipsub mesh (flood runs with the wbsim peer manager), from the `mesh` events logged just
    before publishing starts in each slot. Cached in mesh.json."""
    import numpy as np
    cache = os.path.join(run, "mesh.json")
    if os.path.exists(cache) and os.path.getmtime(cache) > os.path.getmtime(os.path.join(run, "shadow.log")):
        return json.load(open(cache))
    cfg = json.load(open(os.path.join(run, "run.json")))
    nodes = cfg["nodes"]
    fast = np.array([nd["link"] == "cloud" for nd in nodes])
    joins = [set(nd.get("topics") or [0]) for nd in nodes]
    ev = defaultdict(dict)  # slot -> node -> event
    for f in glob.glob(os.path.join(run, "shadow.data/hosts/*/wbsim.*.stdout")):
        for line in open(f):
            if '"ev":"mesh"' in line:
                e = json.loads(line)
                ev[e["slot"]][e["node"]] = e
    subs = {t: sum(t in j for j in joins) for t in sorted(set().union(*joins))}
    out = dict(subnet_subscribers=subs, subnet_subscribers_slow={t: sum(t in j and not fast[i] for i, j in enumerate(joins))
                                                                 for t in subs})
    st = lambda x: dict(mean=float(np.mean(x)), min=int(np.min(x)), p10=float(np.percentile(x, 10)),
                        max=int(np.max(x))) if len(x) else None
    for s in sorted(ev):
        E = ev[s]
        slow_ids = [i for i in E if not fast[i]]
        fast_ids = [i for i in E if fast[i]]
        d = {}
        conns = {i: E[i]["conns"] for i in E}
        d["conns_slow"] = st([len(conns[i]) for i in slow_ids])
        d["conns_fast"] = st([len(conns[i]) for i in fast_ids])
        d["conns_slow_fast_share"] = float(np.mean([np.mean([fast[j] for j in conns[i]]) for i in slow_ids if conns[i]]))
        d["subnet_peers_slow"] = st([sum(bool(joins[j] & joins[i]) for j in conns[i]) for i in slow_ids])
        ms = [E[i]["mesh"][str(next(iter(joins[i])))] for i in slow_ids]
        d["mesh_slow"] = st([len(m) for m in ms])
        d["mesh_slow_fast"] = st([sum(fast[j] for j in m) for m in ms])
        h = np.bincount([sum(fast[j] for j in m) for m in ms], minlength=13)
        d["mesh_slow_fast_hist"] = [int(x) for x in h]
        # fast hosts: per topic, mesh size and fast mesh peers; fast-only mesh graph per topic
        mf, mff, comps = [], [], []
        for t in subs:
            adj = defaultdict(set)
            for i in fast_ids:
                m = E[i]["mesh"].get(str(t), [])
                mf.append(len(m))
                ff = [j for j in m if fast[j]]
                mff.append(len(ff))
                for j in ff:
                    adj[i].add(j)
                    adj[j].add(i)
            seen, big = set(), 0
            for i in fast_ids:
                if i in seen:
                    continue
                stack, size = [i], 0
                seen.add(i)
                while stack:
                    u = stack.pop()
                    size += 1
                    for v in adj[u]:
                        if v not in seen:
                            seen.add(v)
                            stack.append(v)
                big = max(big, size)
            comps.append(big / max(len(fast_ids), 1))
        d["mesh_fast"] = st(mf)
        d["mesh_fast_fast"] = st(mff)
        d["fast_core_largest_component"] = float(min(comps)) if comps else None
        out[str(s)] = d
    json.dump(out, open(cache, "w"))
    return out


def main(runs):
    if runs and runs[0] == "--mesh":
        for r in runs[1:]:
            print(r, json.dumps(mesh_summary(r), indent=1))
        return
    if runs and runs[0] == "--levers":
        return lever_report(runs[1:])
    if runs and json.load(open(os.path.join(runs[0], "run.json")))["mode"] == "flood":
        return flood_report(runs)
    res = [summarise(r) for r in runs]
    keys = [k for k in res[0] if not k.startswith("_") and k != "run"]
    for r in res[1:]:
        keys += [k for k in r if not k.startswith("_") and k != "run" and k not in keys]
    print("| metric | " + " | ".join(r["run"] for r in res) + " |")
    print("|---|" + "---|" * len(res))
    for k in keys:
        print(f"| {k} | " + " | ".join(str(r.get(k, "–")) for r in res) + " |")

    print("\n**Per-node bytes per slot (mean), vote phase [0 s, 8 s) and proof phase [8 s, 12 s)**\n")
    print("| run | node class | votes rx | votes tx | proofs rx | proofs tx |")
    print("|---|---|---|---|---|---|")
    for r in res:
        for cls in sorted(r["_bytes"]):
            d = r["_bytes"][cls]
            f = lambda k: f"{d.get(k, 0) / 2**20:,.2f} MiB"
            print(f"| {r['run']} | {cls} | {f(('votes', 'rx'))} | {f(('votes', 'tx'))} | {f(('proofs', 'rx'))} | {f(('proofs', 'tx'))} |")


if __name__ == "__main__":
    main(sys.argv[1:])
