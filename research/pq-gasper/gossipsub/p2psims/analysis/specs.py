#!/usr/bin/env python3
"""PQ Gasper subnet specs study (Nov 23): 1,600 signatures per subnet per slot, which every node needs by 8.0 s.
Upload (bytes handed to TCP) and download (bytes read from TCP) per class, all traffic, in Mbit/s and as % of the
node's link, over 4-8 s and 4-5 s of each slot (PQ publishing starts at 4.0 s): mean, p90 and p99 over node-slots,
the busiest node (highest mean over the slots, as pq1600.py) and the highest node-slot; plus the PQ topic's share of
the download (wbsim's PQ send counter counts queued sends, dropped ones too, so it gives no upload share). A
node-slot counts if the host is online from slot start to the deadline (as pq1600.py).
GROUP=vcount: 1 Gbit hosts split into <= 8 and > 8 validators.
usage: python3 -I .amp-out/specs.py RUN [--slots A B]"""
import glob, os, re, sys
from collections import defaultdict
from multiprocessing import Pool
import numpy as np

sys.path.insert(0, "repo/sim")
import analyze  # noqa: E402

run = sys.argv[1] if os.path.isdir(sys.argv[1]) else f"runs/{sys.argv[1]}"
cfg = analyze.read_cfg(run)
nodes, t0, S, SL, OFF = cfg["nodes"], cfg["first_slot_s"], cfg["slots"], cfg["slot_s"], cfg["vote_offset_s"]
lo, hi = 2, S - 1
if "--slots" in sys.argv:
    j = sys.argv.index("--slots")
    lo, hi = int(sys.argv[j + 1]), int(sys.argv[j + 2])
GROUP = os.environ.get("GROUP")


def cls(nd):
    c = nd["link"]
    if GROUP == "vcount" and c == "cloud":
        c += "-v<=8" if nd.get("vcount", 0) <= 8 else "-v>8"
    return c


link = [cls(nd) for nd in nodes]
CL = sorted(set(link), key=lambda c: (c.startswith("cloud"), c))
NAME = lambda c: c.replace("cloud", "1 Gbit").replace("x", "/") if not c.startswith("cloud") or GROUP else "1 Gbit"


def cap(s):
    v, u = s.split()
    return float(v) * {"Kbit": 1e3, "Mbit": 1e6, "Gbit": 1e9}[u]


UP = [cap(nd["up"]) for nd in nodes]
DOWN = [cap(nd["down"]) for nd in nodes]
off_iv = [nd.get("offline", []) for nd in nodes]
DL = {s: max(m[4] for m in msgs) / 1e3 for s, msgs in enumerate(cfg["sched"]) if msgs}
KEYS = ["t", "tx", "rx", "topic_msg_sent_bytes", "topic_msg_recv_bytes"]
RE = {k: re.compile(r'[{,]"%s":([0-9.]+)' % k) for k in KEYS}
NODE_RE = re.compile(r'"node":(\d+)')


def per_node(f):
    rows, node = [], None
    for line in open(f):
        if '"ev":"tick"' in line:
            rows.append([float(m.group(1)) if (m := RE[k].search(line)) else 0.0 for k in KEYS])
            if node is None:
                node = int(NODE_RE.search(line).group(1))
    if node is None or not rows:
        return None
    T = np.array(sorted(rows))

    def at(t):
        j = np.searchsorted(T[:, 0], t + 0.05) - 1
        return T[j, 1:] if j >= 0 and abs(T[j, 0] - t) <= 0.05 else None

    out = {}
    for s in range(lo, hi + 1):
        a = t0 + SL * s
        if s not in DL or any(x < a + DL[s] and y > a for x, y in off_iv[node]):
            continue
        x4, x5, x8 = at(a + OFF), at(a + OFF + 1.0), at(a + OFF + 4.0)
        if x4 is None or x5 is None or x8 is None or not ((x8 >= x5).all() and (x5 >= x4).all()):
            continue
        d48, d45 = (x8 - x4) * 8 / 4.0, (x5 - x4) * 8 / 1.0  # bit/s: tx, rx, PQ sent, PQ received
        out[s] = (d48, d45)
    return node, out


with Pool(int(os.environ.get("POOL", "12"))) as pool:
    res = [x for x in pool.map(per_node, glob.glob(f"{run}/shadow.data/hosts/*/wbsim.*.stdout"), chunksize=8) if x]
got = sorted({s for _, o in res for s in o})
print(f"== {os.path.basename(run.rstrip('/'))}: {len(nodes)} hosts ("
      + ", ".join(f"{NAME(c)} {link.count(c)}" for c in CL) + f"), slots {got[0]}-{got[-1]} analysed; "
      f"{cfg.get('msgs', 0):,} signatures per subnet per slot, every node needs all by 8.0 s")
print("   Upload = bytes handed to TCP (can run ahead of the link while socket buffers fill); download = bytes read "
      "from TCP. All traffic; the last column is the PQ topic's share of the download. Node-slots online through the deadline.\n")
print("| Class (hosts, link down/up) | Window | Upload Mbit/s: mean / p90 / p99 / busiest node / top node-slot "
      "| Upload % of link: mean / busiest | Download Mbit/s: mean / p90 / p99 / busiest node / top node-slot "
      "| Download % of link: mean / busiest | PQ share of download |")
print("|---|---|---|---|---|---|---|")
for c in CL:
    members = [i for i in range(len(nodes)) if link[i] == c]
    ups = sorted({UP[i] for i in members})
    dns = sorted({DOWN[i] for i in members})
    lk = "/".join(f"{x / 1e6:g}" for x in (dns[0], ups[0])) if len(ups) == len(dns) == 1 else "mixed"
    for w, wname in ((0, "4-8 s"), (1, "4-5 s")):
        vals, pern = [], defaultdict(list)
        for i, o in res:
            if link[i] != c:
                continue
            for s, x in o.items():
                v = x[w]
                vals.append((v[0], v[1], v[2], v[3], v[0] / UP[i], v[1] / DOWN[i]))
                pern[i].append(v)
        if not vals:
            continue
        A = np.array(vals)
        nm = {i: np.mean(np.array(x), axis=0) for i, x in pern.items()}
        bu = max(nm, key=lambda i: nm[i][0])
        bd = max(nm, key=lambda i: nm[i][1])
        f = lambda col: " / ".join(f"{x / 1e6:.1f}" for x in (A[:, col].mean(), np.percentile(A[:, col], 90),
                                                               np.percentile(A[:, col], 99)))
        print(f"| {NAME(c)} ({len(members)}, {lk}) | {wname} | {f(0)} / {nm[bu][0] / 1e6:.1f} (n{bu}) / "
              f"{A[:, 0].max() / 1e6:.1f} | {100 * A[:, 4].mean():.1f} / {100 * nm[bu][0] / UP[bu]:.1f} | "
              f"{f(1)} / {nm[bd][1] / 1e6:.1f} (n{bd}) / {A[:, 1].max() / 1e6:.1f} | "
              f"{100 * A[:, 5].mean():.1f} / {100 * nm[bd][1] / DOWN[bd]:.1f} | "
              f"{100 * A[:, 3].sum() / max(A[:, 1].sum(), 1):.0f} % |")
