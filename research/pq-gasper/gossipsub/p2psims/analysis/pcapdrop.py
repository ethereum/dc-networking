#!/usr/bin/env python3
"""Packets lost on the way into home nodes, counted from packet captures (PQ Gasper subnet specs study, Nov 23;
coordinator 15:1x). For runs made with gen_config.py --pcap N: N home hosts and one 1 Gbit host write packet headers to
shadow.data/hosts/NAME/eth0.pcap. Shadow captures a sent packet when the upload relay takes it from the interface,
before the path's loss is drawn (core/worker.rs: per data packet, never for pure ACKs), and a received packet when the
download relay hands it to the interface, after the host's inbound router queue (CoDel, network/router/codel_queue.rs)
and the download rate limit (host/network/interface.rs pop/push). Shadow's TCP numbers data packets one by one and a
retransmission repeats the number (host/descriptor/tcp.c L1518), and nothing reorders a flow (FIFO jitter and queues).
1. Exact, captured pairs: per TCP connection and sequence number, transmissions the sender put on the wire against copies
   that reached the receiver; lost = sent - received, by the send time of the lost transmissions. Compared with the
   configured loss of the path (network graph, Shadow's shortest path by latency); with --access-loss-scale 0 only the
   backbone loses packets, so the excess is dropped at the receiver's inbound queue. Inbound queue delay = arrival minus
   send time minus the path's latency (it includes the path's jitter), for packets sent and received once.
2. Lower bound, every sender into a captured home host: holes in the sequence numbers that arrive (a lost original
   followed by a later packet of the same connection; misses losses at the end of a flight), and duplicates.
3. Download use of the captured home hosts from their captures: bytes per 10 ms against the download cap.
Slots 2 to the last (by send time for 1, by arrival for 2 and 3).
usage: python3 -I .amp-out/pcapdrop.py RUN"""
import collections, glob, heapq, json, os, re, struct, sys
import numpy as np

run = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
rj = json.load(open(f"{run}/run.json"))
S, T0, SL = rj["slots"], rj["first_slot_s"], rj["slot_s"]
W0, W1 = T0 + 2 * SL, T0 + S * SL


def cls(n):
    return "1G" if n["link"] == "cloud" else n["link"].replace("x", "/")


def bps(s):
    v, u = s.split()
    return float(v) * {"Mbit": 1e6, "Gbit": 1e9}[u]


node = {n["id"]: n for n in rj["nodes"]}
ipidx = {bytes(int(x) for x in n["ip"].split(".")): n["id"] for n in rj["nodes"]}
C = {i: cls(n) for i, n in node.items()}

# network graph and attachment points, routed as Shadow does: shortest path by latency, then loss; self-loop for a node
y = open(f"{run}/shadow.yaml").read()
adj, selfloop = collections.defaultdict(list), {}
for m in re.finditer(r'edge \[\s*source (\d+)\s*target (\d+)\s*latency "(\d+) us"\s*(?:jitter "(\d+) us"\s*)?'
                     r'packet_loss ([0-9.]+)', y):
    s, t, lat, jit, loss = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4) or 0), float(m.group(5))
    if s == t:
        selfloop[s] = (lat, loss, jit)
    else:
        adj[s].append((t, lat, loss, jit))
        adj[t].append((s, lat, loss, jit))
hostnet = {int(m.group(1)): int(m.group(2)) for m in re.finditer(r"\n  n(\d{4}):\n    network_node_id: (\d+)", y)}
_paths = {}


def path(a, b):
    """(latency us, loss, mean jitter us) of the path from host a to host b."""
    na, nb = hostnet[a], hostnet[b]
    if na not in _paths:
        best, pq = {na: (0, 0.0, 0)}, [(0, 0.0, 0, na)]
        while pq:
            lat, loss, jit, u = heapq.heappop(pq)
            if (lat, loss) > best[u][:2]:
                continue
            for v, l2, p2, j2 in adj[u]:
                c = (lat + l2, 1 - (1 - loss) * (1 - p2), jit + j2)
                if v not in best or c[:2] < best[v][:2]:
                    best[v] = c
                    heapq.heappush(pq, (c[0], c[1], c[2], v))
        best[na] = selfloop[na]
        _paths[na] = best
    return _paths[na][nb]


files = {int(os.path.basename(os.path.dirname(f))[1:]): f for f in glob.glob(f"{run}/shadow.data/hosts/n*/eth0.pcap")
         if os.path.getsize(f) > 24}
cap = set(files)
capb = {b: i for b, i in ipidx.items() if i in cap}
HDR, PKT = struct.Struct("<IIII"), struct.Struct("!12x4s4sHHIIBB")
sent, recv = collections.defaultdict(list), collections.defaultdict(list)
lb = collections.defaultdict(lambda: np.zeros(3))      # (sender class, receiver class): received, holes, duplicates
BIN = 0.01
nb = int(round((W1 - W0) / BIN))
dl = {}                                                 # captured home host: bytes received per 10 ms
for h, f in sorted(files.items()):
    buf = open(f, "rb").read()
    magic, link = struct.unpack_from("<I", buf, 0)[0], struct.unpack_from("<I", buf, 20)[0]
    div, o0 = (1e9 if magic == 0xA1B23C4D else 1e6), (14 if link == 1 else 0)
    me = bytes(int(x) for x in node[h]["ip"].split("."))
    home = C[h] != "1G"
    bins = np.zeros(nb) if home else None
    conns = {}
    off, n = 24, len(buf)
    while off + 16 <= n:
        sec, frac, incl, orig = HDR.unpack_from(buf, off)
        p = off + 16 + o0
        off += 16 + incl
        if incl - o0 < 34 or buf[p + 9] != 6:
            continue
        t = sec + frac / div
        src, dst, sport, dport, seq, ack, offs, flags = PKT.unpack_from(buf, p)
        pay = orig - o0 - 20 - (offs >> 4) * 4
        if src == me:
            if pay > 0 and dst in capb and W0 - 1 <= t < W1 + 1:
                sent[(h, capb[dst], sport, dport, seq)].append(t)
            continue
        if dst != me:
            continue
        if home and W0 <= t < W1:
            bins[int((t - W0) / BIN)] += orig - o0
        if pay <= 0:
            continue
        si = ipidx.get(src)
        if si in cap and W0 - 1 <= t < W1 + 5:
            recv[(si, h, sport, dport, seq)].append(t)
        if not home:
            continue
        st = conns.get((src, sport, dport))
        inwin = W0 <= t < W1
        if st is None:
            conns[(src, sport, dport)] = [seq, set()]
            k = 0
        elif seq == st[0] + 1:
            st[0] = seq
            k = 0
        elif seq > st[0] + 1:
            k = seq - st[0] - 1
            st[1].update(range(st[0] + 1, seq))
            st[0] = seq
        elif seq in st[1]:
            st[1].discard(seq)
            k = -1
        else:
            k = -2
        if inwin and si is not None:
            v = lb[(C[si], C[h])]
            v[0] += 1
            if k > 0:
                v[1] += k
            elif k == -2:
                v[2] += 1
    if home:
        dl[h] = bins

PH = [("4-5 s", 4, 5), ("5-6 s", 5, 6), ("6-8 s", 6, 8), ("other", None, None)]


def phase(t):
    x = (t - T0) % SL
    for i, (_, a, b) in enumerate(PH[:-1]):
        if a <= x < b:
            return i
    return len(PH) - 1


agg = collections.defaultdict(lambda: dict(pairs=set(), sent=0, lost=0, extra=0, exp=0.0, lph=np.zeros(len(PH)),
                                            sph=np.zeros(len(PH)), dly=collections.defaultdict(list)))
for k, ts in sent.items():
    ts.sort()
    if not W0 <= ts[0] < W1:
        continue
    si, hi = k[0], k[1]
    a = agg[(C[si], C[hi])]
    lat, loss, jit = path(si, hi)
    r = recv.get(k, [])
    a["pairs"].add((si, hi))
    a["sent"] += len(ts)
    a["exp"] += len(ts) * loss
    for t in ts:
        a["sph"][phase(t)] += 1
    lost = len(ts) - len(r)
    if lost > 0:
        a["lost"] += lost
        for t in ts[:lost]:
            a["lph"][phase(t)] += 1
    else:
        a["extra"] -= lost
    if len(ts) == 1 and len(r) == 1:
        a["dly"][phase(ts[0])].append(1000 * (r[0] - ts[0] - lat / 1e6))
        a["dly"]["jit"].append(jit / 1000)

order = sorted({c for c in C.values()}, key=lambda c: (c == "1G", c))
print(f"== {os.path.basename(run)}: captured {len(cap)} hosts ("
      + ", ".join(f"{c} {sum(1 for i in cap if C[i] == c)}" for c in order) + f"), slots 2-{S - 1}; data packets only")
print("\n# 1. Exact, between captured hosts: transmissions sent vs copies that reached the receiver's interface "
      "(per 1,000 sent)")
print(f"{'path':20s} {'pairs':>5s} {'sent':>9s} {'lost':>7s} {'/1000':>7s} {'config':>7s} {'excess':>7s} | lost by send time "
      "4-5/5-6/6-8/other s (% of lost; loss /1000 in 4-5 s) | inbound queue delay ms p50/p90/p99/max, sent 4-5 s; "
      "other p50/p99 (path jitter mean ms)")
for b in order:
    for a_ in order:
        a = agg.get((a_, b))
        if not a or a["sent"] < 1000:
            continue
        L = a["lost"]
        sh = "/".join(f"{100 * x / max(L, 1):.0f}" for x in a["lph"])
        d45 = np.array(a["dly"][0] or [0.0])
        doth = np.array(sum((a["dly"][i] for i in (1, 2, 3)), []) or [0.0])
        print(f"{a_ + ' -> ' + b:20s} {len(a['pairs']):5d} {a['sent']:9d} {L:7d} {1000 * L / a['sent']:7.2f} "
              f"{1000 * a['exp'] / a['sent']:7.2f} {1000 * (L - a['exp']) / a['sent']:7.2f} | {sh} "
              f"({1000 * a['lph'][0] / max(a['sph'][0], 1):.1f}) | "
              + "/".join(f"{np.percentile(d45, q):.1f}" for q in (50, 90, 99)) + f"/{d45.max():.1f}; "
              f"{np.percentile(doth, 50):.1f}/{np.percentile(doth, 99):.1f} ({np.mean(a['dly']['jit'] or [0]):.1f})"
              + (f" [received more than sent: {a['extra']}]" if a["extra"] else ""))
print("\n# 2. Lower bound, every sender into the captured home hosts: holes (lost originals followed by a later packet)"
      " and duplicates per 1,000 received data packets")
for b in order:
    for a_ in order:
        v = lb.get((a_, b))
        if v is None or v[0] < 1000:
            continue
        print(f"  {a_ + ' -> ' + b:20s} received {v[0]:10.0f}  holes {1000 * v[1] / v[0]:7.2f}  duplicates "
              f"{1000 * v[2] / v[0]:7.2f}")
print("\n# 3. Download of the captured home hosts (bytes on the wire per 10 ms vs the cap)")
byc = collections.defaultdict(list)
for h, bins in dl.items():
    capb10 = bps(node[h]["down"]) / 8 * BIN
    for s in range(2, S):
        base = int(round(((s - 2) * SL) / BIN))
        x = bins[base + 400: base + 800] / capb10   # 4.0-8.0 s into the slot
        r100 = np.convolve(bins[base + 400: base + 600], np.ones(10), "valid") / (10 * capb10)
        byc[C[h]].append((x[:100].mean(), x.mean(), (x[:200] >= 0.9).mean(), r100.max()))
for c, v in byc.items():
    v = np.array(v)
    print(f"  {c}: {len(v)} node-slots; mean use 4-5 s {100 * v[:, 0].mean():.1f} %, 4-8 s {100 * v[:, 1].mean():.1f} %; "
          f"10-ms bins in 4-6 s at >= 90 % of the cap {100 * v[:, 2].mean():.1f} %; busiest 100 ms in 4-6 s, p50/p90/max of "
          f"node-slots {100 * np.percentile(v[:, 3], 50):.0f}/{100 * np.percentile(v[:, 3], 90):.0f}/{100 * v[:, 3].max():.0f} %")
